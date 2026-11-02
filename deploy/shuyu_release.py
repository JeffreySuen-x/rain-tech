#!/usr/bin/env python3
"""Local-only release operations. No service, firewall or provider invocation."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import secrets
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse

PROVIDERS = {'SHUYU_PROVIDER_' + x for x in 'CAPABILITIES THINKING ASR_ADAPTER VISION_MODEL ASR_MODEL URL KEY MODEL'.split()}
TABLES = set('users sessions workspaces threads memories turns artifacts commands agriculture_schema_meta agriculture_entities agriculture_device_events agriculture_live_demo agent_schema_meta agent_receipts agent_runs media_derivations'.split())
EXCLUDE = {'.git', '.runtime', '.venv', 'node_modules', '__pycache__', '.DS_Store', '.assets'}

class ReleaseError(ValueError):
    """Only static, non-sensitive diagnostics may use this exception."""

def require(ok, message):
    if not ok: raise ReleaseError(message)

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return {'size': path.stat().st_size, 'sha256': h.hexdigest()}

def safe_path(name):
    p = PurePosixPath(name)
    require(bool(name) and not p.is_absolute() and '..' not in p.parts and str(p) == name and '\\' not in name, 'unsafe archive path')
    return p

def regular(path):
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink rejected')
    require(path.is_file(), 'regular file required')

def new_dir(path):
    path = Path(path).absolute()
    require(not path.exists() and not path.is_symlink(), 'destination already exists')
    require(not any(p.is_symlink() for p in path.parents), 'symlink destination rejected')
    path.mkdir(mode=0o700)
    return path

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    path.chmod(0o600)

def files(root):
    out = {}
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(), 'symlink rejected')
        if p.is_file(): out[p.relative_to(root).as_posix()] = digest(p)
    return out

def db_report(path, assets):
    regular(path)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        require(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'database integrity failed')
        require(not db.execute('PRAGMA foreign_key_check').fetchall(), 'database foreign key failed')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        require(tables == TABLES, 'unknown database schema tables')
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
        require(hashlib.sha256(json.dumps(schema,separators=(',',':')).encode()).hexdigest() == '589e85b40a4fe95af43781b68ee90300212e1b16e89f77b37ad039e4fe65ce7e', 'unknown database schema definition')
        require(db.execute('SELECT version FROM agriculture_schema_meta').fetchall() == [(2,)], 'unknown agriculture schema')
        require(db.execute('SELECT version FROM agent_schema_meta').fetchall() == [(2,)], 'unknown agent schema')
        counts = {t: db.execute('SELECT count(*) FROM "' + t + '"').fetchone()[0] for t in sorted(tables)}
        refs = 0
        for (payload,) in db.execute("SELECT payload FROM agriculture_entities WHERE kind='asset'"):
            a = json.loads(payload); key = a.get('storageKey')
            require(isinstance(key, str) and re.fullmatch('[0-9a-f]{32}', key), 'invalid storage key')
            p = assets / key; regular(p)
            require(digest(p) == {'size': a.get('byteSize'), 'sha256': a.get('sha256')}, 'asset reference mismatch')
            refs += 1
        return {'table_counts': counts, 'asset_references': refs, 'database': digest(path)}

def archive(root, output, kind, extra):
    manifest = {'format': 1, 'kind': kind, 'files': files(root), **extra}
    write_json(root / 'MANIFEST.json', manifest)
    with tarfile.open(output, 'w:gz') as tar:
        for name in sorted(files(root)):
            tar.add(root / name, arcname=name, recursive=False)
    output.chmod(0o600)

def unpack(package, destination, kind=None):
    regular(package)
    with tarfile.open(package, 'r:gz') as tar:
        entries = tar.getmembers(); names = [e.name for e in entries]
        require(len(names) == len(set(names)), 'duplicate archive path')
        require('MANIFEST.json' in names, 'manifest missing')
        for e in entries:
            safe_path(e.name); require(e.isfile() and e.size <= 2**34, 'non-regular archive member')
        m = json.load(tar.extractfile('MANIFEST.json'))
        require(m.get('format') == 1 and m.get('kind') in ('code', 'private-data'), 'unknown manifest')
        if kind: require(m['kind'] == kind, 'wrong package kind')
        require(set(names) == set(m['files']) | {'MANIFEST.json'}, 'manifest file set mismatch')
        for e in entries:
            p = destination / e.name; p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tar.extractfile(e) as src, open(p, 'xb') as dst: shutil.copyfileobj(src, dst)
            p.chmod(0o600)
            if e.name != 'MANIFEST.json': require(digest(p) == m['files'][e.name], 'package hash mismatch')
    if m['kind'] == 'private-data': require(db_report(destination / 'database.sqlite3', destination / 'assets') == m['snapshot'], 'snapshot manifest mismatch')
    return m

def select_code(root):
    selected = []
    for top in ('server', 'runtime/dsh', 'web', 'deploy', 'qa'):
        base = root / top
        if not base.exists(): continue
        for p in base.rglob('*'):
            rel = p.relative_to(root); parts = rel.parts
            if any(x in EXCLUDE or x.startswith('.env') for x in parts): continue
            if p.is_dir(): continue
            regular(p)
            name = p.name
            if top == 'server' and not (name.endswith('.py') or name.startswith(('NOTICE', 'requirements', 'AGRICULTURE_SOURCES')) or name == 'README.md'): continue
            if top == 'runtime/dsh' and not (parts[2] in ('src', 'test') or name in ('package.json', 'package-lock.json', 'NOTICE.md')): continue
            if top == 'web' and not (parts[1] in ('src', 'public', 'tests', 'test') or name in ('package.json', 'package-lock.json', 'index.html', 'vite.config.js')): continue
            if top == 'deploy' and p.suffix not in ('.py', '.sh', '.md', '.txt', '.service', '.example'): continue
            if top == 'qa' and p.suffix not in ('.py', '.sh', '.md'): continue
            require(name not in ('local.json',) and not name.endswith(('.sqlite3', '.log')), 'private file selected')
            selected.append(p)
    # Runtime seed inputs are an explicit closure, never a docs/examples sweep.
    public_inputs = (
        'docs/knowledge/grape/environment-monitoring-reading.md',
        'docs/knowledge/grape/equipment-field-inspection.md',
        'docs/knowledge/grape/farm-record-review.md',
        'docs/knowledge/grape/irrigation-observation-log.md',
        'docs/knowledge/grape/leaf-abnormality-observation.md',
        'docs/knowledge/grape/vineyard-scouting-and-photos.md',
        'examples/student-demo/fixture.json',
        'examples/student-demo/images/ORIGIN.json',
        'examples/student-demo/images/grape-leaf.png',
        'examples/student-demo/images/vineyard.png',
        'LICENSE', 'THIRD_PARTY_NOTICES.md',
    )
    for relative in public_inputs:
        path = root / relative
        if path.exists() or path.is_symlink():
            regular(path)
            selected.append(path)
    require(root / 'server/app.py' in selected and root / 'web/package-lock.json' in selected, 'incomplete source tree')
    return selected

def pack(a):
    root = Path(a.source_root).absolute(); out = new_dir(a.output)
    selected = select_code(root); frozen = {str(p.relative_to(root)): digest(p) for p in selected}
    if a.baseline:
        baseline = json.loads(Path(a.baseline).read_text())
        for name, meta in baseline.items():
            # Baseline includes generated dist and source files outside release allowlist.
            p = root / name; regular(p); require(digest(p) == meta, 'source baseline drift')
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve(); code = tmp / 'code'; code.mkdir()
        for p in selected:
            dst = code / p.relative_to(root); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dst)
        require(all(digest(code / n) == meta for n, meta in frozen.items()), 'source copy drift')
        # Build only in an isolated frozen copy; no development dependencies enter release.
        subprocess.run(['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund', '--cache', str(tmp / 'npm-cache')], cwd=code / 'web', check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['npm', 'run', 'build'], cwd=code / 'web', check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(code / 'web/node_modules')
        require((code / 'web/dist/index.html').is_file(), 'web build missing')
        for public in (code / 'web/public').rglob('*'):
            if public.is_file():
                target = code / 'web/dist' / public.relative_to(code / 'web/public')
                require(target.is_file() and digest(target) == digest(public), 'public asset missing from fresh build')
        require(all(digest(root / n) == meta for n, meta in frozen.items()), 'source changed while building')
        archive(code, out / 'code.tar.gz', 'code', {'source_freeze': frozen, 'build': 'npm ci --ignore-scripts; npm run build', 'python': '3.11', 'node': '24'})
        capture_data(a, out / 'private-data.tar.gz')
    write_json(out / 'release.json', {'code': digest(out / 'code.tar.gz'), 'private_data': digest(out / 'private-data.tar.gz')})

def capture_data(a, output):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve(); data = tmp / 'data'; data.mkdir(); (data / 'assets').mkdir()
        dbpath = Path(a.db).absolute(); regular(dbpath)
        with sqlite3.connect(dbpath.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(data / 'database.sqlite3') as dst: src.backup(dst)
        assetroot = Path(a.assets).absolute()
        require(assetroot.is_dir() and not any(p.is_symlink() for p in (assetroot, *assetroot.parents)), 'invalid asset root')
        for p in assetroot.rglob('*'):
            require(not p.is_symlink(), 'asset symlink rejected')
            if p.is_file():
                dst = data / 'assets' / p.relative_to(assetroot); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, dst)
        report = db_report(data / 'database.sqlite3', data / 'assets')
        archive(data, output, 'private-data', {'snapshot': report})
        check = tmp / 'check'; check.mkdir(); unpack(output, check, 'private-data')

def backup(a):
    out = new_dir(a.output)
    capture_data(a, out / 'private-data.tar.gz')

def extract_code(a):
    out = new_dir(a.output)
    unpack(Path(a.package).absolute(), out, 'code')
    # Public code only: Nginx worker must be able to read static assets.
    for p in out.rglob('*'): p.chmod(0o755 if p.is_dir() else 0o644)
    out.chmod(0o755)

def verify(a):
    with tempfile.TemporaryDirectory() as tmp: unpack(Path(a.package).absolute(), Path(tmp).resolve())

def restore(a):
    out = new_dir(a.output)
    unpack(Path(a.package).absolute(), out, 'private-data')
    with sqlite3.connect(out / 'database.sqlite3') as db:
        audit = {'sessions_removed': db.execute('SELECT count(*) FROM sessions').fetchone()[0], 'pending_isolated': 0, 'followups_paused': 0, 'followup_turns_cancelled': 0, 'turns_before': [dict(zip(('id','status','generation','dispatched'), row)) for row in db.execute("SELECT id,status,generation,dispatched FROM turns WHERE status IN ('queued','running') ORDER BY id")], 'followups_before': []}
        # Follow-up authorization withdrawal uses existing cancellation + generation fencing.
        for ident, payload in db.execute("SELECT id,payload FROM agriculture_entities WHERE kind='follow_up'").fetchall():
            v = json.loads(payload)
            if v.get('enabled'):
                audit['followups_before'].append({'id':ident, **{k:v.get(k) for k in ('enabled','authorizationVersion','nextDueAt','remainingRuns')}})
                for tid in v.get('turnIds', []):
                    audit['followup_turns_cancelled'] += db.execute("UPDATE turns SET status='cancelled',generation=generation+1,lease_until=NULL WHERE id=? AND status IN ('queued','running')", (tid,)).rowcount
                v.update(enabled=False, status='disabled', nextDueAt=None, authorizationVersion=v.get('authorizationVersion', 0)+1)
                db.execute('UPDATE agriculture_entities SET payload=? WHERE id=?', (json.dumps(v, ensure_ascii=False), ident)); audit['followups_paused'] += 1
        audit['pending_isolated'] = db.execute("UPDATE turns SET status='needs_review',generation=generation+1,lease_until=NULL WHERE status IN ('queued','running')").rowcount
        db.execute('DELETE FROM sessions')
    write_json(out / 'restore-audit.json', {'worker_enabled': False, **audit})
    for p in out.rglob('*'): p.chmod(0o700 if p.is_dir() else 0o600)
    db_report(out / 'database.sqlite3', out / 'assets')

def status(a):
    p = Path(a.data).absolute()
    report = db_report(p / 'database.sqlite3', p / 'assets')
    with sqlite3.connect((p / 'database.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        report['pending'] = db.execute("SELECT count(*) FROM turns WHERE status IN ('queued','running')").fetchone()[0]
        report['enabled_followups'] = sum(bool(json.loads(r[0]).get('enabled')) for r in db.execute("SELECT payload FROM agriculture_entities WHERE kind='follow_up'"))
    if a.command == 'activation-check': require(report['pending'] == report['enabled_followups'] == 0 and (p / 'restore-audit.json').is_file(), 'worker activation blocked')
    print(json.dumps(report, sort_keys=True))

def node_directory(a):
    node = Path(a.node_bin_dir).absolute()
    require(re.fullmatch(r'/[A-Za-z0-9_./-]+', str(node)) and '..' not in node.parts, 'unsafe Node directory')
    require(subprocess.check_output([str(node / 'node'), '--version'], text=True).strip().startswith('v24.'), 'Node 24 required')
    return str(node)

def render(a):
    node_bin = node_directory(a)
    ip = ipaddress.ip_address(a.ip); cidrs = [ipaddress.ip_network(c, strict=False) for c in a.allow_cidr]
    require(cidrs and all(c.prefixlen > 0 for c in cidrs), 'source allowlist required; all-network forbidden')
    require(not ip.is_unspecified and not ip.is_multicast and 1024 <= a.port <= 65535, 'invalid server IP or port')
    code, data = Path(a.code).absolute(), Path(a.data).absolute()
    for p in (code, data, Path(a.output).absolute()): require(re.fullmatch(r'/[A-Za-z0-9_./-]+', str(p)) and '..' not in p.parts, 'unsafe deployment path')
    static = code / 'web/dist'
    for private in (data, Path(a.output).absolute(), Path(a.provider).absolute()):
        require(not private.resolve().is_relative_to(static.resolve()), 'private path inside static root forbidden')
    provider = Path(a.provider).absolute(); regular(provider)
    require(stat.S_IMODE(provider.stat().st_mode) == 0o600 and stat.S_IMODE(provider.parent.stat().st_mode) == 0o700, 'provider permissions must be 0700/0600')
    v = json.loads(provider.read_text())
    require(isinstance(v, dict) and not set(v) - PROVIDERS and all(isinstance(x,str) and not any(c in x for c in '\n\r\x00') for x in v.values()), 'invalid provider-only configuration')
    require(all(v.get('SHUYU_PROVIDER_' + k) for k in ('URL','KEY','MODEL')), 'provider configuration incomplete')
    url = urllib.parse.urlsplit(v['SHUYU_PROVIDER_URL'])
    require(url.scheme == 'https' and bool(url.hostname) and not any((url.username,url.password,url.query,url.fragment)), 'provider HTTPS URL required')
    url.port
    out = new_dir(a.output); origin = 'https://' + ('[' + str(ip) + ']' if ip.version == 6 else str(ip)) + ':' + str(a.port)
    env = {'SHUYU_ENV':'production','SHUYU_PUBLIC_ORIGIN':origin,'SHUYU_SECRET':secrets.token_hex(32),'SHUYU_DB':str(data / 'database.sqlite3'),'SHUYU_ASSET_ROOT':str(data / 'assets'), **v}
    # systemd EnvironmentFile quoted values: escape backslashes and double quotes, no shell interpolation.
    (out / 'shuyu.env').write_text(''.join(k+'="'+val.replace('\\','\\\\').replace('"','\\"')+'"\n' for k,val in env.items())); (out / 'shuyu.env').chmod(0o600)
    for role, command in [('api', f"{code}/server/.venv/bin/gunicorn --workers 1 --bind 127.0.0.1:6480 'server.app:create_app()'"), ('worker', f'{code}/server/.venv/bin/python -m server.app worker')]:
        (out / ('shuyu-'+role+'.service')).write_text(f'[Unit]\nDescription=Shuyu {role}\nAfter=network.target\n[Service]\nUser=shuyu\nGroup=shuyu\nWorkingDirectory={code}\nEnvironmentFile={out}/shuyu.env\nEnvironment="PATH={node_bin}:/usr/bin:/bin"\nExecStart={command}\nRestart=on-failure\nUMask=0077\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nReadWritePaths={data}\n[Install]\nWantedBy=multi-user.target\n')
    allow = ''.join('    allow '+str(c)+';\n' for c in cidrs)
    (out / 'nginx-http.conf').write_text("# Include once in BaoTa http context before nginx-server.conf.\nlog_format shuyu_private '$request_method $uri $status $request_time';\nlimit_req_zone $binary_remote_addr zone=shuyu_private_login:10m rate=5r/m;\nlimit_req_zone $binary_remote_addr zone=shuyu_private_api:10m rate=10r/s;\n")
    (out / 'nginx-server.conf').write_text(f'''# Include inside BaoTa http context; never replace global nginx.conf.
server {{
    listen {a.port} ssl;
    listen [::]:{a.port} ssl;
    server_name {ip};
    ssl_certificate {out}/ip.crt;
    ssl_certificate_key {out}/ip.key;
{allow}    deny all;
    root {code}/web/dist;
    client_max_body_size 22m;
    access_log /var/log/nginx/shuyu-private-access.log shuyu_private;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy same-origin always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
    location = /api/v1/auth/login {{ limit_req zone=shuyu_private_login burst=5 nodelay; limit_req_status 429; proxy_pass http://127.0.0.1:6480; proxy_set_header Host $http_host; proxy_set_header X-Forwarded-Proto https; proxy_read_timeout 30s; }}
    location ~ ^/api/v1/devices/[^/]+/events/?$ {{ deny all; }}
    location /api/ {{ limit_req zone=shuyu_private_api burst=30 nodelay; limit_req_status 429; proxy_read_timeout 30s; proxy_pass http://127.0.0.1:6480; proxy_set_header Host $http_host; proxy_set_header X-Forwarded-Proto https; }}
    location / {{ try_files $uri $uri/ /index.html; }}
    location ~ /\\. {{ deny all; }}
}}
''')
    (out / 'certificate-commands.txt').write_text(f'cd {out}\numask 077\nopenssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 30 -keyout ip.key -out ip.crt -subj /CN=Shuyu-private-demo -addext "subjectAltName=IP:{ip}"\nopenssl x509 -in ip.crt -noout -fingerprint -sha256\n# Independently compare SHA-256 fingerprint and explicitly trust on each demo device.\n# Worker remains STOPPED; no automatic installation, firewall change or service start.\n')
    write_json(out / 'render-audit.json', {'origin':origin,'worker_enabled':False,'allow_cidr':[str(c) for c in cidrs]})

def preflight(a):
    require(platform.system() == 'Linux', 'Linux required; no system changes performed')
    require(platform.machine() in ('x86_64','aarch64'), 'unvalidated CPU architecture')
    require(sys.version_info[:2] == (3,11), 'Python 3.11 required')
    node_directory(a)
    for exe in ('npm','openssl','systemctl','nginx'): require(shutil.which(exe), 'required executable missing: '+exe)
    require(shutil.disk_usage(a.directory).free >= a.minimum_free_bytes, 'insufficient disk space')
    require(os.access(a.directory, os.W_OK), 'directory not writable')
    for port in (6480, a.port):
        with socket.socket() as s: s.bind(('127.0.0.1',port))
    print(json.dumps({'os':'Linux','arch':platform.machine(),'python':'3.11','node':'24','dependency_install':'required on target: pip lock + npm ci; network or target offline artifacts required','worker_enabled':False}))


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    q = sub.add_parser('pack')
    for name in ('source-root','db','assets','output'): q.add_argument('--'+name, required=True)
    q.add_argument('--baseline')
    q = sub.add_parser('backup')
    for name in ('db','assets','output'): q.add_argument('--'+name, required=True)
    q = sub.add_parser('extract-code'); q.add_argument('--package',required=True); q.add_argument('--output',required=True)
    q = sub.add_parser('verify'); q.add_argument('--package',required=True)
    q = sub.add_parser('restore'); q.add_argument('--package',required=True); q.add_argument('--output',required=True)
    for cmd in ('status','activation-check'):
        q = sub.add_parser(cmd); q.add_argument('--data',required=True)
    q = sub.add_parser('render')
    for name in ('ip','code','data','provider','output'): q.add_argument('--'+name,required=True)
    q.add_argument('--node-bin-dir', required=True)
    q.add_argument('--allow-cidr',action='append',required=True); q.add_argument('--port',type=int,default=8443)
    q = sub.add_parser('preflight'); q.add_argument('--directory',required=True); q.add_argument('--port',type=int,default=8443); q.add_argument('--minimum-free-bytes',type=int,default=2*1024**3); q.add_argument('--node-bin-dir',required=True)
    a = p.parse_args()
    try: globals()[a.command.replace('-','_') if a.command != 'activation-check' else 'status'](a)
    except Exception as e:
        # No exception value: malformed provider inputs or subprocess errors may contain secrets.
        print('FAILED: '+(str(e) if isinstance(e, ReleaseError) else type(e).__name__)+'; output retained for local diagnosis, no services changed', file=sys.stderr); return 1
    return 0

if __name__ == '__main__': sys.exit(main())
