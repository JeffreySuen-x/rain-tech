"""Independent privacy acceptance: synthetic data, real DSH and loopback HTTP."""
import base64
import contextlib
import io
import json
import os
import stat
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from server import agriculture, agent_runtime, agent_provider
from server.app import run_once, encode
from server.tests import test_independent_agriculture_contracts as foundation

class IndependentShuyuPrivacyTests(unittest.TestCase):
    setUp=foundation.IndependentAgricultureTests.setUp
    tearDown=foundation.IndependentAgricultureTests.tearDown
    login=foundation.IndependentAgricultureTests.login
    post=foundation.IndependentAgricultureTests.post
    def submit(self,**kw):
        return self.post('/threads/'+self.t+'/turns',self.command(prompt=kw.pop('prompt','What next?'),**kw),status=202)['turn']['id']
    status=foundation.IndependentAgricultureTests.status
    command=foundation.IndependentAgricultureTests.command
    upload=foundation.IndependentAgricultureTests.upload
    task=foundation.IndependentAgricultureTests.task
    http=foundation.IndependentAgricultureTests.http
    answer=foundation.IndependentAgricultureTests.answer

    def test_actual_dsh_unselected_defaults_and_selected_asset_analysis(self):
        selected=self.upload(raw=b'SELECTED_INDEPENDENT_FACT')
        self.upload(raw=b'UNSELECTED_INDEPENDENT_FACT',name='other.txt')
        self.post('/workspaces/'+self.w+'/memories',self.command(content='UNSELECTED_MEMORY_PRIVATE'))
        first=self.submit(prompt='HISTORY_PRIVATE_SENTINEL')
        run_once(self.app,lambda p:'HISTORICAL_ANSWER_PRIVATE')
        # Authorized image analysis is readable, but its private storage fields are not.
        raw=io.BytesIO();Image.new('RGB',(2,2)).save(raw,'PNG')
        image=self.upload('image',raw.getvalue(),'private-image.png')['asset']
        with agriculture.atomic(self.db):
            value=agriculture.read(self.db,'a',image['id'],'asset')
            agriculture.update(self.db,'a',image['id'],'asset',{**value,'analysis':{'text':'SELECTED_ANALYSIS_ALLOWED','draft':False},'internalSecret':'PRIVATE_TOOL_SENTINEL'})
        def respond(calls):
            if len(calls)==1:return {'choices':[{'message':{'role':'assistant','tool_calls':[{'id':'selected','type':'function','function':{'name':'read_asset_analysis','arguments':json.dumps({'assetId':image['id']})}}]}}]}
            return self.answer('已核对选定分析')
        with self.http(respond) as calls:
            tid=self.submit(includeHistory=False,agricultureContext={'assetIds':[image['id'],selected['asset']['id']]})
            run_once(self.app);self.assertEqual(self.status(tid),'completed')
            self.assertEqual(len(calls),2)
            captured=b'\n'.join(c[2] for c in calls)
            for sentinel in [b'UNSELECTED_INDEPENDENT_FACT',b'UNSELECTED_MEMORY_PRIVATE',b'HISTORY_PRIVATE_SENTINEL',b'HISTORICAL_ANSWER_PRIVATE',b'PRIVATE_TOOL_SENTINEL']:
                self.assertNotIn(sentinel,captured)
            self.assertIn(b'SELECTED_INDEPENDENT_FACT',calls[0][2])
            self.assertIn(b'SELECTED_ANALYSIS_ALLOWED',calls[1][2])
            for internal in ['owner','workspaceId','threadId','storageKey','credentialHash','historyMemoryIds','authorizationVersion']:
                self.assertNotIn(('"'+internal+'"').encode(),captured)

    def test_media_has_no_history_knowledge_or_tools_and_strips_real_gps(self):
        self.upload(raw=b'UNSELECTED_MEDIA_DOCUMENT')
        prior=self.submit(prompt='PRIVATE_MEDIA_HISTORY');run_once(self.app,lambda p:'PRIVATE_MEDIA_ANSWER')
        exif=Image.Exif();exif[274]=6;exif[270]='PRIVATE_EXIF_DESCRIPTION';exif[34853]={1:'N',2:(30.0,10.0,20.0),3:'E',4:(120.0,10.0,20.0)}
        output=io.BytesIO();Image.new('RGB',(3,7),'blue').save(output,'JPEG',exif=exif,icc_profile=b'PRIVATE_ICC')
        original=output.getvalue();image=self.upload('image',original,'PRIVATE_ORIGINAL_FILENAME.jpg')['asset']
        with self.http(lambda c:self.answer('仅分析本图')) as calls:
            tid=self.post('/assets/'+image['id']+'/analyze',self.command(threadId=self.t),status=202)['turn']['id']
            run_once(self.app);self.assertEqual(self.status(tid),'completed')
            request=json.loads(calls[0][2]);self.assertFalse(request.get('tools'))
            for sentinel in [b'UNSELECTED_MEDIA_DOCUMENT',b'PRIVATE_MEDIA_HISTORY',b'PRIVATE_MEDIA_ANSWER',b'PRIVATE_ORIGINAL_FILENAME',b'PRIVATE_EXIF_DESCRIPTION',b'PRIVATE_ICC']:
                self.assertNotIn(sentinel,calls[0][2])
            binary=base64.b64decode(request['messages'][-1]['content'][-1]['image_url']['url'].split(',')[1])
            with Image.open(io.BytesIO(binary)) as clean:
                self.assertEqual(clean.size,(7,3));self.assertEqual(dict(clean.getexif()),{});self.assertEqual(clean.info,{})
            path,_=agriculture.asset_content(self.db,'a',image['id'],self.app.config['ASSET_ROOT'])
            self.assertEqual(path.read_bytes(),original)
            provenance=json.loads(self.db.execute('SELECT provenance FROM media_derivations WHERE turn_id=?',(tid,)).fetchone()[0])
            self.assertNotEqual(provenance['originalHash'],provenance['derivedHash'])
            for name in ['list_work_items','read_source','read_observations']:
                turn=self.db.execute('SELECT * FROM turns WHERE id=?',(tid,)).fetchone()
                with self.assertRaises(agriculture.AgricultureError):agriculture.execute_tool(self.db,turn,name,{},'attempt')

    def test_actual_followup_tools_bound_to_authorized_item_and_plot(self):
        plot=self.post('/workspaces/'+self.w+'/plots',self.command(name='Selected plot'))['plot']
        target=self.post('/workspaces/'+self.w+'/work-items',self.command(title='AUTHORIZED_TARGET_ITEM',plotId=plot['id']))['workItem']
        self.post('/workspaces/'+self.w+'/work-items',self.command(title='UNAUTHORIZED_OTHER_ITEM'))
        self.upload(raw=b'UNAUTHORIZED_FOLLOWUP_KNOWLEDGE')
        self.post('/work-items/'+target['id']+'/follow-up',self.command(threadId=self.t,enabled=True,nextDueAt=time.time()-1,maxRuns=1,maxModelCalls=2),status=200)
        def respond(calls):
            if len(calls)==1:return {'choices':[{'message':{'role':'assistant','tool_calls':[{'id':'read','type':'function','function':{'name':'list_work_items','arguments':'{}'}}]}}]}
            return self.answer('无新观察')
        with self.http(respond) as calls:
            self.assertTrue(run_once(self.app));self.assertEqual(len(calls),2)
            outbound=b'\n'.join(c[2] for c in calls)
            self.assertIn(b'AUTHORIZED_TARGET_ITEM',outbound)
            for forbidden in [b'UNAUTHORIZED_OTHER_ITEM',b'UNAUTHORIZED_FOLLOWUP_KNOWLEDGE',b'authorizationVersion',b'remainingRuns']:
                self.assertNotIn(forbidden,outbound)
            turn=self.db.execute('SELECT * FROM turns ORDER BY created_at DESC LIMIT 1').fetchone()
            payload=json.loads(turn['payload']);foreign=self.post('/workspaces',{'name':'foreign'})['workspace']['id']
            other=agriculture.create_entity(self.db,'a',foreign,'plot',self.command(name='foreign plot'))['plot']
            with self.assertRaises(agriculture.AgricultureError):
                agriculture.snapshot_context(self.db,'b',self.w,{})
            with self.assertRaises(agriculture.AgricultureError):
                agriculture.snapshot_context(self.db,'a',self.w,{'plotId':other['id']})

    def test_real_redirect_denial_proxy_ignored_child_env_and_permissions(self):
        hits=[]
        class Sink(BaseHTTPRequestHandler):
            def do_POST(s):hits.append(s.path);s.send_response(200);s.end_headers()
            def do_GET(s):hits.append(s.path);s.send_response(200);s.end_headers()
            def log_message(self,*args):pass
        sink=ThreadingHTTPServer(('127.0.0.1',0),Sink);thread=threading.Thread(target=sink.serve_forever);thread.start()
        class Redirect(BaseHTTPRequestHandler):
            def do_POST(s):s.rfile.read(int(s.headers['Content-Length']));s.send_response(307);s.send_header('Location',f'http://127.0.0.1:{sink.server_port}/sink');s.end_headers()
            def log_message(self,*args):pass
        redirect=ThreadingHTTPServer(('127.0.0.1',0),Redirect);rt=threading.Thread(target=redirect.serve_forever);rt.start()
        try:
            self.app.config.update(PROVIDER_URL=f'http://127.0.0.1:{redirect.server_port}',PROVIDER_KEY='INDEPENDENT_KEY_SENTINEL',PROVIDER_MODEL='local',PROVIDER_CAPABILITIES='text')
            tid=self.submit();run_once(self.app);self.assertEqual(self.status(tid),'needs_review');run_once(self.app)
            self.assertEqual(hits,[])
            with patch.dict(os.environ,{'HTTP_PROXY':f'http://127.0.0.1:{sink.server_port}','HTTPS_PROXY':f'http://127.0.0.1:{sink.server_port}','NO_PROXY':'','no_proxy':'','DATABASE_URL':'CHILD_PRIVATE_SENTINEL'}):
                import subprocess
                real=subprocess.Popen;envs=[]
                def launch(*args,**kwargs):envs.append(kwargs['env']);return real(*args,**kwargs)
                with self.http(lambda c:self.answer('ok')) as calls,patch('server.agent_runtime.subprocess.Popen',side_effect=launch):
                    tid=self.submit();run_once(self.app);self.assertEqual(self.status(tid),'completed');self.assertEqual(len(calls),1)
                    self.assertTrue(envs);self.assertNotIn('DATABASE_URL',envs[0]);self.assertNotIn('HTTP_PROXY',envs[0]);self.assertEqual(hits,[])
            all_receipts=''.join(r[0] or '' for r in self.db.execute('SELECT result FROM agent_receipts'))
            self.assertNotIn('INDEPENDENT_KEY_SENTINEL',all_receipts)
            self.assertEqual(stat.S_IMODE(Path(self.app.config['DB_PATH']).stat().st_mode),0o600)
            uploaded=self.upload();path,_=agriculture.asset_content(self.db,'a',uploaded['asset']['id'],self.app.config['ASSET_ROOT'])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600);self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode),0o700)
        finally:
            redirect.shutdown();sink.shutdown();rt.join();thread.join();redirect.server_close();sink.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
