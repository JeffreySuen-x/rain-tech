#!/usr/bin/env python3
"""Local lifecycle manager. Business accounts, sessions and jobs stay in server/SQLite."""
import contextlib
import hashlib
import hmac
import html
import json
import os
import platform
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR_NAME = "澍雨"
DEFAULT_PORT = 5196
MAX_FORM = 16384
RUNTIME_KEYS = {'SHUYU_DB', 'SHUYU_ASSET_ROOT', 'SHUYU_STATIC_DIR', 'SHUYU_PUBLIC_ORIGIN'}
PROVIDER_FIELDS = {'providerUrl': 'SHUYU_PROVIDER_URL', 'providerModel': 'SHUYU_PROVIDER_MODEL',
                   'visionModel': 'SHUYU_PROVIDER_VISION_MODEL', 'asrModel': 'SHUYU_PROVIDER_ASR_MODEL',
                   'asrAdapter': 'SHUYU_PROVIDER_ASR_ADAPTER'}


class DesktopError(Exception):
    """A message safe to display; underlying exceptions are never reflected."""


def bundle_root():
    return Path(os.environ.get('SHUYU_BUNDLE_ROOT', Path(__file__).resolve().parents[1])).resolve()


def project_root(bundle):
    return bundle / 'project' if (bundle / 'project').is_dir() else bundle


def runtime_bin(bundle):
    return bundle / 'runtime/bin'


def user_data_dir():
    if os.environ.get('SHUYU_DATA_DIR'):
        return Path(os.environ['SHUYU_DATA_DIR']).expanduser().absolute()
    if platform.system() == 'Darwin':
        base = Path.home() / 'Library/Application Support'
    elif platform.system() == 'Windows':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return base / APP_DIR_NAME


def log_line(path, message):
    with contextlib.suppress(OSError):
        with path.open('a', encoding='utf-8') as stream:
            stream.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(.2)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def browser_open(url):
    if os.environ.get('SHUYU_NO_BROWSER') != '1':
        webbrowser.open(url)


def secure_equal(left, right):
    return isinstance(left, str) and isinstance(right, str) and hmac.compare_digest(left.encode('utf-8'), right.encode('utf-8'))


def atomic_bytes(path, payload):
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


class InstanceLock:
    """OS releases the lock even after a crash; metadata alone never owns an instance."""
    def __init__(self, path):
        self.path, self.stream = path, None

    def acquire(self):
        self.stream = self.path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.stream.seek(0)
                if not self.stream.read(1):
                    self.stream.write(b'0'); self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self.stream.close(); self.stream = None
            return False

    def close(self):
        if self.stream:
            self.stream.close(); self.stream = None


class DesktopApp:
    def __init__(self):
        self.bundle = bundle_root()
        self.project = project_root(self.bundle)
        self.data = user_data_dir()
        self.port = int(os.environ.get('SHUYU_PORT', DEFAULT_PORT))
        if not 1 <= self.port <= 65535:
            raise DesktopError('应用端口无效，请检查 SHUYU_PORT。')
        self.log_path = self.data / 'desktop.log'
        self.config_path = self.data / 'local.json'
        self.db_path = self.data / 'shuyu.sqlite3'
        self.asset_root = self.data / 'assets'
        self.instance_path = self.data / 'desktop-instance.json'
        self.api = self.worker = None
        self.lock = InstanceLock(self.data / 'desktop.lock')
        self.nonce = secrets.token_urlsafe(32)
        self.identity = hashlib.sha256(str(self.data.resolve()).encode()).hexdigest()
        self.done = threading.Event()
        self.submit_lock = threading.Lock()
        self.lifecycle_lock = threading.RLock()
        self.setup_token = None
        self.setup_complete = False
        self.setup_error = ''
        self.control = None
        self.exit_code = 0
        self.config = {}
        self.first_account = False
        self._log_stream = None
        self._windows_job = None

    def prepare_data_dir(self):
        # Preserve configured spelling until link validation; allow OS aliases.
        aliases = {Path('/tmp'), Path('/var'), Path('/etc')} if platform.system() == 'Darwin' else set()
        if any(path.is_symlink() and path not in aliases for path in (self.data, *self.data.parents)):
            raise DesktopError('数据目录不能是符号链接。')
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != 'nt':
            os.chmod(self.data, 0o700)

    def _server_imports(self):
        # Explicit project path also works with Windows embedded Python isolated _pth.
        if str(self.project) not in sys.path:
            sys.path.insert(0, str(self.project))
        from server.app import SCHEMA, connect
        from server import agriculture, agent_runtime
        return SCHEMA, connect, agriculture, agent_runtime

    def validate_database(self, path):
        try:
            with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError()
                if db.execute('PRAGMA foreign_key_check').fetchone():
                    raise ValueError()
                users = db.execute('SELECT id,username,password FROM users').fetchall()
                db.execute('SELECT id FROM workspaces LIMIT 1')
            return users
        except (sqlite3.Error, ValueError):
            raise DesktopError('本机数据库缺失、损坏或版本不兼容。请保留数据目录并从备份恢复。') from None

    def validate_seed(self, seed):
        try:
            manifest_path = seed / 'manifest.json'
            if not manifest_path.is_file() or manifest_path.stat().st_size > 1024 * 1024:
                raise ValueError()
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest.get('fixtureVersion') != 'student-demo-v1' or manifest.get('owner') != 'student-demo-owner':
                raise ValueError()
            _, _, agriculture, _ = self._server_imports()
            with sqlite3.connect(f"{(seed / 'shuyu.sqlite3').resolve().as_uri()}?mode=ro", uri=True) as db:
                db.row_factory = sqlite3.Row
                for table in ('sessions', 'turns', 'artifacts', 'commands', 'agriculture_device_events'):
                    if db.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                        raise ValueError()
                assets = []
                for row in db.execute("SELECT * FROM agriculture_entities WHERE kind='asset'"):
                    item = agriculture.unpack(row)
                    path, asset = agriculture.asset_content(db, 'student-demo-owner', item['id'], seed / 'assets')
                    assets.append(dict(storageKey=path.name, sha256=asset['sha256'], byteSize=asset['byteSize']))
            if sorted(assets, key=lambda i: i['storageKey']) != manifest.get('assets'):
                raise ValueError()
            if {i['storageKey'] for i in assets} != {str(p.relative_to(seed / 'assets')) for p in (seed / 'assets').rglob('*') if p.is_file()}:
                raise ValueError()
        except Exception:
            raise DesktopError('演示资料清单、原件或数据库校验失败，请从项目源码重新生成完整示例。') from None

    def seed_if_needed(self):
        if self.db_path.exists():
            self.validate_database(self.db_path)
            return
        if self.config_path.exists() or self.asset_root.exists():
            raise DesktopError('已有配置或资料，但数据库缺失。为保护数据，启动已停止；请从备份恢复。')
        seed = Path(os.environ.get('SHUYU_SEED_DIR', self.bundle / 'seed'))
        staging = self.data / ('.initialize-' + secrets.token_hex(8))
        staging.mkdir(mode=0o700)
        try:
            staged_db, staged_assets = staging / 'shuyu.sqlite3', staging / 'assets'
            if seed.exists():
                if not (seed / 'shuyu.sqlite3').is_file() or not (seed / 'assets').is_dir():
                    raise DesktopError('随包演示资料不完整，请重新解压完整软件包。')
                if seed.is_symlink() or any(p.is_symlink() for p in seed.rglob('*')):
                    raise DesktopError('演示资料包含不安全的文件链接。')
                seed_users = self.validate_database((seed / 'shuyu.sqlite3').resolve())
                if len(seed_users) != 1 or seed_users[0][0] != 'student-demo-owner' or seed_users[0][2] != '!student-setup-required':
                    raise DesktopError('演示库不符合合成资料版本，启动已停止。')
                self.validate_seed(seed)
                shutil.copy2(seed / 'shuyu.sqlite3', staged_db)
                shutil.copytree(seed / 'assets', staged_assets)
            else:
                schema, connect, agriculture, agent_runtime = self._server_imports()
                with contextlib.closing(connect(staged_db)) as db:
                    db.executescript(schema); agriculture.migrate(db); agent_runtime.migrate(db)
                staged_assets.mkdir()
            self.validate_database(staged_db.resolve())
            # The database is the completion marker, installed last. Roll back assets on failure.
            os.replace(staged_assets, self.asset_root)
            try:
                os.replace(staged_db, self.db_path)
            except BaseException:
                shutil.rmtree(self.asset_root)
                raise
            if os.name != 'nt':
                os.chmod(self.db_path, 0o600)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def config_values(self):
        if not self.config_path.exists():
            return {}
        from server.local_config import ALLOWED
        try:
            if self.config_path.is_symlink() or self.config_path.stat().st_size > 65536:
                raise ValueError()
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result: raise ValueError()
                    result[key] = value
                return result
            value = json.loads(self.config_path.read_text(encoding='utf-8'), object_pairs_hook=pairs)
            if not isinstance(value, dict) or set(value) - ALLOWED or any(not isinstance(v, str) or '\x00' in v for v in value.values()):
                raise ValueError()
            if len(value.get('SHUYU_SECRET', '')) < 32:
                raise ValueError()
            self.validate_provider(value)
            return value
        except (OSError, ValueError, UnicodeError):
            raise DesktopError('local.json 配置损坏或字段无效；请先备份，再修复配置文件。') from None

    @staticmethod
    def validate_provider(values):
        url = values.get('SHUYU_PROVIDER_URL', '')
        if url:
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError('invalid URL')
            parsed.port  # Force urllib to validate numeric ports and the 0–65535 range.
        caps = values.get('SHUYU_PROVIDER_CAPABILITIES', '')
        if caps and (set(caps.split(',')) - {'text', 'vision', 'asr'}):
            raise ValueError('invalid capabilities')
        if values.get('SHUYU_PROVIDER_ASR_ADAPTER', 'transcriptions') not in ('transcriptions', 'input_audio'):
            raise ValueError('invalid adapter')
        if any(len(v) > 8192 or '\n' in v or '\r' in v or '\x00' in v for k, v in values.items() if k.startswith('SHUYU_PROVIDER_')):
            raise ValueError('invalid provider value')
        if values.get('SHUYU_PROVIDER_KEY') and (not url or not values.get('SHUYU_PROVIDER_MODEL')):
            raise ValueError('missing provider fields')

    def write_config(self, provider):
        values = {k: v for k, v in self.config.items() if k not in RUNTIME_KEYS}
        values.setdefault('SHUYU_SECRET', secrets.token_hex(32))
        values['SHUYU_ENV'] = 'development'
        values.update(provider)
        self.validate_provider(values)
        atomic_json(self.config_path, values)
        self.config = values

    def child_env(self):
        # Do not inherit accidental model credentials or a different product's runtime config.
        env = {k: v for k, v in os.environ.items() if not k.startswith('SHUYU_')}
        env.update(self.config)
        env.update(SHUYU_ENV='development', SHUYU_DB=str(self.db_path),
                   SHUYU_ASSET_ROOT=str(self.asset_root), SHUYU_STATIC_DIR=str(self.project / 'web/dist'),
                   SHUYU_PUBLIC_ORIGIN=f'http://127.0.0.1:{self.port}', PYTHONUNBUFFERED='1')
        env['PYTHONPATH'] = str(self.project)
        env['PATH'] = str(runtime_bin(self.bundle)) + os.pathsep + env.get('PATH', '')
        return env

    def start_services(self):
        if self.api or self.worker:
            raise DesktopError('服务已在运行。')
        if port_open(self.port):
            raise DesktopError(f'端口 {self.port} 已被其他程序占用。请关闭该程序，或设置 SHUYU_PORT 后重试。')
        python = sys.executable
        if os.name == 'nt' and Path(python).name.lower().startswith('pythonw'):
            python = str(Path(python).with_name('python.exe'))
        # -c explicitly inserts the project for embeddable Python, which ignores PYTHONPATH.
        code = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('server.app',run_name='__main__')"
        common = [python, '-c', code, str(self.project)]
        options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
        self._log_stream = (self.data / 'services.log').open('ab')
        try:
            if os.name == 'nt':
                from desktop.windows_job import WindowsJob
                self._windows_job = WindowsJob()
            self.api = subprocess.Popen(common + ['serve', '--port', str(self.port)], cwd=self.project, env=self.child_env(), stdout=self._log_stream, stderr=subprocess.STDOUT, **options)
            if self._windows_job: self._windows_job.assign(self.api)
            self.worker = subprocess.Popen(common + ['worker'], cwd=self.project, env=self.child_env(), stdout=self._log_stream, stderr=subprocess.STDOUT, **options)
            if self._windows_job: self._windows_job.assign(self.worker)
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if self.done.is_set():
                    raise DesktopError('启动已停止。')
                if self.api.poll() is not None or self.worker.poll() is not None:
                    raise DesktopError('本机服务意外退出，请查看 services.log。')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/api/v1/health', timeout=.5) as response:
                        if response.status == 200: return
                except (OSError, ValueError):
                    time.sleep(.15)
            raise DesktopError('服务启动超时，请查看 services.log。')
        except BaseException:
            self.stop_services()
            raise

    def stop_services(self):
        processes = [p for p in (self.worker, self.api) if p]
        if self._windows_job:
            self._windows_job.close()
            self._windows_job = None
        for process in processes:
            if os.name == 'nt':
                if process.poll() is None:
                    process.terminate()
            else:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    process.kill()
                else:
                    with contextlib.suppress(ProcessLookupError): os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            # Children may survive a parent that already exited; kill the owned process group.
            if os.name != 'nt':
                with contextlib.suppress(ProcessLookupError): os.killpg(process.pid, signal.SIGKILL)
        self.api = self.worker = None
        if self._log_stream:
            self._log_stream.close(); self._log_stream = None

    def needs_account(self):
        users = self.validate_database(self.db_path)
        if not users: return True
        # Only the explicit non-login student placeholder may be claimed. Never reset a private account.
        return len(users) == 1 and users[0][0] == 'student-demo-owner' and users[0][2] == '!student-setup-required'

    def activate_setup(self):
        if not self.setup_token or self.setup_complete:
            self.setup_token = secrets.token_urlsafe(32)
            self.setup_complete = False
        return f'{self.control_origin}/?token={self.setup_token}'

    def apply_setup(self, form):
        get = lambda key: (form.get(key) or [''])[0]
        provider = {}
        for field, key in PROVIDER_FIELDS.items():
            value = get(field).strip()
            if value: provider[key] = value
        key = get('providerKey').strip()
        if key: provider['SHUYU_PROVIDER_KEY'] = key
        if get('clearKey') == 'yes': provider['SHUYU_PROVIDER_KEY'] = ''
        caps = form.get('capability', [])
        if set(caps) - {'text', 'vision', 'asr'}: raise DesktopError('模型能力选择无效。')
        provider['SHUYU_PROVIDER_CAPABILITIES'] = ','.join(sorted(set(caps)))
        proposed = dict(self.config); proposed.update(provider)
        try: self.validate_provider(proposed)
        except ValueError: raise DesktopError('模型配置无效：请检查 HTTPS 地址、模型名与能力。') from None
        first = self.needs_account()
        username, password = get('username').strip(), get('password')
        if first and (not 1 <= len(username) <= 100 or not 8 <= len(password) <= 1024 or password != get('confirm')):
            raise DesktopError('请填写 1–100 字用户名及两次相同的 8–1024 字密码。密码中的空格会原样保留。')
        old_bytes = self.config_path.read_bytes() if self.config_path.exists() else None
        old_config = self.config.copy()
        old_user = None; created_id = None
        was_running = self.api is not None
        self.stop_services()
        try:
            if first:
                from server.app import generate_password_hash
                with sqlite3.connect(self.db_path) as db:
                    db.execute('BEGIN IMMEDIATE')
                    rows = db.execute('SELECT id,username,password FROM users').fetchall()
                    if rows:
                        if len(rows) != 1 or rows[0][0] != 'student-demo-owner' or rows[0][2] != '!student-setup-required':
                            raise DesktopError('账号状态已变化，请重新打开设置页。')
                        old_user = rows[0]
                        db.execute('UPDATE users SET username=?,password=? WHERE id=?', (username, generate_password_hash(password), old_user[0]))
                    else:
                        created_id = secrets.token_hex(16)
                        db.execute('INSERT INTO users VALUES(?,?,?)', (created_id, username, generate_password_hash(password)))
            self.write_config(provider)
            self.start_services()
        except BaseException:
            self.stop_services()
            if old_user or created_id:
                with sqlite3.connect(self.db_path) as db:
                    if old_user: db.execute('UPDATE users SET username=?,password=? WHERE id=?', (old_user[1], old_user[2], old_user[0]))
                    else: db.execute('DELETE FROM users WHERE id=?', (created_id,))
            if old_bytes is None:
                with contextlib.suppress(FileNotFoundError): self.config_path.unlink()
            else:
                atomic_bytes(self.config_path, old_bytes)
            self.config = old_config
            if was_running:
                with contextlib.suppress(Exception): self.start_services()
            raise

    def setup_page(self):
        page = Path(__file__).with_name('setup.html').read_text(encoding='utf-8')
        values = {field: html.escape(self.config.get(key, ''), quote=True) for field, key in PROVIDER_FIELDS.items()}
        values.update(token=html.escape(self.setup_token or '', quote=True), account_hidden='' if self.needs_account() else 'hidden',
                      account_disabled='' if self.needs_account() else 'disabled',
                      setup_title='首次创建本机账号' if self.needs_account() else '模型设置（保留账号、密码和会话）')
        values['asr_input_selected'] = 'selected' if self.config.get('SHUYU_PROVIDER_ASR_ADAPTER') == 'input_audio' else ''
        for cap in ('text', 'vision', 'asr'):
            values[cap + '_checked'] = 'checked' if cap in self.config.get('SHUYU_PROVIDER_CAPABILITIES', '').split(',') else ''
        for key, value in values.items(): page = page.replace('{{' + key + '}}', value)
        return page

    def start_control(self):
        app = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def respond(self, status, text, content_type='text/html; charset=utf-8'):
                payload = text.encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', content_type); self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers(); self.wfile.write(payload)
            def host_ok(self): return self.headers.get('Host') == urllib.parse.urlsplit(app.control_origin).netloc
            def authorized(self): return secure_equal(self.headers.get('X-Shuyu-Nonce', ''), app.nonce)
            def do_GET(self):
                if not self.host_ok(): return self.respond(403, '请求主机不受信任。')
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path == '/status' and self.authorized():
                    return self.respond(200, json.dumps({'identity': app.identity}), 'application/json')
                token = urllib.parse.parse_qs(parsed.query).get('token', [''])[0]
                if parsed.path != '/' or not app.setup_token or not secure_equal(token, app.setup_token) or app.setup_complete:
                    return self.respond(403, '设置链接已失效，请重新打开设置。')
                try: self.respond(200, app.setup_page())
                except Exception: self.respond(500, '无法读取设置页，请检查应用文件和数据目录。')
            def do_POST(self):
                if not self.host_ok(): return self.respond(403, '请求主机不受信任。')
                if self.path == '/command':
                    if not self.authorized(): return self.respond(403, '实例身份不匹配。')
                    command = self.headers.get('X-Shuyu-Command')
                    if command == 'stop':
                        app.done.set(); return self.respond(200, '{}', 'application/json')
                    if command in ('open', 'setup'):
                        url = app.activate_setup() if command == 'setup' or not app.api else f'http://127.0.0.1:{app.port}/'
                        return self.respond(200, json.dumps({'url': url}), 'application/json')
                    return self.respond(400, '命令无效。')
                if self.path != '/setup': return self.respond(404, '页面不存在。')
                if self.headers.get('Origin') != app.control_origin:
                    return self.respond(403, '请求来源不受信任。')
                try:
                    length = int(self.headers.get('Content-Length', '-1'))
                    if not 0 < length <= MAX_FORM: return self.respond(413, '设置内容过长或缺少长度。')
                    if self.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded': return self.respond(415, '表单类型无效。')
                    self.connection.settimeout(5)
                    form = urllib.parse.parse_qs(self.rfile.read(length).decode('utf-8'), max_num_fields=32, keep_blank_values=True)
                except (ValueError, UnicodeError, OSError): return self.respond(400, '表单读取失败。')
                token = form.get('token', [''])[0]
                if not app.setup_token or not secure_equal(token, app.setup_token): return self.respond(403, '设置令牌无效。')
                if not app.submit_lock.acquire(blocking=False): return self.respond(409, '设置正在保存，请勿重复提交。')
                try:
                    if app.setup_complete: return self.respond(409, '设置已保存，请重新打开设置。')
                    with app.lifecycle_lock: app.apply_setup(form)
                    app.setup_complete = True
                    url = f'http://127.0.0.1:{app.port}/'
                    self.respond(200, f"<!doctype html><meta charset='utf-8'><p>设置已保存。</p><a href='{url}'>打开澍雨</a><p>关闭浏览器不会停止服务；请使用“停止澍雨”。</p>")
                    browser_open(url)
                except DesktopError as error:
                    self.respond(400, html.escape(str(error)))
                except Exception:
                    log_line(app.log_path, 'setup failed; original account and configuration restored')
                    self.respond(500, '设置未完成，已保留原账号与配置。请查看数据目录中的日志后重试。')
                finally: app.submit_lock.release()
        port = int(os.environ.get('SHUYU_SETUP_PORT', '0'))
        self.control = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.control.daemon_threads = True
        self.control_origin = f'http://127.0.0.1:{self.control.server_port}'
        threading.Thread(target=self.control.serve_forever, daemon=True).start()
        atomic_json(self.instance_path, {'port': self.control.server_port, 'nonce': self.nonce, 'identity': self.identity})

    def contact_existing(self, command):
        for _ in range(30):
            try:
                metadata = json.loads(self.instance_path.read_text(encoding='utf-8'))
                port, nonce = metadata['port'], metadata['nonce']
                if not isinstance(port, int) or not 1 <= port <= 65535 or not isinstance(nonce, str) or len(nonce) < 32 or metadata['identity'] != self.identity:
                    raise ValueError()
                base = f'http://127.0.0.1:{port}'
                request = urllib.request.Request(base + '/status', headers={'X-Shuyu-Nonce': nonce})
                with urllib.request.urlopen(request, timeout=.5) as response:
                    if json.load(response).get('identity') != self.identity: raise ValueError()
                request = urllib.request.Request(base + '/command', data=b'', headers={'X-Shuyu-Nonce': nonce, 'X-Shuyu-Command': command})
                with urllib.request.urlopen(request, timeout=2) as response: result = json.load(response)
                if result.get('url'): browser_open(result['url'])
                return 0
            except (OSError, ValueError, KeyError, TypeError): time.sleep(.1)
        raise DesktopError('同一数据目录已有实例，但身份验证失败。请检查 desktop.log，勿删除运行中的锁文件。')

    def run(self, setup=False, stop=False):
        self.prepare_data_dir()
        if not self.lock.acquire(): return self.contact_existing('stop' if stop else 'setup' if setup else 'open')
        try:
            if stop: return 0
            self._server_imports()
            self.seed_if_needed()
            self.config = self.config_values()
            self.first_account = self.needs_account()
            self.start_control()
            if setup or self.first_account or not self.config_path.exists():
                browser_open(self.activate_setup())
            else:
                self.start_services(); browser_open(f'http://127.0.0.1:{self.port}/')
            while not self.done.wait(.2):
                with self.lifecycle_lock:
                    if any(p and p.poll() is not None for p in (self.api, self.worker)):
                        log_line(self.log_path, 'API or worker exited unexpectedly; stopping owned services')
                        self.exit_code = 1; break
            return self.exit_code
        finally:
            with self.lifecycle_lock: self.stop_services()
            if self.control:
                self.control.shutdown(); self.control.server_close()
            with contextlib.suppress(FileNotFoundError): self.instance_path.unlink()
            self.lock.close()


def main():
    app = None
    try:
        app = DesktopApp()
        def stop_signal(signum, frame): app.done.set()
        signal.signal(signal.SIGTERM, stop_signal); signal.signal(signal.SIGINT, stop_signal)
        return app.run('--setup' in sys.argv or os.environ.get('SHUYU_SETUP') == '1', '--stop' in sys.argv)
    except Exception as error:
        message = '澍雨未能启动。请检查数据目录中的 desktop.log；保留原数据，不要删除数据库。'
        if app:
            log_line(app.log_path, str(error) if isinstance(error, DesktopError) else '启动失败，请检查目录权限、端口与应用文件。')
        print(str(error) if isinstance(error, DesktopError) else message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
