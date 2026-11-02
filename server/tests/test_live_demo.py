"""Isolated virtual-scene contracts. No external model or hardware calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from server import agriculture as a, agriculture_live_demo as live, agent_runtime
from test_agriculture_domain import BASE, connect, png

class LiveDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'assets'
        self.db=connect(str(Path(self.tmp.name)/'db'));self.db.executescript(BASE);a.migrate(self.db)
        self.plot=a.create_entity(self.db,'a','w','plot',dict(commandId='p',name='一号地'))['plot']['id']
        self.other=a.create_entity(self.db,'a','w','plot',dict(commandId='p2',name='二号地'))['plot']['id']
        self.asset=a.upload(self.db,'a','w',dict(commandId='img',kind='image'),png(),'模拟原型图片.png',self.root)['asset']
        live.enable_demo(self.db,'a','w',100, [self.asset['id']])
        self.plot=live.view(self.db,'a','w',at=100)['robot']['plotId']
        self.other=next(p['id'] for p in a.entities(self.db,'a','w','plot') if p['id']!=self.plot)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def act(self,op,key=None,**args):return live.action(self.db,'a','w',dict(commandId=key or op,action=op,**args),self.root,110)['liveDemo']
    def test_read_scope_readonly_and_freshness(self):
        before=self.db.total_changes
        self.assertEqual(live.view(self.db,'a','w',at=121)['status'],'stale')
        self.assertEqual(live.view(self.db,'a','w',self.other,at=100)['samples'],[])
        self.assertIsNone(live.view(self.db,'a','w2',at=100))
        with self.assertRaises(a.AgricultureError):live.view(self.db,'b','w')
        with self.assertRaises(a.AgricultureError):self.act('demo.pause',plotId=self.other)
        self.assertEqual(before,self.db.total_changes)
    def test_tick_pause_restart_scene_and_bounded(self):
        before=[tuple(x) for x in self.db.execute('SELECT * FROM agriculture_entities')]
        with patch('server.agriculture.due_followups',side_effect=AssertionError('must not enqueue')):
            live.advance(self.db,104);self.assertEqual(live.view(self.db,'a','w',at=104)['version'],1)
            live.advance(self.db,105);live.advance(self.db,105)
        self.assertEqual(live.view(self.db,'a','w',at=105)['version'],2)
        self.act('scenario.set',scenario='humidity_change');live.advance(self.db,115)
        self.assertGreater(live.view(self.db,'a','w',at=115)['samples'][-1]['humidity'],68)
        self.act('demo.pause');v=live.view(self.db,'a','w',at=999);live.advance(self.db,999)
        self.assertEqual(live.view(self.db,'a','w',at=999),v)
        self.act('demo.resume');live.advance(self.db,114)
        self.assertEqual(live.view(self.db,'a','w',at=114)['samples'][-1]['observedAt'],115)
        for t in range(120,2000,5):live.advance(self.db,t)
        for i in range(40):self.act('scenario.set',str(i),scenario='leaf_anomaly')
        v=live.view(self.db,'a','w');self.assertLessEqual(len(v['samples']),120);self.assertEqual(len(v['events']),30)
        self.assertEqual(before,[tuple(x) for x in self.db.execute('SELECT * FROM agriculture_entities')])
    def test_robot_position_pause_and_return(self):
        self.act('robot.start')
        for t in range(115,150,5):live.advance(self.db,t)
        moving=live.view(self.db,'a','w')['robot'];self.assertGreater(moving['progress'],0)
        paused=self.act('robot.pause')['robot'];live.advance(self.db,155)
        self.assertEqual(paused['position'],live.view(self.db,'a','w')['robot']['position'])
        self.act('robot.return')
        for t in range(160,230,5):live.advance(self.db,t)
        r=live.view(self.db,'a','w')['robot'];self.assertEqual(r['state'],'docked');self.assertEqual(r['position'],r['route'][0])
    def test_low_battery_and_second_worker_persisted_pause(self):
        row=self.db.execute('SELECT * FROM agriculture_live_demo').fetchone()
        state=json.loads(row['state']);state['robot'].update(state='patrolling',battery=15,progress=40)
        live.save(self.db,row,state,100)
        second=connect(self.db.execute('PRAGMA database_list').fetchone()[2])
        try:
            live.advance(self.db,105);version=live.view(self.db,'a','w',at=105)['version']
            live.advance(second,105)
            self.assertEqual(live.view(second,'a','w',at=105)['version'],version)
            self.assertEqual(live.view(second,'a','w',at=105)['robot']['state'],'returning')
            self.act('demo.pause');live.advance(second,999)
            self.assertTrue(live.view(second,'a','w',at=999)['paused'])
        finally:second.close()
    def test_capture_private_copy_idempotent_and_revoked(self):
        first=self.act('camera.capture','snap',cameraId='demo-camera-1');second=self.act('camera.capture','snap',cameraId='demo-camera-1')
        self.assertEqual(first,second);cap=first['captures'][0];self.assertNotEqual(cap['assetId'],self.asset['id'])
        new=a.read(self.db,'a',cap['assetId'],'asset','w');old=a.read(self.db,'a',self.asset['id'],'asset','w')
        self.assertNotEqual(new['storageKey'],old['storageKey']);self.assertEqual(new['sha256'],old['sha256']);self.assertEqual(new['status'],'stored')
        with self.assertRaises(a.AgricultureError):self.act('camera.capture','snap',cameraId='demo-camera-2')
        self.db.execute('UPDATE agriculture_entities SET deleted=1 WHERE id=?',(old['id'],))
        with self.assertRaises(a.AgricultureError):a.asset_content(self.db,'a',new['id'],self.root)
        self.assertIsNone(live.view(self.db,'a','w')['captures'][0]['assetId'])
    def test_revoked_capture_source_blocks_publish_analysis_and_knowledge(self):
        capture=self.act('camera.capture','derived',cameraId='demo-camera-1')['captures'][0]['assetId']
        snapshot=a.snapshot_context(self.db,'a','w',dict(assetIds=[capture]))
        asset=a.read(self.db,'a',capture,'asset','w')
        asset.update(status='ready',analysis={'text':'previous analysis'})
        a.update(self.db,'a',capture,'asset',asset)
        knowledge=a.insert(self.db,'a','w','knowledge',dict(assetId=capture,title='capture excerpt',version=1,sourceHash=asset['sha256'],excerpts=[dict(locator='frame',text='excerpt')]))
        knowledge_snapshot=a.snapshot_context(self.db,'a','w',dict(knowledgeIds=[knowledge['id']]))
        turn=dict(id='synthetic-turn',owner='a',workspace_id='w',payload=dict(agricultureContext=snapshot,processingKind='image_analysis',mediaAssetId=capture))
        a.validate_context(self.db,'a','w',snapshot)
        media=agent_runtime.model_input_view(turn['payload'])['agricultureContext']
        self.assertNotIn('liveDemo',media)
        self.assertEqual(media['sources'][0]['origin'],'demo')
        prototype=a.snapshot_context(self.db,'a','w',dict(assetIds=[self.asset['id']]))
        self.assertEqual(agent_runtime.model_input_view(dict(agricultureContext=prototype,processingKind='image_analysis'))['agricultureContext']['sources'][0]['origin'],'demo')
        self.db.execute('UPDATE agriculture_entities SET deleted=1 WHERE id=?',(self.asset['id'],))
        checks=[lambda:a.validate_context(self.db,'a','w',snapshot),lambda:a.validate_context(self.db,'a','w',knowledge_snapshot),lambda:a.seal_media(self.db,turn,'must not publish'),lambda:a.execute_tool(self.db,{**turn,'payload':dict(agricultureContext=snapshot)},'read_asset_analysis',{'assetId':capture},'read')]
        for check in checks:
            with self.assertRaises(a.AgricultureError) as caught:check()
            self.assertEqual(caught.exception.code,'asset_revoked')
        self.assertEqual(a.read(self.db,'a',capture,'asset','w')['analysis']['text'],'previous analysis')
    def test_same_named_user_upload_is_not_demo_source(self):
        ordinary=a.upload(self.db,'a','w',dict(commandId='ordinary-same-name',kind='image'),png(),'模拟原型图片.png',self.root)['asset']
        snapshot=a.snapshot_context(self.db,'a','w',dict(assetIds=[ordinary['id']]))
        asset_source=next(source for source in snapshot['sources'] if source['id']==ordinary['id'])
        self.assertNotIn('origin',asset_source)
        media=agent_runtime.model_input_view(dict(agricultureContext=snapshot,processingKind='image_analysis'))
        self.assertNotIn('origin',media['agricultureContext']['sources'][0])
        self.db.execute('UPDATE agriculture_live_demo SET enabled=0')
        prototype=a.snapshot_context(self.db,'a','w',dict(assetIds=[self.asset['id']]))
        self.assertNotIn('origin',prototype['sources'][0])
    def test_snapshot_frozen_tick_model_projection_media(self):
        snapshot=a.snapshot_context(self.db,'a','w',dict(plotId=self.plot))
        live.advance(self.db,200);a.validate_context(self.db,'a','w',snapshot)
        self.assertEqual(snapshot['liveDemo']['observedAt'],100)
        result=agent_runtime.model_input_view(dict(agricultureContext=snapshot))
        self.assertEqual(result['agricultureContext']['liveDemo']['samples'][0]['humidity'],68)
        media=agent_runtime.model_input_view(dict(agricultureContext=snapshot,processingKind='image_analysis'))
        self.assertNotIn('liveDemo',media['agricultureContext']);self.assertFalse(media['agricultureContext']['sources'])
    def test_migration_and_validation(self):
        self.db.execute('UPDATE agriculture_schema_meta SET version=1');a.migrate(self.db);a.migrate(self.db)
        self.assertEqual(self.db.execute('SELECT version FROM agriculture_schema_meta').fetchone()[0],2)
        self.db.execute('UPDATE agriculture_schema_meta SET version=99')
        with self.assertRaises(RuntimeError):a.migrate(self.db)
        for args in [dict(action='wrong'),dict(action='scenario.set',scenario='bad'),dict(action='demo.pause',cameraId='demo-camera-1')]:
            with self.assertRaises(a.AgricultureError):live.action(self.db,'a','w',dict(commandId='bad',**args),self.root,100)

class LiveHTTPTests(unittest.TestCase):
    from test_agriculture_domain_http import AgricultureHTTPTests as Fixture
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    def test_http_csrf_scope_get_zero_write_worker_no_model(self):
        from server.app import run_once
        plot=a.create_entity(self.db,'a','a-w','plot',dict(commandId='p',name='Plot'))['plot']['id']
        live.enable_demo(self.db,'a','a-w',time_now:=__import__('time').time()-10,[])
        path='/api/v1/workspaces/a-w/live-demo'
        before=self.db.total_changes
        self.assertEqual(self.a.get(path).status_code,200)
        self.assertEqual(before,self.db.total_changes)
        self.assertEqual(self.b.get(path).status_code,404)
        self.assertEqual(self.a.get(path+'?plotId=foreign').status_code,404)
        body=dict(commandId='pause',action='demo.pause')
        self.assertEqual(self.a.post(path+'/actions',json=body).status_code,403)
        headers={'X-CSRF-Token':'a-csrf'}
        self.assertEqual(self.a.post(path+'/actions',json=body,headers={**headers,'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.b.post(path+'/actions',json=body,headers={'X-CSRF-Token':'b-csrf'}).status_code,404)
        response=self.a.post(path+'/actions',json=body,headers=headers)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['liveDemo']['status'],'paused')
        self.assertEqual(self.a.post(path+'/actions',json=body,headers=headers).json,response.json)
        self.assertEqual(self.a.post(path+'/actions',json={**body,'action':'demo.resume'},headers=headers).status_code,409)
        self.assertEqual(self.a.post(path+'/actions',json=dict(commandId='resume',action='demo.resume'),headers=headers).status_code,200)
        self.db.execute('UPDATE agriculture_live_demo SET state=json_set(state,\'$.lastTickAt\',?)',(time_now,))
        with patch('server.app.provider',side_effect=AssertionError('no automatic model')):
            self.assertFalse(run_once(self.app))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM turns').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM agriculture_device_events').fetchone()[0],0)
        self.assertGreater(live.view(self.db,'a','a-w')['version'],3)
