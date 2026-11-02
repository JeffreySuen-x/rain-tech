"""Synthetic sentinels only: inspect real HTTP bytes and actual DSH callbacks."""
import base64
import io
import json
import os
import threading
import unittest
from http.server import HTTPServer,BaseHTTPRequestHandler
from unittest.mock import patch
from PIL import Image
from server.tests import test_agent_runtime
from server.app import run_once,encode
from server import agriculture,agent_runtime,agent_provider

class PrivacyTests(unittest.TestCase):
    setUp=test_agent_runtime.AgentRuntimeTests.setUp
    tearDown=test_agent_runtime.AgentRuntimeTests.tearDown
    login=test_agent_runtime.AgentRuntimeTests.login
    post=test_agent_runtime.AgentRuntimeTests.post
    submit=test_agent_runtime.AgentRuntimeTests.submit
    status=test_agent_runtime.AgentRuntimeTests.status
    http=test_agent_runtime.AgentRuntimeTests.http
    answer=test_agent_runtime.AgentRuntimeTests.answer
    def test_explicit_sources_history_and_document_mapping_real_dsh(self):
        root=self.tmp.name+'/assets';self.app.config['ASSET_ROOT']=root
        selected=agriculture.upload(self.db,'a',self.w,{'commandId':'yes','kind':'document'},b'SELECTED_SENTINEL','yes.txt',root)
        agriculture.upload(self.db,'a',self.w,{'commandId':'no','kind':'document'},b'UNSELECTED_SENTINEL','no.txt',root)
        foreign=self.post('/workspaces',{'name':'Other'})['workspace']['id']
        agriculture.upload(self.db,'a',foreign,{'commandId':'other','kind':'document'},b'OTHER_WORKSPACE_SENTINEL','other.txt',root)
        self.post('/workspaces/'+self.w+'/memories',{'commandId':'memory','content':'UNSELECTED_MEMORY_SENTINEL'})
        first=self.post('/threads/'+self.t+'/turns',{'commandId':'history','prompt':'HISTORY_SENTINEL'},status=202)['turn']['id'];run_once(self.app,lambda p:'HISTORY_ANSWER_SENTINEL')
        with self.http(lambda c:self.answer('done')) as calls:
            second=self.submit(agricultureContext={'assetIds':[selected['asset']['id']]});run_once(self.app)
            self.assertEqual(self.status(second),'completed')
            raw=calls[0][2]
            self.assertIn(b'SELECTED_SENTINEL',raw)
            for value in (b'UNSELECTED_SENTINEL',b'OTHER_WORKSPACE_SENTINEL',b'UNSELECTED_MEMORY_SENTINEL',b'HISTORY_SENTINEL',b'HISTORY_ANSWER_SENTINEL',b'workspaceId',b'historyMemoryIds'):self.assertNotIn(value,raw)
            third=self.submit(includeHistory=True);run_once(self.app)
            self.assertIn(b'HISTORY_SENTINEL',calls[1][2])
    def test_projection_and_child_environment(self):
        payload={'prompt':'allowed','owner':'OWNER_SENTINEL','agricultureContext':{'workspaceId':'WORKSPACE_SENTINEL','sources':[]},'history':[{'prompt':'OLD_SENTINEL'}],'memories':[],'followUp':{'id':'INTERNAL_SENTINEL'}}
        self.assertNotIn('SENTINEL',encode(agent_runtime.model_input_view(payload)))
        tool=agent_runtime.model_tool_view({'data':{'devices':[{'id':'ref','owner':'OWNER_SENTINEL','credentialHash':'KEY_SENTINEL','storageKey':'PATH_SENTINEL'}]}})
        self.assertNotIn('SENTINEL',encode(tool));self.assertIn('ref',encode(tool))
        selected=agent_runtime.model_tool_view({'data':{'asset':{'analysis':{'text':'selected analysis'},'credentialHash':'secret'},'devices':[{'latest':{'humidity':{'value':40,'unit':'percent'}},'thresholds':{'humidity':{'max':80}}}]}})
        self.assertEqual(selected['data']['asset']['analysis']['text'],'selected analysis')
        self.assertEqual(selected['data']['devices'][0]['latest']['humidity']['value'],40)
        self.assertNotIn('credentialHash',encode(selected))
        with patch.dict(os.environ,{'CLOUD_CONNECTION_STRING':'CREDENTIAL_SENTINEL','HTTP_PROXY':'PROXY_SENTINEL','MiXeD_credential':'CREDENTIAL_SENTINEL'}):
            env=agent_runtime.child_environment();self.assertFalse(any('SENTINEL' in v for v in env.values()))
        for value in [True,1,'true',None]:
            if value is True:continue
            self.post('/threads/'+self.t+'/turns',{'commandId':str(value),'prompt':'x','includeHistory':value},status=400)
    def test_redirect_all_statuses_never_forward(self):
        hits=[]
        class Sink(BaseHTTPRequestHandler):
            def do_POST(s):hits.append(1);s.send_response(200);s.end_headers()
            def log_message(self,*a):pass
        sink=HTTPServer(('127.0.0.1',0),Sink);t=threading.Thread(target=sink.serve_forever);t.start()
        class Redirect(BaseHTTPRequestHandler):
            def do_POST(s):s.rfile.read(int(s.headers['Content-Length']));s.send_response(int(s.path.split('/')[1]));s.send_header('Location',f'http://127.0.0.1:{sink.server_port}/sink');s.end_headers()
            def log_message(self,*a):pass
        source=HTTPServer(('127.0.0.1',0),Redirect);u=threading.Thread(target=source.serve_forever);u.start()
        try:
            for status in (301,302,303,307,308):
                config={'PROVIDER_URL':f'http://127.0.0.1:{source.server_port}/{status}','PROVIDER_KEY':'KEY_SENTINEL','PROVIDER_MODEL':'test','PRODUCTION':False}
                with self.assertRaises(Exception):agent_provider.complete(config,{'messages':[{'role':'user','content':'BODY_SENTINEL'}]})
            self.assertEqual(hits,[])
        finally:source.shutdown();sink.shutdown();u.join();t.join();source.server_close();sink.server_close()
        for url in ['http://127.0.0.1/v1','https://user:password@example.com','https://example.com?key=x','https://example.com#x','file:///tmp/test']:
            with self.assertRaises(agent_provider.ProviderFailure):agent_provider.configured({'PROVIDER_URL':url,'PROVIDER_KEY':'x','PROVIDER_MODEL':'x','PRODUCTION':True})
    def test_exif_orientation_removed_in_real_vision_http(self):
        root=self.tmp.name+'/assets';self.app.config['ASSET_ROOT']=root
        self.db.execute('UPDATE workspaces SET name=? WHERE id=?',('MEDIA_GARDEN_SENTINEL',self.w))
        image=Image.new('RGB',(3,5),'red');exif=Image.Exif();exif[274]=6;exif[270]='EXIF_GPS_SENTINEL';buf=io.BytesIO();image.save(buf,format='JPEG',exif=exif,icc_profile=b'ICC_SENTINEL')
        raw=buf.getvalue();asset=agriculture.upload(self.db,'a',self.w,{'commandId':'image','kind':'image'},raw,'PRIVATE_FILENAME_SENTINEL.jpg',root)['asset']
        with self.http(lambda c:self.answer('done')) as calls:
            turn=self.post('/assets/'+asset['id']+'/analyze',{'commandId':'analyze','threadId':self.t},status=202)['turn']['id'];run_once(self.app)
            self.assertEqual(self.status(turn),'completed')
            request=json.loads(calls[0][2]);content=request['messages'][-1]['content'];binary=base64.b64decode(content[-1]['image_url']['url'].split(',')[1])
            self.assertNotIn(b'EXIF_GPS_SENTINEL',binary);self.assertNotIn(b'ICC_SENTINEL',binary)
            with Image.open(io.BytesIO(binary)) as clean:self.assertEqual(clean.size,(5,3));self.assertFalse(clean.getexif());self.assertFalse(clean.info)
            self.assertNotIn(b'MEDIA_GARDEN_SENTINEL',calls[0][2]);self.assertNotIn(b'plotId',calls[0][2])
            self.assertFalse(request.get('tools'));self.assertNotIn(b'PRIVATE_FILENAME_SENTINEL',calls[0][2])
            original,_=agriculture.asset_content(self.db,'a',asset['id'],__import__('pathlib').Path(root));self.assertEqual(original.read_bytes(),raw)
            self.assertIsNotNone(self.db.execute('SELECT provenance FROM media_derivations WHERE turn_id=?',(turn,)).fetchone())
    def test_followup_scope_and_media_tool_denial(self):
        item=agriculture.create_entity(self.db,'a',self.w,'work_item',{'commandId':'target','title':'TARGET_ITEM_SENTINEL'})['workItem']
        agriculture.create_entity(self.db,'a',self.w,'work_item',{'commandId':'other-task','title':'UNRELATED_ITEM_SENTINEL'})
        snapshot=agriculture.snapshot_context(self.db,'a',self.w,{})
        snapshot['workItemId']=item['id']
        payload={'agricultureContext':snapshot}
        turn={'owner':'a','workspace_id':self.w,'payload':payload}
        self.assertNotIn('UNRELATED_ITEM_SENTINEL',encode(agriculture.execute_tool(self.db,turn,'list_work_items',{},'operation')))
        self.assertEqual(agriculture.execute_tool(self.db,turn,'read_observations',{},'operation')['data']['devices'],[])
        payload['processingKind']='audio_transcription'
        with self.assertRaises(agriculture.AgricultureError):agriculture.execute_tool(self.db,turn,'list_work_items',{},'operation')
    def test_asr_no_sources_history_and_actual_child_env(self):
        import wave,subprocess
        root=self.tmp.name+'/assets';self.app.config['ASSET_ROOT']=root
        agriculture.upload(self.db,'a',self.w,{'commandId':'doc-asr','kind':'document'},b'ASR_UNSELECTED_SENTINEL','private.txt',root)
        first=self.post('/threads/'+self.t+'/turns',{'commandId':'history-asr','prompt':'ASR_HISTORY_SENTINEL'},status=202)['turn']['id'];run_once(self.app,lambda p:'ASR_HISTORY_SENTINEL')
        audio=io.BytesIO()
        with wave.open(audio,'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000);out.writeframes(b'\0\0'*100)
        asset=agriculture.upload(self.db,'a',self.w,{'commandId':'asr','kind':'audio'},audio.getvalue(),'private.wav',root)['asset']
        original=subprocess.Popen;environments=[]
        def launch(*args,**kwargs):environments.append(kwargs['env']);return original(*args,**kwargs)
        with self.http(lambda c:{'text':'draft'}) as calls,patch.dict(os.environ,{'CLOUD_CONNECTION_STRING':'CHILD_CREDENTIAL_SENTINEL'}),patch('server.agent_runtime.subprocess.Popen',side_effect=launch):
            turn=self.post('/assets/'+asset['id']+'/transcribe',{'commandId':'transcribe','threadId':self.t},status=202)['turn']['id'];run_once(self.app)
            self.assertEqual(self.status(turn),'completed');self.assertEqual(len(calls),1)
            self.assertNotIn(b'ASR_UNSELECTED_SENTINEL',calls[0][2]);self.assertNotIn(b'ASR_HISTORY_SENTINEL',calls[0][2])
            self.assertTrue(environments);self.assertNotIn('CLOUD_CONNECTION_STRING',environments[0])

    def test_asset_private_permissions_before_first_write(self):
        from pathlib import Path
        import stat
        root=Path(self.tmp.name)/'existing-public-root';root.mkdir(mode=0o755)
        os.chmod(root,0o755)
        original=os.fdopen;checked=[]
        def open_private(fd,*args,**kwargs):
            # Runs before the returned stream can write the first content byte.
            checked.append(stat.S_IMODE(os.fstat(fd).st_mode))
            self.assertEqual(checked[-1],0o600)
            self.assertEqual(os.fstat(fd).st_size,0)
            return original(fd,*args,**kwargs)
        previous=os.umask(0)
        try:
            with patch('server.agriculture.os.fdopen',side_effect=open_private):
                key=agriculture.save_file(root,b'PRIVATE_CONTENT')
        finally:os.umask(previous)
        self.assertEqual(checked,[0o600]);self.assertEqual((root/key).read_bytes(),b'PRIVATE_CONTENT')
        self.assertEqual(stat.S_IMODE((root/key).stat().st_mode),0o600)
        self.assertEqual(stat.S_IMODE(root.stat().st_mode),0o755)

    def test_runtime_schema_v1_upgrade_preserves_derivations_and_future_rejected(self):
        turn=self.submit()
        self.db.execute('INSERT INTO media_derivations VALUES(?,?)',(turn,'{"kept":true}'))
        self.db.execute('UPDATE agent_schema_meta SET version=1')
        agent_runtime.migrate(self.db)
        self.assertEqual(self.db.execute('SELECT version FROM agent_schema_meta').fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT provenance FROM media_derivations WHERE turn_id=?',(turn,)).fetchone()[0],'{"kept":true}')
        agent_runtime.migrate(self.db)
        self.db.execute('UPDATE agent_schema_meta SET version=3')
        with self.assertRaises(ValueError):agent_runtime.migrate(self.db)
        self.assertEqual(self.db.execute('SELECT version FROM agent_schema_meta').fetchone()[0],3)
        self.assertEqual(self.db.execute('SELECT count(*) FROM media_derivations').fetchone()[0],1)
        projected=agent_runtime.model_input_view({'processingKind':'image_analysis','agricultureContext':{'gardenName':'GARDEN_SENTINEL','plotId':'PLOT_SENTINEL','sources':[]}})
        self.assertNotIn('SENTINEL',encode(projected))
