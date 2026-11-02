import contextlib
import json
import threading
import time
import unittest
from http.server import HTTPServer,BaseHTTPRequestHandler
from unittest.mock import patch
from server.tests import test_server
from server.app import run_once,connect,claim,encode,uid
from server import agent_runtime,agriculture

class AgentRuntimeTests(unittest.TestCase):
    setUp=test_server.ServerTests.setUp
    tearDown=test_server.ServerTests.tearDown
    login=test_server.ServerTests.login
    post=test_server.ServerTests.post
    submit=test_server.ServerTests.submit
    status=test_server.ServerTests.status
    @contextlib.contextmanager
    def http(self,responder):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(s):
                raw=s.rfile.read(int(s.headers['Content-Length']));captured.append((s.path,s.headers,raw))
                value=responder(captured)
                if value is None:s.connection.close();return
                s.send_response(200);s.end_headers();s.wfile.write(json.dumps(value).encode())
            def log_message(self,*a):pass
        http=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever);thread.start()
        self.app.config.update(PROVIDER_URL=f'http://127.0.0.1:{http.server_port}/v1',PROVIDER_KEY='local-only',PROVIDER_MODEL='local',PROVIDER_CAPABILITIES='text,vision,asr')
        try:yield captured
        finally:http.shutdown();thread.join();http.server_close()
    def modify_payload(self,turn,**values):
        payload=json.loads(self.db.execute('SELECT payload FROM turns WHERE id=?',(turn,)).fetchone()[0]);payload.update(values);self.db.execute('UPDATE turns SET payload=? WHERE id=?',(encode(payload),turn))
    def answer(self,text):return {'choices':[{'message':{'role':'assistant','content':text}}],'usage':{'prompt_tokens':12,'completion_tokens':3,'total_tokens':15}}
    def test_actual_dsh_multistep_and_receipts(self):
        def reply(calls):
            if len(calls)==1:return {'choices':[{'message':{'role':'assistant','content':'','tool_calls':[{'id':'read-1','type':'function','function':{'name':'list_work_items','arguments':'{}'}}]}}]}
            return self.answer('已读取真实待办，无完成动作')
        with self.http(reply) as calls:
            turn=self.submit();self.assertTrue(run_once(self.app));self.assertEqual(self.status(turn),'completed');self.assertEqual(len(calls),2)
            second=json.loads(calls[1][2]);self.assertTrue(any(m['role']=='tool' for m in second['messages']));self.assertTrue(any(t['function']['name']=='list_work_items' for t in json.loads(calls[0][2])['tools']))
            self.db.execute("UPDATE turns SET status='running',result=NULL,artifact_id=NULL,lease_until=0 WHERE id=?",(turn,));self.db.execute('DELETE FROM artifacts')
            run_once(self.app);self.assertEqual(self.status(turn),'completed');self.assertEqual(len(calls),2)
        rows=self.db.execute('SELECT * FROM agent_receipts WHERE turn_id=? ORDER BY rowid',(turn,)).fetchall()
        self.assertEqual([r['kind'] for r in rows],['model','tool','model']);self.assertTrue(all(r['state']=='sealed' for r in rows))
    def test_budget_prevents_second_model_dispatch(self):
        reply=lambda calls:{'choices':[{'message':{'role':'assistant','tool_calls':[{'id':'r','type':'function','function':{'name':'list_work_items','arguments':'{}'}}]}}]}
        with self.http(reply) as calls:
            turn=self.submit();self.modify_payload(turn,budget={'maxModelCalls':1});run_once(self.app);self.assertEqual(self.status(turn),'failed');self.assertEqual(len(calls),1)
            self.assertEqual(json.loads(self.db.execute('SELECT error FROM turns WHERE id=?',(turn,)).fetchone()[0])['code'],'budget_exceeded')
    def test_unknown_http_never_resends(self):
        with self.http(lambda calls:None) as calls:
            turn=self.submit();run_once(self.app);self.assertEqual(self.status(turn),'needs_review');run_once(self.app);self.assertEqual(len(calls),1)
    def test_heartbeat_and_cancel_late_http(self):
        ready=threading.Event();release=threading.Event()
        def reply(calls):ready.set();release.wait(4);return self.answer('late')
        with self.http(reply):
            turn=self.submit();worker=threading.Thread(target=run_once,args=(self.app,));worker.start();self.assertTrue(ready.wait(3))
            self.db.execute('UPDATE turns SET lease_until=? WHERE id=?',(time.time()+2,turn));time.sleep(.8)
            self.assertGreater(self.db.execute('SELECT lease_until FROM turns WHERE id=?',(turn,)).fetchone()[0],time.time()+60)
            self.post('/turns/'+turn+'/cancel',{'commandId':'cancel'},status=200);release.set();worker.join(5);self.assertFalse(worker.is_alive());self.assertEqual(self.status(turn),'cancelled');self.assertEqual(self.db.execute('SELECT count(*) FROM artifacts').fetchone()[0],0)
    def test_vision_and_asr_real_http_and_draft(self):
        import io,wave
        from server.tests.test_agriculture_domain import png
        self.app.config['ASSET_ROOT']=self.tmp.name+'/assets'
        # Routes capture their configured root at startup; use the domain upload seam
        # with that same root then set the runtime root to it.
        root=self.app.config['ASSET_ROOT']
        image=agriculture.upload(self.db,'a',self.w,{'commandId':'image','kind':'image'},png(),'photo.png',root)['asset']
        audio=io.BytesIO()
        with wave.open(audio,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\x00\x00'*800)
        voice=agriculture.upload(self.db,'a',self.w,{'commandId':'audio','kind':'audio'},audio.getvalue(),'recording.wav',root)['asset']
        def respond(calls):return {'text':'这是转写草稿'} if calls[-1][0].endswith('transcriptions') else self.answer('叶片照片分析，模型推断待现场确认')
        with self.http(respond) as calls:
            for asset,op,kind in [(image,'analyze','image_analysis'),(voice,'transcribe','audio_transcription')]:
                turn=self.post('/assets/'+asset['id']+'/'+op,{'commandId':op,'threadId':self.t},status=202)['turn']['id'];run_once(self.app)
                self.assertEqual(self.status(turn),'completed');result=self.a.get('/api/v1/turns/'+turn).json;self.assertEqual(result['turn']['processingKind'],kind);self.assertTrue(result['artifact']['body'])
            photo=json.loads(calls[0][2]);self.assertTrue(photo['messages'][-1]['content'][-1]['image_url']['url'].startswith('data:image/png;base64,'))
            self.assertEqual(calls[1][0],'/v1/audio/transcriptions');self.assertIn(b'filename="audio.wav"',calls[1][2]);self.assertIn(b'RIFF',calls[1][2])
            asset=agriculture.read(self.db,'a',voice['id'],'asset',self.w);self.assertEqual(asset['transcription']['text'],'这是转写草稿')
    def test_transitive_history_source_revoked_before_model(self):
        root=self.tmp.name+'/assets';self.app.config['ASSET_ROOT']=root
        doc=agriculture.upload(self.db,'a',self.w,{'commandId':'doc','kind':'document'},b'Original agricultural evidence','field.txt',root)
        first=self.submit(agricultureContext={'knowledgeIds':[doc['knowledge']['id']]});run_once(self.app,lambda p:'Source-derived answer')
        second=self.submit(includeHistory=True,agricultureContext={'knowledgeIds':[]})
        payload=json.loads(self.db.execute('SELECT payload FROM turns WHERE id=?',(second,)).fetchone()[0]);self.assertTrue(payload['historyAgricultureContexts'])
        self.a.delete('/api/v1/assets/'+doc['asset']['id'],headers={'X-CSRF-Token':self.at})
        with self.http(lambda c:self.answer('must not send')) as calls:
            run_once(self.app);self.assertEqual(self.status(second),'failed');self.assertEqual(calls,[])
    def test_client_cannot_forge_internal_runtime_fields(self):
        for values in ({'followUp':{'id':'fake'}},{'processingKind':'audio_transcription'},{'mediaAssetId':'x'},{'budget':{'maxModelCalls':1}}):
            self.post('/threads/'+self.t+'/turns',{'commandId':uid(),'prompt':'x',**values},status=400)
    def test_version_future_refused_atomic(self):
        self.db.execute('UPDATE agent_schema_meta SET version=9')
        with self.assertRaises(ValueError):agent_runtime.migrate(self.db)
        self.assertEqual(self.db.execute('SELECT version FROM agent_schema_meta').fetchone()[0],9)
    def test_recover_sealed_frontier_without_http(self):
        # A parent crash after final callback commit but before artifact seal.
        with self.http(lambda c:self.answer('sealed')) as calls:
            turn=self.submit();run_once(self.app);self.assertEqual(self.status(turn),'completed')
            self.db.execute("UPDATE turns SET status='running',result=NULL,artifact_id=NULL,lease_until=0 WHERE id=?",(turn,));self.db.execute('DELETE FROM artifacts')
            self.app.config.update(PROVIDER_KEY='',PROVIDER_URL='',PROVIDER_MODEL='')
            run_once(self.app);self.assertEqual(self.status(turn),'completed');self.assertEqual(len(calls),1)
    def test_capability_failure_before_dispatch(self):
        with self.http(lambda c:self.answer('unused')) as calls:
            turn=self.submit();self.modify_payload(turn,processingKind='audio_transcription');self.app.config['PROVIDER_CAPABILITIES']='text';run_once(self.app)
            self.assertEqual(self.status(turn),'failed');self.assertEqual(calls,[]);self.assertEqual(self.db.execute('SELECT count(*) FROM agent_receipts').fetchone()[0],0)

if __name__=='__main__':unittest.main()
