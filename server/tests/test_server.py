import contextlib
import json
import tempfile
import threading
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
from server.app import create_app,connect,uid,generate_password_hash,run_once,claim,transaction,provider

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.app=create_app({'DB_PATH':self.tmp.name+'/db','PRODUCTION':False,'PUBLIC_ORIGIN':'http://localhost:6480'})
        self.db=connect(self.app.config['DB_PATH'])
        for name in ('a','b'): self.db.execute('INSERT INTO users VALUES(?,?,?)',(name,name,generate_password_hash('long-password-123')))
        self.a,self.at=self.login('a'); self.b,self.bt=self.login('b')
        self.w=self.post('/workspaces',{'name':'Test'})['workspace']['id']; self.t=self.post('/workspaces/'+self.w+'/threads',{'title':'Decision'})['thread']['id']
    def tearDown(self): self.db.close(); self.tmp.cleanup()
    def login(self,name):
        c=self.app.test_client(); token=c.get('/api/v1/auth/csrf').json['csrfToken']; r=c.post('/api/v1/auth/login',json={'username':name,'password':'long-password-123'},headers={'X-CSRF-Token':token}); self.assertEqual(r.status_code,200); return c,r.json['csrfToken']
    def post(self,path,data,client=None,token=None,status=201):
        r=(client or self.a).post('/api/v1'+path,json=data,headers={'X-CSRF-Token':token or self.at}); self.assertEqual(r.status_code,status,r.json); return r.json
    def submit(self,**kw): return self.post('/threads/'+self.t+'/turns',dict(commandId=uid(),prompt='What next?',**kw),status=202)['turn']['id']
    def status(self,id): return self.a.get('/api/v1/turns/'+id).json['turn']['status']
    def expire(self): self.db.execute('UPDATE turns SET lease_until=0')
    def test_headers_and_invalid_input(self):
        r=self.a.get('/api/v1/auth/me'); self.assertEqual(r.headers['Cache-Control'],'no-store'); self.assertEqual(r.headers['X-Content-Type-Options'],'nosniff')
        r=self.a.post('/api/v1/workspaces',json={'name':'x'},headers={'X-CSRF-Token':'中文'}); self.assertEqual(r.status_code,403)
        self.post('/workspaces/'+self.w+'/memories',{'commandId':'bad','content':'x','sourceTurnId':[]},status=400)
    def test_thread_busy_and_payload_budget(self):
        id=self.submit()
        r=self.a.post('/api/v1/threads/'+self.t+'/turns',json={'commandId':'other','prompt':'x'},headers={'X-CSRF-Token':self.at}); self.assertEqual(r.status_code,409); self.assertEqual(r.json['error']['code'],'thread_busy')
        self.post('/turns/'+id+'/cancel',{'commandId':'stop'},status=200)
        memories=[]
        for i in range(7): memories.append(self.post('/workspaces/'+self.w+'/memories',{'commandId':'m'+str(i),'content':'a'*16000})['memory']['id'])
        r=self.a.post('/api/v1/threads/'+self.t+'/turns',json={'commandId':'large','prompt':'x','memoryIds':memories},headers={'X-CSRF-Token':self.at}); self.assertEqual(r.status_code,413); self.assertEqual(r.json['error']['code'],'too_large')
    def test_password_preserves_whitespace(self):
        self.db.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(' padded-password '),'a'))
        c=self.app.test_client(); token=c.get('/api/v1/auth/csrf').json['csrfToken']
        r=c.post('/api/v1/auth/login',json={'username':' a ','password':' padded-password '},headers={'X-CSRF-Token':token})
        self.assertEqual(r.status_code,200)
    def test_csrf_sessions_origin(self):
        self.assertEqual(self.a.post('/api/v1/workspaces',json={'name':'x'}).status_code,403)
        self.assertEqual(self.a.post('/api/v1/workspaces',json={'name':'x'},headers={'X-CSRF-Token':self.at,'Origin':'https://evil'}).status_code,403)
        self.assertEqual(self.app.test_client().get('/api/v1/auth/me').status_code,401)
        self.post('/auth/logout',{},status=204); self.assertEqual(self.a.get('/api/v1/auth/me').status_code,401)
    def test_ownership_and_idempotency(self):
        payload={'commandId':'same','prompt':'question'}; endpoint='/threads/'+self.t+'/turns'
        first=self.post(endpoint,payload,status=202); self.assertEqual(first,self.post(endpoint,payload,status=202))
        self.post(endpoint,dict(payload,prompt='changed'),status=409)
        turn=first['turn']['id']; run_once(self.app,lambda p:'answer'); art=self.a.get('/api/v1/turns/'+turn).json['artifact']['id']
        memory=self.post('/workspaces/'+self.w+'/memories',{'commandId':'m','content':'fact'})['memory']['id']
        for path in ('/workspaces/'+self.w+'/threads','/threads/'+self.t,'/turns/'+turn,'/artifacts/'+art): self.assertEqual(self.b.get('/api/v1'+path).status_code,404)
        for path,data in ((endpoint,{'commandId':'b','prompt':'x'}),('/turns/'+turn+'/cancel',{'commandId':'c'}),('/workspaces/'+self.w+'/memories',{'commandId':'m','content':'x'})):
            self.post(path,data,self.b,self.bt,status=404)
        self.assertEqual(self.b.delete('/api/v1/memories/'+memory,headers={'X-CSRF-Token':self.bt}).status_code,404)
    def test_queued_restart_and_single_claim(self):
        id=self.submit(); other=connect(self.app.config['DB_PATH']); a=claim(self.db); self.assertEqual(a['id'],id); self.assertIsNone(claim(other)); other.close()
        self.expire(); self.assertTrue(run_once(self.app,lambda p:'recovered')); self.assertEqual(self.status(id),'completed')
    def test_cancel_late_and_repeat(self):
        id=self.submit()
        def call(p):
            self.post('/turns/'+id+'/cancel',{'commandId':'stop'},status=200); return 'late'
        run_once(self.app,call); self.assertEqual(self.status(id),'cancelled'); self.post('/turns/'+id+'/cancel',{'commandId':'stop'},status=200)
        self.assertEqual(self.db.execute('SELECT count(*) FROM artifacts').fetchone()[0],0)
    def test_dispatched_crash_never_retries(self):
        id=self.submit()
        def crash(): raise SystemExit('crash')
        with self.assertRaises(SystemExit): run_once(self.app,lambda p:'unused',after_dispatch=crash)
        self.expire(); calls=[]; run_once(self.app,lambda p:calls.append(p)); self.assertEqual(calls,[]); self.assertEqual(self.status(id),'needs_review')
    def test_sealed_restart_publishes_without_dispatch(self):
        id=self.submit()
        def crash(): raise SystemExit('crash')
        with self.assertRaises(SystemExit): run_once(self.app,lambda p:'sealed',after_seal=crash)
        self.expire(); calls=[]; run_once(self.app,lambda p:calls.append(p)); self.assertEqual(calls,[]); self.assertEqual(self.status(id),'completed')
    def test_memory_revocation_and_scope(self):
        mid=self.post('/workspaces/'+self.w+'/memories',{'commandId':'m','content':'secret'})['memory']['id']; id=self.submit(memoryIds=[mid])
        def call(p):
            self.a.delete('/api/v1/memories/'+mid,headers={'X-CSRF-Token':self.at}); return 'late secret'
        run_once(self.app,call); self.assertEqual(self.status(id),'failed')
        self.post('/threads/'+self.t+'/turns',{'commandId':'new','prompt':'x','memoryIds':[mid]},status=404)
        self.assertEqual(self.db.execute('SELECT content FROM memories WHERE id=?',(mid,)).fetchone()[0],'')
    def test_history_memory_revocation_before_dispatch(self):
        mid=self.post('/workspaces/'+self.w+'/memories',{'commandId':'m','content':'secret'})['memory']['id']
        first=self.submit(memoryIds=[mid]); run_once(self.app,lambda p:'first result')
        second=self.submit(includeHistory=True); payload=json.loads(self.db.execute('SELECT payload FROM turns WHERE id=?',(second,)).fetchone()[0])
        self.assertEqual(payload['history'][0]['id'],first)
        self.assertEqual(payload['memories'],[])
        self.assertEqual(payload['historyMemoryIds'],[{'id':mid}])
        run_once(self.app,lambda p:'second result')
        second=self.submit(includeHistory=True)
        payload=json.loads(self.db.execute('SELECT payload FROM turns WHERE id=?',(second,)).fetchone()[0])
        self.assertEqual(len(payload['history']),2)
        self.assertEqual(payload['historyMemoryIds'],[{'id':mid}])
        self.a.delete('/api/v1/memories/'+mid,headers={'X-CSRF-Token':self.at})
        calls=[]; run_once(self.app,lambda p:calls.append(p)); self.assertEqual(calls,[]); self.assertEqual(self.status(second),'failed')
        third=self.submit(includeHistory=True); payload=json.loads(self.db.execute('SELECT payload FROM turns WHERE id=?',(third,)).fetchone()[0]); self.assertEqual(payload['history'],[])
        self.post('/workspaces/'+self.w+'/memories',{'commandId':'m','content':'secret'},status=409)
    def test_foreign_keys(self):
        with self.assertRaises(Exception): self.db.execute('INSERT INTO threads VALUES(?,?,?,?)',(uid(),'a','missing','x'))
    def test_missing_provider_visible(self):
        id=self.submit(); run_once(self.app); self.assertEqual(self.status(id),'failed')
    def test_production_configuration(self):
        with self.assertRaises(ValueError): create_app({'DB_PATH':self.tmp.name+'/prod','PRODUCTION':True,'PUBLIC_ORIGIN':'http://example.com','SECRET_KEY':'x'*40})
    def test_real_http_provider_transport(self):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(s):
                captured.append((s.path,s.headers['Authorization'],json.loads(s.rfile.read(int(s.headers['Content-Length'])))))
                s.send_response(200); s.end_headers(); s.wfile.write(json.dumps({'choices':[{'message':{'content':'HTTP synthetic result'}}]}).encode())
            def log_message(self,*a): pass
        http=HTTPServer(('127.0.0.1',0),Handler); thread=threading.Thread(target=http.serve_forever); thread.start()
        try:
            self.app.config.update(PROVIDER_URL='http://127.0.0.1:'+str(http.server_port)+'/v1',PROVIDER_KEY='synthetic-test-key',PROVIDER_MODEL='synthetic')
            id=self.submit(background='source'); run_once(self.app); self.assertEqual(self.status(id),'completed'); self.assertEqual(captured[0][0],'/v1/chat/completions'); self.assertEqual(captured[0][1],'Bearer synthetic-test-key')
        finally: http.shutdown(); thread.join(); http.server_close()

if __name__=='__main__': unittest.main()
