import contextlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('shuyu_desktop', ROOT / 'desktop/shuyu_desktop.py')
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)

class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='澍雨 测试 ')
        self.env = patch.dict(os.environ, {'SHUYU_DATA_DIR': self.tmp.name, 'SHUYU_BUNDLE_ROOT': str(ROOT), 'SHUYU_NO_BROWSER': '1', 'SHUYU_PORT': str(d.free_port()), 'SHUYU_SETUP_PORT':'0','SHUYU_SEED_DIR': str(Path(self.tmp.name)/'no-seed')})
        self.env.start(); self.app = d.DesktopApp(); self.app.prepare_data_dir();self.app._server_imports();self.app.seed_if_needed()
    def tearDown(self):
        self.app.stop_services()
        if self.app.control: self.app.control.shutdown(); self.app.control.server_close()
        self.app.lock.close(); self.env.stop(); self.tmp.cleanup()
    def user(self, owner='private', password='existing-hash'):
        with sqlite3.connect(self.app.db_path) as db: db.execute('INSERT INTO users VALUES(?,?,?)',(owner,'before',password))
    def form(self, **kwargs):
        result = dict(username=['student'],password=['  password  '],confirm=['  password  '],capability=['text'])
        result.update({k:[v] for k,v in kwargs.items()});return result
    def start_http(self):
        self.app.start_control();self.app.activate_setup()
    def request(self, form=None, origin=None, token=True, host=None, length=None):
        form = form or self.form()
        if token: form['token']=[self.app.setup_token]
        data=urllib.parse.urlencode(form,doseq=True).encode()
        headers={'Origin':origin or self.app.control_origin,'Content-Type':'application/x-www-form-urlencoded'}
        if host:headers['Host']=host
        if length:headers['Content-Length']=str(length)
        req=urllib.request.Request(self.app.control_origin+'/setup',data=data,headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=4) as response:return response.status,response.read().decode()
        except urllib.error.HTTPError as error:return error.code,error.read().decode()
    def test_invalid_provider_url_rejected_before_account_or_config_change(self):
        for url in ('https://example.invalid:bad/v1', 'https://example.invalid:65536/v1',
                    'https://example.invalid/v1?unsupported=query'):
            with self.subTest(url=url):
                with patch.object(self.app, 'start_services') as start:
                    with self.assertRaises(d.DesktopError):
                        self.app.apply_setup(self.form(providerUrl=url))
                    start.assert_not_called()
                self.assertFalse(self.app.config_path.exists())
                self.assertTrue(self.app.needs_account())
        self.app.validate_provider({'SHUYU_PROVIDER_URL': 'https://example.invalid:8443/v1'})

    def test_security_rejects_origin_host_token_size_without_changes(self):
        self.start_http()
        with patch.object(self.app,'apply_setup') as apply:
            self.assertEqual(self.request(origin='https://evil.invalid')[0],403)
            self.assertEqual(self.request(host='evil.invalid')[0],403)
            self.assertEqual(self.request(token=False)[0],403)
            self.assertEqual(self.request(form={'token':['无效令牌']}, token=False)[0],403)
            self.assertEqual(self.request(length=d.MAX_FORM+1)[0],413)
            self.assertFalse(apply.called)
    def test_single_submit_and_no_exception_leak(self):
        self.start_http(); entered=threading.Event();release=threading.Event();results=[]
        def apply(form):entered.set();release.wait(2)
        with patch.object(self.app,'apply_setup',side_effect=apply):
            t=threading.Thread(target=lambda:results.append(self.request()[0]));t.start();self.assertTrue(entered.wait(2))
            self.assertEqual(self.request()[0],409);release.set();t.join(3)
            self.assertEqual(results,[200]);self.assertEqual(self.request()[0],409)
        self.app.activate_setup()
        with patch.object(self.app,'apply_setup',side_effect=RuntimeError('SECRET_SENTINEL')):
            code,body=self.request();self.assertEqual(code,500);self.assertNotIn('SECRET_SENTINEL',body)
    def test_first_account_preserves_student_owner(self):
        self.user('student-demo-owner','!student-setup-required')
        with sqlite3.connect(self.app.db_path) as db:db.execute("INSERT INTO workspaces VALUES('fixture-workspace','student-demo-owner','合成园区')")
        with patch.object(self.app,'start_services'):
            self.app.apply_setup(self.form())
        from werkzeug.security import check_password_hash
        with sqlite3.connect(self.app.db_path) as db:row=db.execute('SELECT * FROM users').fetchone()
        with sqlite3.connect(self.app.db_path) as db:self.assertEqual(db.execute("SELECT owner FROM workspaces WHERE id='fixture-workspace'").fetchone()[0],'student-demo-owner')
        self.assertEqual(row[:2],('student-demo-owner','student'));self.assertTrue(check_password_hash(row[2],'  password  '))
    def test_reconfigure_keeps_private_account_session_secret_and_key(self):
        self.user(); self.app.config={'SHUYU_SECRET':'s'*64,'SHUYU_PROVIDER_URL':'https://example.invalid/v1','SHUYU_PROVIDER_MODEL':'local-stub','SHUYU_PROVIDER_KEY':'SENTINEL'}
        with sqlite3.connect(self.app.db_path) as db:db.execute("INSERT INTO sessions VALUES('session','private','csrf',9999999999)")
        with patch.object(self.app,'start_services'):self.app.apply_setup(self.form(providerModel='new'))
        self.assertEqual(self.app.config['SHUYU_SECRET'],'s'*64);self.assertEqual(self.app.config['SHUYU_PROVIDER_KEY'],'SENTINEL')
        with sqlite3.connect(self.app.db_path) as db:self.assertEqual(db.execute('SELECT username,password FROM users').fetchone(),('before','existing-hash'));self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],1)
    def test_failed_service_start_rolls_back_account_and_config(self):
        self.user('student-demo-owner','!student-setup-required')
        with patch.object(self.app,'start_services',side_effect=RuntimeError('sentinel')):
            with self.assertRaises(RuntimeError):self.app.apply_setup(self.form())
        self.assertFalse(self.app.config_path.exists())
        with sqlite3.connect(self.app.db_path) as db:self.assertEqual(db.execute('SELECT username,password FROM users').fetchone(),('before','!student-setup-required'))
    def test_atomic_file_failure_keeps_old_bytes(self):
        self.app.config_path.write_bytes(b'original')
        with patch.object(d.os,'replace',side_effect=OSError('disk')):
            with self.assertRaises(OSError):d.atomic_json(self.app.config_path,{'new':'value'})
        self.assertEqual(self.app.config_path.read_bytes(),b'original');self.assertFalse(list(self.app.data.glob('*.tmp')))
    def test_corrupt_or_unknown_config_rejected(self):
        for value in ('{}', '{', '{"UNTRUSTED":"value"}', '{"SHUYU_SECRET":"a","SHUYU_SECRET":"b"}'):
            self.app.config_path.write_text(value)
            with self.assertRaises(d.DesktopError):self.app.config_values()
    def test_runtime_paths_and_no_inherited_credentials(self):
        self.app.config={'SHUYU_STATIC_DIR':'old','SHUYU_PUBLIC_ORIGIN':'old','SHUYU_SECRET':'s'*64}
        with patch.dict(os.environ,{'SHUYU_PROVIDER_KEY':'SHOULD_NOT_LEAK'}):env=self.app.child_env()
        self.assertEqual(env['SHUYU_STATIC_DIR'],str(ROOT/'web/dist'));self.assertEqual(env['SHUYU_PUBLIC_ORIGIN'],f'http://127.0.0.1:{self.app.port}');self.assertNotIn('SHUYU_PROVIDER_KEY',env)
    def test_unrelated_port_is_rejected(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));sock.listen();self.app.port=sock.getsockname()[1]
            with self.assertRaises(d.DesktopError):self.app.start_services()
        self.assertIsNone(self.app.api);self.assertIsNone(self.app.worker)
    def test_lock_and_nonce_identity(self):
        self.assertTrue(self.app.lock.acquire());other=d.InstanceLock(self.app.data/'desktop.lock');self.assertFalse(other.acquire())
        self.start_http();second=d.DesktopApp()
        self.assertEqual(second.contact_existing('setup'),0)
        with patch.object(d,'browser_open') as opened:self.assertEqual(second.contact_existing('open'),0);self.assertTrue(opened.called)
        metadata=json.loads(self.app.instance_path.read_text());metadata['nonce']='x'*43;d.atomic_json(self.app.instance_path,metadata)
        with patch.object(d.time,'sleep'):
            with self.assertRaises(d.DesktopError):second.contact_existing('stop')
        self.assertFalse(self.app.done.is_set())
    def test_missing_database_with_config_is_not_overwritten(self):
        self.app.db_path.unlink();self.app.config_path.write_text('{}')
        with self.assertRaises(d.DesktopError):self.app.seed_if_needed()
        self.assertFalse(self.app.db_path.exists())
    def test_seed_manifest_and_assets_are_verified_before_copy(self):
        self.user('student-demo-owner','!student-setup-required')
        seed=self.app.data/'seed-input';seed.mkdir();(seed/'assets').mkdir()
        with sqlite3.connect(self.app.db_path) as src,sqlite3.connect(seed/'shuyu.sqlite3') as dst:src.backup(dst)
        d.atomic_json(seed/'manifest.json',dict(fixtureVersion='student-demo-v1',owner='student-demo-owner',assets=[]))
        self.app.db_path.unlink();self.app.asset_root.rmdir()
        (seed/'assets/orphan').write_bytes(b'not in manifest')
        with patch.dict(os.environ,{'SHUYU_SEED_DIR':str(seed)}):
            with self.assertRaises(d.DesktopError):self.app.seed_if_needed()
            self.assertFalse(self.app.db_path.exists());self.assertFalse(self.app.asset_root.exists())
            (seed/'assets/orphan').unlink();self.app.seed_if_needed()
        self.assertTrue(self.app.needs_account());self.assertEqual(len(self.app.validate_database(self.app.db_path)),1)
    def test_explicit_model_capabilities_and_clear_key(self):
        self.user();self.app.config={'SHUYU_PROVIDER_KEY':'SENTINEL','SHUYU_PROVIDER_URL':'https://example.invalid','SHUYU_PROVIDER_MODEL':'stub'}
        form=self.form(clearKey='yes',visionModel='vision',asrModel='asr');form['capability']=['vision','asr']
        with patch.object(self.app,'start_services'):self.app.apply_setup(form)
        self.assertEqual(self.app.config['SHUYU_PROVIDER_KEY'],'');self.assertEqual(self.app.config['SHUYU_PROVIDER_CAPABILITIES'],'asr,vision')
    def test_worker_exit_stops_api_and_returns_failure(self):
        self.user();self.app.write_config({})
        owned=[]
        def start():
            self.app.api=subprocess.Popen([sys.executable,'-c','import time;time.sleep(90)'],start_new_session=os.name!='nt')
            self.app.worker=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.1)'],start_new_session=os.name!='nt')
            owned.extend([self.app.api,self.app.worker])
        with patch.object(self.app,'start_services',side_effect=start):self.assertEqual(self.app.run(),1)
        self.assertTrue(all(p.poll() is not None for p in owned));self.assertFalse(self.app.instance_path.exists())
    def test_real_first_login_reconfigure_and_stop_without_model(self):
        import http.cookiejar
        process=subprocess.Popen([sys.executable,str(ROOT/'desktop/shuyu_desktop.py')],env=os.environ.copy(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if self.app.instance_path.exists():break
                if process.poll() is not None:self.fail('launcher exited before setup')
                time.sleep(.05)
            metadata=json.loads(self.app.instance_path.read_text());origin=f"http://127.0.0.1:{metadata['port']}"
            def command(name):
                req=urllib.request.Request(origin+'/command',data=b'',headers={'X-Shuyu-Nonce':metadata['nonce'],'X-Shuyu-Command':name})
                with urllib.request.urlopen(req,timeout=3) as response:return json.load(response)
            def submit(url,fields):
                fields['token']=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['token'][0]
                req=urllib.request.Request(origin+'/setup',data=urllib.parse.urlencode(fields).encode(),headers={'Origin':origin})
                with urllib.request.urlopen(req,timeout=45) as response:self.assertEqual(response.status,200)
            submit(command('setup')['url'],dict(username='student',password='password123',confirm='password123'))
            api=f'http://127.0.0.1:{self.app.port}'
            opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            with opener.open(api+'/api/v1/auth/csrf') as response:csrf=json.load(response)['csrfToken']
            request=urllib.request.Request(api+'/api/v1/auth/login',data=json.dumps(dict(username='student',password='password123')).encode(),headers={'Origin':api,'Content-Type':'application/json','X-CSRF-Token':csrf})
            with opener.open(request) as response:self.assertEqual(json.load(response)['user']['username'],'student')
            submit(command('setup')['url'],{})
            with opener.open(api+'/api/v1/auth/me') as response:self.assertEqual(json.load(response)['user']['username'],'student')
            command('stop');self.assertEqual(process.wait(timeout=10),0)
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)
    @unittest.skipIf(os.name=='nt','POSIX process group test; Windows Job/taskkill requires real Windows')
    def test_stop_reaps_owned_process_group(self):
        child_pid=self.app.data/'child.pid'
        code="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)']);open(sys.argv[1],'w').write(str(p.pid));time.sleep(90)"
        self.app.api=subprocess.Popen([sys.executable,'-c',code,str(child_pid)],start_new_session=True)
        for _ in range(100):
            if child_pid.exists():break
            time.sleep(.02)
        pid=int(child_pid.read_text());process=self.app.api;self.app.stop_services();self.assertIsNotNone(process.returncode)
        for _ in range(50):
            try:os.kill(pid,0)
            except ProcessLookupError:break
            time.sleep(.02)
        else:self.fail('grandchild survived stop')

if __name__=='__main__':unittest.main()

class DataPathTests(unittest.TestCase):
    def test_link_and_parent_preserve_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve(); target = base / 'shared'; target.mkdir(mode=0o755)
            marker = target / 'existing'; marker.write_text('keep')
            link = base / 'configured'; link.symlink_to(target, target_is_directory=True)
            for configured in (link, link / 'nested'):
                with patch.dict(os.environ, {'SHUYU_DATA_DIR': str(configured)}):
                    with self.assertRaises(d.DesktopError):
                        d.DesktopApp().prepare_data_dir()
                self.assertEqual(target.stat().st_mode & 0o777, 0o755)
                self.assertEqual(marker.read_text(), 'keep')
            self.assertFalse((target / 'nested').exists())
