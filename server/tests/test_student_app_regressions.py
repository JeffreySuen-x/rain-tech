"""Student delivery regressions: synthetic data and child processes only."""
import contextlib
import json
import subprocess
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from server import agriculture, agent_runtime
from server.app import run_once
from server.tests import test_server
from server.tests import test_agent_runtime
from server.tests.test_agriculture_domain import png


class StudentRuntimeTests(unittest.TestCase):
    setUp=test_server.ServerTests.setUp
    tearDown=test_server.ServerTests.tearDown
    login=test_server.ServerTests.login
    post=test_server.ServerTests.post
    submit=test_server.ServerTests.submit
    status=test_server.ServerTests.status
    modify_payload=test_agent_runtime.AgentRuntimeTests.modify_payload
    http=test_agent_runtime.AgentRuntimeTests.http
    answer=test_agent_runtime.AgentRuntimeTests.answer

    @contextlib.contextmanager
    def node_child(self, code):
        original=subprocess.Popen
        children=[]
        def start(_command, **kwargs):
            child=original(['node','-e',code],**kwargs)
            children.append(child)
            return child
        with patch.object(agent_runtime.subprocess,'Popen',side_effect=start):yield children
        for child in children:
            self.assertIsNotNone(child.poll(),'child must be reaped')
            self.assertTrue(child.stdin.closed)
            self.assertTrue(child.stdout.closed)

    def error(self, turn):
        return json.loads(self.db.execute('SELECT error FROM turns WHERE id=?',(turn,)).fetchone()[0])['code']

    def test_actual_node_text_tool_text_keeps_durable_receipts(self):
        def respond(calls):
            if len(calls)==1:return {'choices':[{'message':{'role':'assistant','tool_calls':[{'id':'inspect','type':'function','function':{'name':'list_work_items','arguments':'{}'}}]}}]}
            return self.answer('Synthetic sourced response')
        with self.http(respond) as calls:
            turn=self.submit();run_once(self.app)
            self.assertEqual(self.status(turn),'completed');self.assertEqual(len(calls),2)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT kind,state FROM agent_receipts ORDER BY rowid')],[('model','sealed'),('tool','sealed'),('model','sealed')])

    def test_actual_node_eof_protocol_and_output_limit_are_known_failures(self):
        for code, expected in [('process.exit(0)','runtime_unavailable'),("process.stdout.write('invalid-json\\n');process.stdin.resume()",'runtime_unavailable'),("process.stdout.write('x'.repeat(2048));process.stdin.resume()",'budget_exceeded')]:
            with self.subTest(code=code),self.node_child(code):
                turn=self.submit();self.modify_payload(turn,budget={'maxOutputBytes':1024});run_once(self.app)
                self.assertEqual(self.status(turn),'failed');self.assertEqual(self.error(turn),expected)
                self.assertEqual(self.db.execute('SELECT count(*) FROM agent_receipts WHERE turn_id=?',(turn,)).fetchone()[0],0)

    def test_actual_node_stall_obeys_deadline_and_reaps(self):
        with self.node_child('process.stdin.resume()'):
            turn=self.submit();self.modify_payload(turn,budget={'deadlineSeconds':.15})
            started=time.monotonic();run_once(self.app)
            self.assertLess(time.monotonic()-started,3)
            self.assertEqual(self.status(turn),'failed');self.assertEqual(self.error(turn),'budget_exceeded')

    def test_actual_node_not_reading_large_stdin_still_obeys_deadline(self):
        with self.node_child('setInterval(()=>{},1000)'):
            turn=self.submit();self.modify_payload(turn,background='x'*(1024*1024),budget={'deadlineSeconds':.15})
            started=time.monotonic();run_once(self.app)
            self.assertLess(time.monotonic()-started,3)
            self.assertEqual(self.status(turn),'failed');self.assertEqual(self.error(turn),'budget_exceeded')

    def test_actual_node_stall_cancel_fence_reaps_without_artifact(self):
        with self.node_child('process.stdin.resume()') as children:
            turn=self.submit();worker=threading.Thread(target=run_once,args=(self.app,));worker.start()
            deadline=time.monotonic()+3
            while not children and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue(children)
            self.post('/turns/'+turn+'/cancel',{'commandId':'stop-node'},status=200)
            worker.join(4);self.assertFalse(worker.is_alive());self.assertEqual(self.status(turn),'cancelled')
            self.assertEqual(self.db.execute('SELECT count(*) FROM artifacts').fetchone()[0],0)

    def test_missing_runtime_and_thread_start_failure_cleanup_are_known(self):
        with patch.object(agent_runtime.subprocess,'Popen',side_effect=OSError('synthetic unavailable')):
            turn=self.submit();run_once(self.app);self.assertEqual(self.error(turn),'runtime_unavailable');self.assertEqual(self.status(turn),'failed')
        original=threading.Thread.start
        count=0
        def start(thread):
            nonlocal count
            count+=1
            if count==2:raise RuntimeError('synthetic reader startup failure')
            return original(thread)
        with self.node_child('process.stdin.resume()'),patch.object(agent_runtime.threading.Thread,'start',new=start):
            turn=self.submit();run_once(self.app);self.assertEqual(self.status(turn),'failed');self.assertEqual(self.error(turn),'runtime_unavailable')


class StudentPhotoTests(unittest.TestCase):
    setUp=test_server.ServerTests.setUp
    tearDown=test_server.ServerTests.tearDown
    login=test_server.ServerTests.login
    post=test_server.ServerTests.post
    submit=test_server.ServerTests.submit
    status=test_server.ServerTests.status

    def photo(self, key, wid=None, owner='a'):
        root=self.tmp.name+'/assets';self.app.config['ASSET_ROOT']=root
        return agriculture.upload(self.db,owner,wid or self.w,{'commandId':key,'kind':'image'},png(),key+'.png',root)['asset']

    def messages(self):
        response=self.a.get('/api/v1/threads/'+self.t);self.assertEqual(response.status_code,200)
        return response.json['messages']

    def test_chat_and_media_history_restore_only_available_frozen_images(self):
        image=self.photo('photo')
        turn=self.submit(agricultureContext={'assetIds':[image['id']]});run_once(self.app,lambda p:'Synthetic image response')
        self.assertEqual(self.messages()[0]['assetIds'],[image['id']])
        media=self.post('/assets/'+image['id']+'/analyze',{'commandId':'analyze','threadId':self.t},status=202)['turn']['id'];run_once(self.app,lambda p:'Synthetic analysis')
        messages=self.messages();self.assertEqual(messages[2]['assetIds'],[image['id']])
        self.assertEqual(self.b.get('/api/v1/threads/'+self.t).status_code,404)
        self.a.delete('/api/v1/assets/'+image['id'],headers={'X-CSRF-Token':self.at})
        messages=self.messages();self.assertEqual(messages[0]['assetIds'],[]);self.assertEqual(messages[2]['assetIds'],[])
        self.assertEqual(messages[0]['content'],'What next?');self.assertEqual(messages[1]['content'],'Synthetic image response')

    def test_missing_changed_cross_workspace_and_foreign_owner_images_omitted(self):
        image=self.photo('photo')
        turn=self.submit(agricultureContext={'assetIds':[image['id']]});run_once(self.app,lambda p:'answer')
        raw=self.db.execute('SELECT payload FROM turns WHERE id=?',(turn,)).fetchone()[0];payload=json.loads(raw)
        def replace_reference(asset):
            payload['agricultureContext']['assets']=[{'id':asset['id'],'version':asset['version'],'sourceHash':asset['sha256']}]
            self.db.execute('UPDATE turns SET payload=? WHERE id=?',(json.dumps(payload),turn))
        other=self.post('/workspaces',{'name':'Other garden'})['workspace']['id']
        foreign=self.post('/workspaces',{'name':'Foreign'},self.b,self.bt)['workspace']['id']
        for asset in [self.photo('other',other),self.photo('foreign',foreign,'b')]:
            replace_reference(asset);self.assertEqual(self.messages()[0]['assetIds'],[])
        replace_reference(image)
        payload['agricultureContext']['assets'][0]['version']=image['version']+1
        self.db.execute('UPDATE turns SET payload=? WHERE id=?',(json.dumps(payload),turn));self.assertEqual(self.messages()[0]['assetIds'],[])
        replace_reference(image);(Path(self.app.config['ASSET_ROOT'])/agriculture.read(self.db,'a',image['id'],'asset')['storageKey']).unlink()
        self.assertEqual(self.messages()[0]['assetIds'],[])
        del payload['agricultureContext'];self.db.execute('UPDATE turns SET payload=? WHERE id=?',(json.dumps(payload),turn))
        self.assertEqual(self.messages()[0]['assetIds'],[]);self.assertEqual(self.messages()[0]['content'],'What next?')


class StudentLocalConfigTests(unittest.TestCase):
    def test_non_posix_config_fails_closed_before_read_or_mutation(self):
        from server import local_config
        env={'SHUYU_PROVIDER_MODEL':'synthetic'}
        with patch.object(local_config.os,'name','nt'),patch.object(local_config.os,'open') as opened:
            with self.assertRaisesRegex(ValueError,'POSIX permission checks'):
                local_config.load_config('unused-private-config.json',env)
        opened.assert_not_called()
        self.assertEqual(env,{'SHUYU_PROVIDER_MODEL':'synthetic'})


class PublicSeedTests(unittest.TestCase):
    def test_seed_has_explicit_synthetic_identity_and_complete_owned_references(self):
        import sqlite3
        import tempfile
        from server import student_demo, workspace_seed, demo_restore
        self.assertEqual(workspace_seed.WORKSPACE, 'shuyu-demo-workspace-v1')
        self.assertEqual(demo_restore.SOURCE_WORKSPACE, workspace_seed.WORKSPACE)
        self.assertEqual(demo_restore.SOURCE_USER, 'synthetic-demo-source')
        with tempfile.TemporaryDirectory() as tmp, patch('socket.socket', side_effect=AssertionError('seed must be offline')):
            output = Path(tmp) / 'seed'
            student_demo.build(output)
            with sqlite3.connect(output / 'shuyu.sqlite3') as db:
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(db.execute('SELECT id,owner FROM workspaces').fetchall(),
                                 [('shuyu-demo-workspace-v1', student_demo.OWNER)])
                for table in ('threads', 'agriculture_entities'):
                    self.assertEqual(db.execute('SELECT DISTINCT workspace_id,owner FROM ' + table).fetchall(),
                                     [('shuyu-demo-workspace-v1', student_demo.OWNER)])
                self.assertEqual(db.execute("SELECT count(*) FROM agriculture_entities WHERE kind='knowledge'").fetchone()[0], 6)
                for table in ('sessions', 'turns', 'agent_receipts'):
                    self.assertEqual(db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
            before = (output / 'shuyu.sqlite3').read_bytes()
            with self.assertRaises(FileExistsError): student_demo.build(output)
            self.assertEqual((output / 'shuyu.sqlite3').read_bytes(), before)
