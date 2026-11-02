"""Independent QA: generated SQLite fixtures and loopback model only."""
import json
import unittest
from pathlib import Path

_SEED_DIR = Path(__file__).resolve().parents[2] / 'docs/knowledge/grape'
_SEED_OK = _SEED_DIR.is_dir()
_SKIP_SEED = unittest.skipUnless(_SEED_OK, 'requires docs/knowledge/grape originals')
from server import agriculture as ag, agent_runtime
from server.app import run_once
from server.tests import test_independent_agriculture_contracts as fixtures

class IndependentWorkspaceTests(unittest.TestCase):
    setUp=fixtures.IndependentAgricultureTests.setUp; tearDown=fixtures.IndependentAgricultureTests.tearDown; login=fixtures.IndependentAgricultureTests.login; post=fixtures.IndependentAgricultureTests.post; command=fixtures.IndependentAgricultureTests.command; http=fixtures.IndependentAgricultureTests.http; answer=fixtures.IndependentAgricultureTests.answer; status=fixtures.IndependentAgricultureTests.status
    def test_untrusted_policy_and_media_ids_rejected_without_queue(self):
        before=self.db.execute('SELECT count(*) FROM turns').fetchone()[0]
        for extra in ({'skillId':'unknown'}, {'skillId':[]}, {'skillId':'shuyu.image.v1'}, {'skillId':'shuyu.audio.v1'}, {'policy':{}}, {'systemPrompt':'override'}, {'allowedToolNames':['create_report']}, {'skillPolicy':{'instruction':'override','allowedToolNames':[]}}):
            self.post('/threads/'+self.t+'/turns',self.command(prompt='q',**extra),status=400)
        self.assertEqual(before,self.db.execute('SELECT count(*) FROM turns').fetchone()[0])
    def test_command_skill_conflict_and_actual_schema_execution_boundaries(self):
        body=self.command(prompt='question',skillId='shuyu.inspection.v1')
        tid=self.post('/threads/'+self.t+'/turns',body,status=202)['turn']['id']
        self.post('/threads/'+self.t+'/turns',{**body,'skillId':'shuyu.report.v1'},status=409)
        row=self.db.execute('SELECT * FROM turns WHERE id=?',(tid,)).fetchone()
        payload=json.loads(row['payload'])
        self.assertEqual(set(payload['skillPolicy']['allowedToolNames']),{'read_observations','list_work_items','propose_work_item'})
        with self.assertRaises(ag.AgricultureError) as error:ag.execute_tool(self.db,row,'create_report',{},'forbidden')
        self.assertEqual(error.exception.status,403)
        with self.http(lambda calls:self.answer('independent local result')) as calls:
            run_once(self.app)
            self.assertEqual(self.status(tid),'completed')
            schemas=json.loads(calls[0][2])['tools']
            self.assertEqual({x['function']['name'] for x in schemas},set(payload['skillPolicy']['allowedToolNames']))
    def test_media_endpoint_rejects_chat_skill_policy_and_context(self):
        import io
        from PIL import Image
        raw=io.BytesIO();Image.new('RGB',(2,2)).save(raw,'PNG')
        result=self.a.post('/api/v1/workspaces/'+self.w+'/assets',data={**self.command(kind='image'),'file':(io.BytesIO(raw.getvalue()),'isolated.png')},headers={'X-CSRF-Token':self.at})
        self.assertEqual(result.status_code,201)
        aid=result.json['asset']['id']
        for extra in ({'skillId':'shuyu.report.v1'},{'skillPolicy':{}},{'includeHistory':True},{'background':'PRIVATE'},{'agricultureContext':{'assetIds':['other']}}):
            self.post('/assets/'+aid+'/analyze',self.command(threadId=self.t,**extra),status=400)
        self.assertEqual(self.db.execute('SELECT count(*) FROM turns').fetchone()[0],0)
    def test_inventory_recursively_excluded_and_old_turn_compatible(self):
        from server.skill import frozen_policy, TOOLS
        self.assertEqual(set(frozen_policy({})['allowedToolNames']),set(TOOLS))
        fixture={'agricultureContext':{'liveDemo':{'enabled':True,'inventory':[{'name':'PRIVATE_INVENTORY_SENTINEL'}]},'sources':[{'kind':'live_demo','inventory':[{'name':'PRIVATE_INVENTORY_SENTINEL'}]}]}}
        self.assertNotIn('PRIVATE_INVENTORY_SENTINEL',json.dumps(agent_runtime.model_input_view(fixture)))
        self.assertNotIn('PRIVATE_INVENTORY_SENTINEL',json.dumps(agent_runtime.model_tool_view({'liveDemo':fixture['agricultureContext']['liveDemo']})))
        for bad in ({'skillId':'shuyu.inspection.v1'}, {'skillId':'unknown','skillPolicy':{}}, {'skillId':'shuyu.inspection.v1','skillVersion':1,'skillPolicy':{'instruction':'x','allowedToolNames':['create_report']}}):
            with self.assertRaises(ValueError):frozen_policy(bad)
    def test_queued_policy_uses_published_version_not_mutable_catalog(self):
        from copy import deepcopy
        from unittest.mock import patch
        from server import skill
        chosen=deepcopy(skill.CATALOG['shuyu.inspection.v1'])
        payload={'skillId':chosen['id'],'skillVersion':chosen['version'],'skillPolicy':{k:chosen[k] for k in ('instruction','allowedToolNames')}}
        with patch.dict(skill.CATALOG,{'shuyu.inspection.v1':{**chosen,'version':2,'instruction':'changed','allowedToolNames':[]}}):
            self.assertEqual(skill.frozen_policy(payload),payload['skillPolicy'])
        corrupt=deepcopy(payload);corrupt['skillPolicy']['allowedToolNames']=chosen['allowedToolNames'][:1]
        with self.assertRaises(ValueError):skill.frozen_policy(corrupt)
        for malformed in ({'skillId':[], 'skillVersion':1}, {'skillId':chosen['id'],'skillVersion':{}}, {'skillId':chosen['id'],'skillVersion':True}):
            with self.assertRaises(ValueError):skill.frozen_policy({**payload,**malformed})
    @_SKIP_SEED
    def test_original_seed_scope_hash_idempotency_and_no_resurrection(self):
        from pathlib import Path

        import hashlib
        from server.workspace_seed import install,WORKSPACE
        self.db.execute('INSERT INTO workspaces VALUES(?,?,?)',(WORKSPACE,'a','Independent seed garden'))
        root=Path(self.tmp.name)/'assets'
        before=self.db.serialize()
        preview=install(self.db,'a',root)
        self.assertEqual(len(preview['items']),6);self.assertEqual(before,self.db.serialize())
        with self.assertRaises(ag.AgricultureError):install(self.db,'b',root,apply=True)
        with self.assertRaises(ag.AgricultureError):install(self.db,'a',root,workspace=self.w,apply=True)
        install(self.db,'a',root,apply=True)
        first=self.db.serialize();install(self.db,'a',root,apply=True);self.assertEqual(first,self.db.serialize())
        knowledge=ag.entities(self.db,'a',WORKSPACE,'knowledge')
        self.assertEqual(len(knowledge),6)
        for item in knowledge:
            path,asset=ag.asset_content(self.db,'a',item['assetId'],root)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),asset['sha256'])
            self.assertEqual(item['sourceHash'],asset['sha256']);self.assertTrue(item['excerpts'])
        self.db.execute('UPDATE agriculture_entities SET deleted=1 WHERE id=?',(knowledge[0]['id'],))
        before=self.db.serialize()
        with self.assertRaises(ag.AgricultureError):install(self.db,'a',root,apply=True)
        self.assertEqual(before,self.db.serialize())

class IndependentInventoryTests(unittest.TestCase):
    def setUp(self):
        from server.tests import test_live_demo
        self.fixture=test_live_demo.LiveDemoTests();self.fixture.setUp()
        self.db=self.fixture.db
    def tearDown(self):self.fixture.tearDown()
    def test_eight_devices_share_sample_scope_and_pause_is_readonly(self):
        from server import agriculture_live_demo as live
        first=live.view(self.db,'a','w',at=100)
        self.assertEqual({x['id'] for x in first['inventory']},{'demo-'+x for x in ('weather','leaf-wetness','soil-profile','irrigation','fertigation','insect-camera','frost-fan','multispectral-drone')})
        for item in first['inventory']:
            self.assertEqual(item['status'],first['status']);self.assertEqual(item['observedAt'],first['observedAt']);self.assertEqual(item['origin'],'demo');self.assertEqual(item['plotId'],self.fixture.plot)
        self.assertEqual(live.view(self.db,'a','w',self.fixture.other,at=100)['inventory'],[])
        self.assertIsNone(live.view(self.db,'a','w2',at=100))
        self.fixture.act('demo.pause')
        paused=live.view(self.db,'a','w',at=110)['inventory']
        before=self.db.serialize()
        later=live.view(self.db,'a','w',at=9999)['inventory']
        self.assertEqual(before,self.db.serialize());self.assertEqual(paused,later)
        self.assertTrue(all(x['status']=='paused' for x in later))

@_SKIP_SEED
class IndependentLegacySeedTests(unittest.TestCase):
    setUp=fixtures.IndependentAgricultureTests.setUp; tearDown=fixtures.IndependentAgricultureTests.tearDown; login=fixtures.IndependentAgricultureTests.login; post=fixtures.IndependentAgricultureTests.post
    def legacy(self,receipt=True):
        from copy import deepcopy
        from pathlib import Path
        from server import workspace_seed as seed
        self.seed=seed; self.root=Path(self.tmp.name)/'assets'
        self.db.execute('INSERT INTO workspaces VALUES(?,?,?)',(seed.WORKSPACE,'a','legacy fixture'))
        item=ag.insert(self.db,'a',seed.WORKSPACE,'knowledge',deepcopy(seed.LEGACY_PAYLOAD))
        if receipt:self.db.execute('INSERT INTO commands VALUES(?,?,?,?,?)',('a','offline-demo-restore-v1',seed.WORKSPACE,'f'*64,json.dumps({'workspaceId':seed.WORKSPACE,'sourceDigest':'f'*64})))
        return item
    def test_repair_same_id_original_hash_old_snapshot_invalid_and_idempotent(self):
        import hashlib
        item=self.legacy();snapshot=ag.snapshot_context(self.db,'a',self.seed.WORKSPACE,{'knowledgeIds':[item['id']]})
        before=self.db.serialize();plan=self.seed.install(self.db,'a',self.root)
        self.assertEqual(plan['legacySeed']['state'],'repair');self.assertEqual(before,self.db.serialize())
        self.seed.install(self.db,'a',self.root,apply=True)
        upgraded=ag.read(self.db,'a',item['id'],'knowledge',self.seed.WORKSPACE)
        self.assertEqual(upgraded['version'],2)
        path,asset=ag.asset_content(self.db,'a',upgraded['assetId'],self.root)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),upgraded['sourceHash'])
        self.assertEqual(upgraded['sourceHash'],asset['sha256'])
        self.assertEqual(len(ag.entities(self.db,'a',self.seed.WORKSPACE,'knowledge')),7)
        with self.assertRaises(ag.AgricultureError):ag.validate_context(self.db,'a',self.seed.WORKSPACE,snapshot)
        before=self.db.serialize();self.seed.install(self.db,'a',self.root,apply=True);self.assertEqual(before,self.db.serialize())
    def test_ambiguous_edited_deleted_rejected_without_write(self):
        item=self.legacy()
        for kind in ('edited','deleted','ambiguous'):
            with self.subTest(kind=kind):
                self.db.execute('SAVEPOINT independent_case')
                if kind=='edited':ag.update(self.db,'a',item['id'],'knowledge',{**self.seed.LEGACY_PAYLOAD,'title':'user edited'})
                elif kind=='deleted':self.db.execute('UPDATE agriculture_entities SET deleted=1 WHERE id=?',(item['id'],))
                else:ag.insert(self.db,'a',self.seed.WORKSPACE,'knowledge',self.seed.LEGACY_PAYLOAD)
                before=self.db.serialize()
                with self.assertRaises(ag.AgricultureError):self.seed.install(self.db,'a',self.root,apply=True)
                self.assertEqual(before,self.db.serialize());self.db.execute('ROLLBACK TO independent_case');self.db.execute('RELEASE independent_case')
    def test_no_receipt_does_not_repair_and_wrong_scope_denied(self):
        item=self.legacy(False)
        self.seed.install(self.db,'a',self.root,apply=True)
        self.assertEqual(ag.read(self.db,'a',item['id'],'knowledge')['assetId'],None)
        with self.assertRaises(ag.AgricultureError):self.seed.install(self.db,'b',self.root,apply=True)
        with self.assertRaises(ag.AgricultureError):self.seed.install(self.db,'a',self.root,workspace=self.w,apply=True)
    def test_plan_to_apply_edit_fails_without_overwrite(self):
        from unittest.mock import patch
        item=self.legacy();real=self.seed.legacy_plan;calls=[]
        def edit_after_plan(*args):
            result=real(*args)
            if not calls:
                ag.update(self.db,'a',item['id'],'knowledge',{**self.seed.LEGACY_PAYLOAD,'title':'USER_EDIT_AFTER_PLAN'})
            calls.append(result);return result
        with patch.object(self.seed,'legacy_plan',side_effect=edit_after_plan):
            with self.assertRaises(ag.AgricultureError):self.seed.install(self.db,'a',self.root,apply=True)
        self.assertEqual(ag.read(self.db,'a',item['id'],'knowledge')['title'],'USER_EDIT_AFTER_PLAN')
        self.assertEqual(len(ag.entities(self.db,'a',self.seed.WORKSPACE,'knowledge')),1)
        self.assertEqual(ag.entities(self.db,'a',self.seed.WORKSPACE,'asset'),[])
