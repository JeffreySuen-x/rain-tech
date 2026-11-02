"""Independent acceptance, isolated DB/assets and loopback HTTP provider only."""
import concurrent.futures
import io
import json
import os
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch
from server import agriculture as a
from server.app import connect, create_app, generate_password_hash, run_once, enqueue_turn
from server.tests import test_server as base_server
from server.tests import test_agent_runtime as base_runtime

class IndependentAgricultureTests(unittest.TestCase):
    login=base_server.ServerTests.login
    post=base_server.ServerTests.post
    submit=base_server.ServerTests.submit
    status=base_server.ServerTests.status
    http=base_runtime.AgentRuntimeTests.http
    answer=base_runtime.AgentRuntimeTests.answer
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='shuyu-independent-')
        self.app=create_app({'DB_PATH':self.tmp.name+'/db','ASSET_ROOT':self.tmp.name+'/assets','PRODUCTION':False,'PUBLIC_ORIGIN':'http://localhost:6480','PROVIDER_URL':'','PROVIDER_KEY':'','PROVIDER_MODEL':''})
        self.db=connect(self.app.config['DB_PATH'])
        for who in ('a','b'):
            self.db.execute('INSERT INTO users VALUES(?,?,?)',(who,who,generate_password_hash('long-password-123')))
        self.a,self.at=self.login('a');self.b,self.bt=self.login('b')
        self.w=self.post('/workspaces',{'name':'Independent garden'})['workspace']['id']
        self.t=self.post('/workspaces/'+self.w+'/threads',{'title':'Independent thread'})['thread']['id']
    def tearDown(self):
        self.db.close();self.tmp.cleanup()
    def command(self,**kw):return {'commandId':uuid.uuid4().hex,**kw}
    def upload(self,kind='document',raw=b'independent source\nsoil inspection',name='source.md'):
        result=self.a.post('/api/v1/workspaces/'+self.w+'/assets',data={**self.command(kind=kind),'file':(io.BytesIO(raw),name)},headers={'X-CSRF-Token':self.at})
        self.assertEqual(result.status_code,201,result.json)
        return result.json
    def task(self):return self.post('/workspaces/'+self.w+'/work-items',self.command(title='Inspect soil'))['workItem']
    def test_http_owner_csrf_origin_token_scope_and_safe_download(self):
        plot=self.post('/workspaces/'+self.w+'/plots',self.command(name='P'))['plot']
        device=self.post('/workspaces/'+self.w+'/devices',self.command(plotId=plot['id'],name='sensor',kind='sensor'))
        did=device['device']['id'];token=device['ingestToken'];path='/api/v1/devices/'+did+'/events'
        event=self.command(sourceEventId='one',observedAt=time.time(),source='device',readings=[{'metric':'humidity','value':70,'unit':'percent'}])
        anonymous=self.app.test_client()
        self.assertEqual(anonymous.post(path,json=event,headers={'Authorization':'Bearer '+token}).status_code,201)
        self.assertEqual(anonymous.post(path,json=self.command(**{k:v for k,v in event.items() if k!='commandId'}),headers={'Authorization':'Bearer '+token,'Origin':'https://evil.invalid'}).status_code,403)
        self.assertEqual(anonymous.get('/api/v1/devices/'+did+'/readings',headers={'Authorization':'Bearer '+token}).status_code,401)
        self.assertEqual(anonymous.post('/api/v1/workspaces/'+self.w+'/plots',json=self.command(name='bad'),headers={'Authorization':'Bearer '+token}).status_code,403)
        self.assertEqual(self.a.post(path,json=event).status_code,403)
        self.assertEqual(self.b.post(path,json=event,headers={'X-CSRF-Token':self.bt}).status_code,404)
        uploaded=self.upload();task=self.task();report=self.post('/workspaces/'+self.w+'/reports',self.command())['report']
        for target in ['/workspaces/'+self.w+'/agriculture','/knowledge/'+uploaded['knowledge']['id'],'/assets/'+uploaded['asset']['id']+'/content','/reports/'+report['id'],'/devices/'+did+'/readings']:
            self.assertEqual(self.b.get('/api/v1'+target).status_code,404,target)
        for target,data in [('/work-items/'+task['id']+'/complete',self.command(note='forged')),('/knowledge/'+uploaded['knowledge']['id']+'/learning',self.command(answer='forged'))]:
            self.post(target,data,self.b,self.bt,status=404)
        download=self.a.get('/api/v1/assets/'+uploaded['asset']['id']+'/content')
        self.assertEqual(download.status_code,200)
        self.assertEqual(download.headers['Cache-Control'],'no-store')
        self.assertEqual(download.headers['X-Content-Type-Options'],'nosniff')
        download.close()

    def test_real_http_publication_revoked_while_inflight(self):
        uploaded=self.upload();ready=threading.Event();release=threading.Event()
        def respond(calls):ready.set();release.wait(5);return self.answer('private source answer')
        with self.http(respond) as calls:
            tid=self.submit(agricultureContext={'knowledgeIds':[uploaded['knowledge']['id']]})
            worker=threading.Thread(target=run_once,args=(self.app,));worker.start()
            self.assertTrue(ready.wait(4))
            self.assertEqual(self.a.delete('/api/v1/assets/'+uploaded['asset']['id'],headers={'X-CSRF-Token':self.at}).status_code,204)
            release.set();worker.join(6)
            self.assertFalse(worker.is_alive())
            self.assertEqual(self.status(tid),'failed')
            self.assertEqual(self.db.execute('SELECT count(*) FROM artifacts WHERE turn_id=?',(tid,)).fetchone()[0],0)
            self.assertEqual(len(calls),1)
            self.assertEqual(json.loads(self.db.execute('SELECT error FROM turns WHERE id=?',(tid,)).fetchone()[0])['code'],'asset_revoked')
            run_once(self.app);self.assertEqual(len(calls),1)

    def test_real_connections_concurrent_complete_and_command_conflict(self):
        task=self.task();command=self.command(note='independent actual completion')
        def complete(_):
            db=connect(self.app.config['DB_PATH'])
            try:return a.complete_item(db,'a',task['id'],command)
            finally:db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            result=list(pool.map(complete,range(24)))
        self.assertEqual(len({r['record']['id'] for r in result}),1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM agriculture_entities WHERE kind='activity_record'").fetchone()[0],1)
        with self.assertRaises(a.AgricultureError) as caught:a.complete_item(self.db,'a',task['id'],{**command,'note':'changed'})
        self.assertEqual(caught.exception.status,409)

    def test_followup_real_enqueue_restart_finite_and_revoke(self):
        task=self.task()
        settings=self.command(threadId=self.t,enabled=True,nextDueAt=time.time()-1,maxRuns=2,intervalSeconds=60,maxModelCalls=1)
        follow=self.post('/work-items/'+task['id']+'/follow-up',settings,status=200)['followUp']
        at=time.time()
        self.assertEqual(a.due_followups(self.db,at,enqueue_turn),1)
        restart=connect(self.app.config['DB_PATH'])
        try:self.assertEqual(a.due_followups(restart,at,enqueue_turn),0)
        finally:restart.close()
        stored=a.read(self.db,'a',follow['id'],'follow_up')
        self.assertEqual(stored['remainingRuns'],1)
        turn=stored['turnIds'][0]
        payload=json.loads(self.db.execute('SELECT payload FROM turns WHERE id=?',(turn,)).fetchone()[0])
        self.assertEqual(payload['budget']['maxModelCalls'],1)
        with self.http(lambda c:self.answer('无新数据，不能确认改善。')) as calls:
            self.assertTrue(run_once(self.app));self.assertEqual(self.status(turn),'completed');self.assertEqual(len(calls),1)
            a.due_followups(self.db,at+61,enqueue_turn)
            stored=a.read(self.db,'a',follow['id'],'follow_up')
            self.assertEqual(stored['remainingRuns'],0)
            second=stored['turnIds'][1]
            self.post('/work-items/'+task['id']+'/follow-up',self.command(threadId=self.t,enabled=False),status=200)
            self.assertEqual(self.status(second),'cancelled')
            self.assertFalse(run_once(self.app));self.assertEqual(len(calls),1)
        reports=a.entities(self.db,'a',self.w,'report')
        self.assertEqual(len(reports),1);self.assertEqual(reports[0]['generationType'],'agent_followup')
        self.assertEqual(a.read(self.db,'a',task['id'],'work_item')['status'],'open')

    def test_contract_followup_eight_model_calls_budget_is_executable(self):
        task=self.task()
        follow=self.post('/work-items/'+task['id']+'/follow-up',self.command(threadId=self.t,enabled=True,nextDueAt=time.time()-1,maxRuns=1,maxModelCalls=8),status=200)['followUp']
        with self.http(lambda c:self.answer('无新观察。')) as calls:
            self.assertTrue(run_once(self.app))
            stored=a.read(self.db,'a',follow['id'],'follow_up')
            self.assertEqual(len(stored['turnIds']),1)
            self.assertEqual(self.status(stored['turnIds'][0]),'completed')
            self.assertEqual(len(calls),1)

    def test_persisted_deadline_does_not_reset_on_worker_restart(self):
        turn=self.submit()
        self.db.execute('INSERT INTO agent_runs VALUES(?,?)',(turn,time.time()-181))
        with self.http(lambda c:self.answer('must not send')) as calls:
            restarted=create_app({**self.app.config,'DB_PATH':self.app.config['DB_PATH']})
            self.assertTrue(run_once(restarted))
            self.assertEqual(self.status(turn),'failed')
            self.assertEqual(json.loads(self.db.execute('SELECT error FROM turns WHERE id=?',(turn,)).fetchone()[0])['code'],'budget_exceeded')
            self.assertEqual(calls,[])
            self.assertEqual(self.db.execute('SELECT count(*) FROM agent_receipts WHERE turn_id=?',(turn,)).fetchone()[0],0)

    def test_jpeg_webp_real_http_bytes_and_input_audio_adapter(self):
        import base64,wave
        from PIL import Image
        images=[]
        for fmt,mime in [('JPEG','image/jpeg'),('WEBP','image/webp')]:
            image=io.BytesIO();Image.new('RGB',(4,4),'green').save(image,fmt)
            raw=image.getvalue();images.append((raw,mime,self.upload('image',raw,'phone.'+fmt.lower())['asset']))
        audio=io.BytesIO()
        with wave.open(audio,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\x00\x00'*80)
        raw_audio=audio.getvalue();voice=self.upload('audio',raw_audio,'voice.wav')['asset']
        with self.http(lambda c:self.answer('受控媒体结果')) as calls:
            for raw,mime,asset in images:
                tid=self.post('/assets/'+asset['id']+'/analyze',self.command(threadId=self.t),status=202)['turn']['id']
                run_once(self.app);self.assertEqual(self.status(tid),'completed')
                body=json.loads(calls[-1][2]);url=body['messages'][-1]['content'][-1]['image_url']['url']
                self.assertEqual(url.split(',')[0],'data:image/png;base64')
                from server.agriculture_materials import outbound_image
                self.assertEqual(base64.b64decode(url.split(',')[1]),outbound_image(raw)[0])
                self.assertNotIn(self.tmp.name,calls[-1][2].decode())
            self.app.config['PROVIDER_ASR_ADAPTER']='input_audio'
            tid=self.post('/assets/'+voice['id']+'/transcribe',self.command(threadId=self.t),status=202)['turn']['id']
            run_once(self.app);self.assertEqual(self.status(tid),'completed')
            block=json.loads(calls[-1][2])['messages'][-1]['content'][0]['input_audio']
            self.assertEqual(block['format'],'wav');self.assertEqual(base64.b64decode(block['data']),raw_audio)
            self.assertTrue(a.read(self.db,'a',voice['id'],'asset')['transcription']['draft'])

if __name__=='__main__':unittest.main(verbosity=2)
