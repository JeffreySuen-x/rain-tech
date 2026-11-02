import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from server.app import create_app
from server import agriculture as ag
from server.demo_restore import restore, SOURCE_WORKSPACE, SOURCE_USER
from server.local_config import load_config

class LocalConfigTests(unittest.TestCase):
    def test_shuyu_environment_mapping_and_production_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = {
                'SHUYU_ENV': 'production', 'SHUYU_DB': str(Path(tmp) / 'isolated.sqlite3'),
                'SHUYU_ASSET_ROOT': str(Path(tmp) / 'assets'), 'SHUYU_STATIC_DIR': str(Path(tmp) / 'web'),
                'SHUYU_PUBLIC_ORIGIN': 'https://example.invalid', 'SHUYU_SECRET': 's' * 64,
                'SHUYU_PROVIDER_URL': 'https://model.invalid/v1', 'SHUYU_PROVIDER_KEY': 'synthetic-only',
                'SHUYU_PROVIDER_MODEL': 'text-stub', 'SHUYU_PROVIDER_CAPABILITIES': 'text,vision,asr',
                'SHUYU_PROVIDER_THINKING': 'disabled', 'SHUYU_PROVIDER_ASR_ADAPTER': 'input_audio',
                'SHUYU_PROVIDER_VISION_MODEL': 'vision-stub', 'SHUYU_PROVIDER_ASR_MODEL': 'audio-stub',
            }
            Path(values['SHUYU_STATIC_DIR']).mkdir()
            with patch.dict(os.environ, values, clear=True):
                app = create_app()
            self.assertTrue(app.config['PRODUCTION'])
            for key, value in values.items():
                if key == 'SHUYU_ENV': continue
                field = {'SHUYU_DB': 'DB_PATH', 'SHUYU_SECRET': 'SECRET_KEY'}.get(key, key.removeprefix('SHUYU_'))
                self.assertEqual(app.config[field], value)
            for invalid in ({'SHUYU_SECRET': 'short'}, {'SHUYU_PUBLIC_ORIGIN': 'http://example.invalid'}):
                with self.subTest(invalid=next(iter(invalid))), patch.dict(os.environ, {**values, **invalid}, clear=True):
                    with self.assertRaises(ValueError): create_app()

    def test_shuyu_cookie_login_logout_and_csrf(self):
        from server.app import connect, generate_password_hash
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            app = create_app({'DB_PATH': str(Path(tmp) / 'auth.sqlite3'), 'PRODUCTION': True,
                              'PUBLIC_ORIGIN': 'https://example.invalid', 'SECRET_KEY': 's' * 64})
            db = connect(app.config['DB_PATH'])
            try: db.execute('INSERT INTO users VALUES(?,?,?)', ('test-user', 'test-user', generate_password_hash('synthetic-password')))
            finally: db.close()
            client = app.test_client()
            origin = 'https://example.invalid'
            response = client.get('/api/v1/auth/csrf', base_url=origin)
            cookie = response.headers['Set-Cookie']
            self.assertTrue(cookie.startswith('shuyu_session='))
            for flag in ('Secure', 'HttpOnly', 'SameSite=Lax'): self.assertIn(flag, cookie)
            headers = {'Origin': origin, 'X-CSRF-Token': response.json['csrfToken']}
            response = client.post('/api/v1/auth/login', base_url=origin, headers=headers,
                                   json={'username': 'test-user', 'password': 'synthetic-password'})
            self.assertEqual(response.status_code, 200)
            headers['X-CSRF-Token'] = response.json['csrfToken']
            self.assertEqual(client.get('/api/v1/auth/me', base_url=origin).json['user']['username'], 'test-user')
            self.assertEqual(client.post('/api/v1/auth/logout', base_url=origin, json={}).status_code, 403)
            self.assertEqual(client.post('/api/v1/auth/logout', base_url=origin, headers={**headers, 'Origin': 'https://other.invalid'}, json={}).status_code, 403)
            response = client.post('/api/v1/auth/logout', base_url=origin, headers=headers, json={})
            self.assertEqual(response.status_code, 204)
            self.assertIn('shuyu_session=;', response.headers['Set-Cookie'])
            self.assertIn('Max-Age=0', response.headers['Set-Cookie'])
            self.assertEqual(client.get('/api/v1/auth/me', base_url=origin).status_code, 401)

    def test_private_config_env_precedence_and_safe_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve()/'local.json'; path.write_text(json.dumps({'SHUYU_PROVIDER_KEY':'sentinel-private','SHUYU_ENV':'development'})); path.chmod(0o600)
            env={'SHUYU_PROVIDER_KEY':'explicit'}; load_config(path,env)
            self.assertEqual(env['SHUYU_PROVIDER_KEY'],'explicit'); self.assertEqual(env['SHUYU_ENV'],'development')
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError,'^Invalid or insecure local configuration$'): load_config(path,{})
            path.chmod(0o600); path.write_text('{"INVALID":"sentinel-private"}')
            with self.assertRaises(ValueError): load_config(path,{})
            path.unlink(); os.mkfifo(path,0o600)
            with self.assertRaises(ValueError): load_config(path,{})
            path.unlink(); path.symlink_to(Path(tmp)/'missing')
            with self.assertRaises(ValueError): load_config(path,{})

class DemoRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve()
        self.source=self.root/'source.sqlite'; self.target=self.root/'target.sqlite'
        self.assets=self.root/'source-assets'; self.dest=self.root/'target-assets'; self.proto=self.root/'prototype'
        self.assets.mkdir(mode=0o700); self.proto.mkdir()
        for name in ('vineyard.png','grape-leaf.png'): (self.proto/name).write_bytes(b'fake-image-'+name.encode())
        for path in (self.source,self.target): create_app({'DB_PATH':str(path),'ASSET_ROOT':str(self.assets),'PRODUCTION':False,'TESTING':True})
        with sqlite3.connect(self.source) as db:
            db.row_factory=sqlite3.Row
            db.execute("INSERT INTO users VALUES('old',?,'never-import')", (SOURCE_USER,))
            db.execute('INSERT INTO workspaces VALUES(?,?,?)',(SOURCE_WORKSPACE,'old','QA'))
            db.execute('INSERT INTO threads VALUES(?,?,?,?)',('thread','old',SOURCE_WORKSPACE,'QA'))
            db.execute('INSERT INTO turns(id,owner,workspace_id,thread_id,status,payload,created_at) VALUES(?,?,?,?,?,?,?)',('turn','old',SOURCE_WORKSPACE,'thread','completed','{}',1))
            ag.insert(db,'old',SOURCE_WORKSPACE,'plot',{'name':'测试地块','crop':'葡萄','stage':None})
            ag.insert(db,'old',SOURCE_WORKSPACE,'follow_up',{'enabled':True,'status':'completed','remainingRuns':0,'nextDueAt':None,'authorizationVersion':1,'authorizedAt':1})
            raw=b'original synthetic document'; key='a'*32; (self.assets/key).write_bytes(raw)
            self.asset=ag.insert(db,'old',SOURCE_WORKSPACE,'asset',{'storageKey':key,'sha256':hashlib.sha256(raw).hexdigest(),'byteSize':len(raw),'kind':'document','name':'qa.txt','status':'ready'})['id']
        with sqlite3.connect(self.target) as db:
            db.execute("INSERT INTO users VALUES('new','target','private-password')")
            db.execute("INSERT INTO workspaces VALUES('existing','new','existing')")
            db.execute("INSERT INTO threads VALUES('existing-thread','new','existing','existing')")
            db.execute("INSERT INTO turns(id,owner,workspace_id,thread_id,status,payload,created_at,error) VALUES('failed','new','existing','existing-thread','failed','{}',1,'keep me')")
    def tearDown(self): self.tmp.cleanup()
    def run_restore(self,**extra): return restore(self.source,self.assets,self.target,self.dest,'target',self.proto,**extra)
    def test_dry_run_apply_repeat_preserve_history_and_no_external_work(self):
        before=self.target.read_bytes(); self.assertFalse(self.run_restore()['noop']); self.assertEqual(before,self.target.read_bytes()); self.assertFalse(self.dest.exists())
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            result=self.run_restore(apply=True)
        self.assertTrue(result['applied'])
        with sqlite3.connect(self.target) as db:
            db.row_factory=sqlite3.Row
            self.assertEqual(db.execute("SELECT error FROM turns WHERE id='failed'").fetchone()[0],'keep me')
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            self.assertFalse(db.execute("SELECT 1 FROM turns WHERE status IN ('queued','running')").fetchone())
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchone())
            follow=json.loads(db.execute("SELECT payload FROM agriculture_entities WHERE kind='follow_up'").fetchone()[0]); self.assertFalse(follow['enabled']); self.assertEqual(follow['authorizationVersion'],0)
            self.assertNotIn('authorizedAt',follow)
            prototype_images=[json.loads(row[0]) for row in db.execute("SELECT payload FROM agriculture_entities WHERE kind='asset'") if json.loads(row[0]).get('name','').startswith('模拟原型图片 · ')]
            self.assertEqual(len(prototype_images),2)
            for image in prototype_images:
                self.assertEqual(image['status'],'stored')
                self.assertNotIn('analysis',image)
                self.assertNotIn('processingTurnId',image)
            old_asset=json.loads(db.execute('SELECT payload FROM agriculture_entities WHERE id=?',(self.asset,)).fetchone()[0])
            self.assertEqual(old_asset['status'],'ready')
            for row in db.execute("SELECT payload FROM agriculture_entities WHERE kind='asset'"):
                p=json.loads(row[0]); raw=(self.dest/p['storageKey']).read_bytes(); self.assertEqual(hashlib.sha256(raw).hexdigest(),p['sha256']); self.assertEqual((self.dest/p['storageKey']).stat().st_mode&0o777,0o600)
            db.execute("UPDATE workspaces SET name='my later edit' WHERE id=?",(SOURCE_WORKSPACE,)); db.commit()
            count=db.execute('SELECT count(*) FROM agriculture_entities').fetchone()[0]
        self.assertTrue(self.run_restore(apply=True)['noop'])
        with sqlite3.connect(self.target) as db:
            self.assertEqual(db.execute('SELECT name FROM workspaces WHERE id=?',(SOURCE_WORKSPACE,)).fetchone()[0],'my later edit'); self.assertEqual(db.execute('SELECT count(*) FROM agriculture_entities').fetchone()[0],count)
    def test_conflict_hash_owner_and_rollback(self):
        (self.assets/('a'*32)).write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError,'hash'): self.run_restore(apply=True)
        (self.assets/('a'*32)).write_bytes(b'original synthetic document')
        with sqlite3.connect(self.source) as db:
            db.execute("INSERT INTO users VALUES('intruder','other','x')"); db.execute("UPDATE agriculture_entities SET owner='intruder' WHERE id=?",(self.asset,))
        with self.assertRaisesRegex(ValueError,'Cross-owner'): self.run_restore()
        with sqlite3.connect(self.source) as db: db.execute("UPDATE agriculture_entities SET owner='old' WHERE id=?",(self.asset,))
        with patch('server.demo_restore.supplement',side_effect=ValueError('injected failure')):
            with self.assertRaisesRegex(ValueError,'injected'): self.run_restore(apply=True)
        self.assertEqual(list(self.dest.iterdir()),[])
        with sqlite3.connect(self.target) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM workspaces').fetchone()[0],1)
            db.execute('INSERT INTO workspaces VALUES(?,?,?)',(SOURCE_WORKSPACE,'new','collision'))
        with self.assertRaisesRegex(ValueError,'collision'): self.run_restore(apply=True)
