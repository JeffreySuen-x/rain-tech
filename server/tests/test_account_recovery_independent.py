"""Synthetic-only independent acceptance of local credential recovery."""
import tempfile
import unittest
from pathlib import Path
from server.app import create_app, connect, generate_password_hash
from server.account_recovery import recover_owner_access

class IndependentRecoveryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'db'
        self.app=create_app({'DB_PATH':str(self.path),'ASSET_ROOT':self.tmp.name+'/assets','PRODUCTION':False,'PUBLIC_ORIGIN':'http://localhost:6480'})
        self.db=connect(str(self.path));self.addCleanup(self.db.close)
        for uid in ('a','b'):self.db.execute('INSERT INTO users VALUES(?,?,?)',(uid,uid,generate_password_hash('old-password-123')))
        self.db.execute("INSERT INTO workspaces VALUES('w','a','synthetic')")
        self.db.execute("INSERT INTO threads VALUES('t','a','w','business')")
    def login(self,name,password):
        client=self.app.test_client();csrf=client.get('/api/v1/auth/csrf').json['csrfToken']
        response=client.post('/api/v1/auth/login',json={'username':name,'password':password},headers={'X-CSRF-Token':csrf})
        return client,response
    def business(self):
        result={}
        for (name,) in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            if name not in ('users','sessions'):result[name]=self.db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
        return result
    def test_login_csrf_session_revocation_and_owner_isolation(self):
        a,ar=self.login('a','old-password-123');b,br=self.login('b','old-password-123')
        self.assertEqual(ar.status_code,200);self.assertEqual(br.status_code,200)
        before=self.business();other=self.db.execute("SELECT * FROM users WHERE id='b'").fetchall()
        recover_owner_access(self.path,'w','a','new-password-123')
        self.assertEqual(self.business(),before);self.assertEqual(self.db.execute("SELECT * FROM users WHERE id='b'").fetchall(),other)
        self.assertEqual(a.get('/api/v1/auth/me').status_code,401)
        self.assertEqual(a.post('/api/v1/workspaces',json={'name':'forbidden'},headers={'X-CSRF-Token':ar.json['csrfToken']}).status_code,403)
        self.assertEqual(b.get('/api/v1/auth/me').status_code,200)
        self.assertEqual(b.get('/api/v1/threads/t').status_code,404)
        self.assertEqual(self.login('a','old-password-123')[1].status_code,401)
        fresh,response=self.login('a','new-password-123');self.assertEqual(response.status_code,200)
        self.assertEqual(fresh.get('/api/v1/threads/t').status_code,200)
        self.assertEqual(fresh.post('/api/v1/workspaces',json={'name':'no csrf'}).status_code,403)
    def test_missing_database_is_not_created(self):
        missing=Path(self.tmp.name)/'absent'
        with self.assertRaises(Exception):recover_owner_access(missing,'w','a','new-password-123')
        self.assertFalse(missing.exists())
    def test_cli_recovery_never_initializes_app(self):
        from unittest.mock import patch
        import io
        from server.app import main
        with patch('sys.argv',['app','recover-owner-access','--workspace','w','--expected-user-id','a','--password-stdin']),patch('sys.stdin',io.StringIO('new-password-123\n')),patch.dict('os.environ',{'SHUYU_DB':str(self.path)}),patch('server.app.create_app',side_effect=AssertionError('must not initialize')),patch('sys.stdout',io.StringIO()):
            main()
        self.assertEqual(self.login('a','new-password-123')[1].status_code,200)
