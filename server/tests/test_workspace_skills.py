"""Original isolated product contracts; fake/local only."""
import copy
import json
import unittest
from pathlib import Path

_SEED_DIR = Path(__file__).resolve().parents[2] / 'docs/knowledge/grape'
_SEED_OK = _SEED_DIR.is_dir()
_SKIP_SEED = unittest.skipUnless(_SEED_OK, 'requires docs/knowledge/grape originals')
from unittest.mock import patch
import test_server as baseline
from server import skill, agriculture as a, agent_runtime
from server.workspace_seed import install, WORKSPACE, LEGACY_PAYLOAD, LEGACY_KEY

class SkillTests(baseline.ServerTests):
    # Avoid inheriting/repeating the baseline test suite.
    def test_catalog_and_request_rejections(self):
        catalog = self.a.get('/api/v1/skills').json['skills']
        self.assertEqual({item['id'] for item in catalog}, {
            'shuyu.analyze.v1', 'shuyu.inspection.v1', 'shuyu.knowledge.v1', 'shuyu.plan.v1',
            'shuyu.report.v1', 'shuyu.image.v1', 'shuyu.audio.v1',
        })
        for value in ('unknown',[], 'shuyu.image.v1'):
            self.post('/threads/'+self.t+'/turns',dict(commandId='bad',prompt='x',skillId=value),status=400)
        for key in ('systemPrompt','skillPolicy','allowedToolNames'):
            self.post('/threads/'+self.t+'/turns',{'commandId':'bad','prompt':'x',key:{}},status=400)
    def test_frozen_policy_and_command_conflict(self):
        body=dict(commandId='skill',prompt='x',skillId='shuyu.knowledge.v1')
        tid=self.post('/threads/'+self.t+'/turns',body,status=202)['turn']['id']
        payload=json.loads(self.db.execute('SELECT payload FROM turns WHERE id=?',(tid,)).fetchone()[0])
        self.assertEqual(skill.frozen_policy(payload)['allowedToolNames'],['search_knowledge','read_source','read_asset_analysis'])
        with patch.dict(skill.CATALOG['shuyu.knowledge.v1'],allowedToolNames=[]):
            self.assertEqual(len(skill.frozen_policy(payload)['allowedToolNames']),3)
        self.post('/threads/'+self.t+'/turns',{**body,'skillId':skill.SKILL_ID},status=409)
        turn=dict(owner='a',workspace_id=self.w,payload=payload)
        with self.assertRaises(a.AgricultureError):a.execute_tool(self.db,turn,'create_report',{},'x')
        for mutation in ({'instruction':'override'}, {'allowedToolNames':['create_report']}):
            corrupt=copy.deepcopy(payload);corrupt['skillPolicy'].update(mutation)
            with self.assertRaises(ValueError):skill.frozen_policy(corrupt)
        self.assertEqual(len(skill.frozen_policy({})['allowedToolNames']),7)
        with self.assertRaises(ValueError):skill.frozen_policy({'skillId':'unknown'})
    @_SKIP_SEED
    def test_seed_original_asset_idempotency_and_revoke(self):
        self.db.execute('INSERT INTO workspaces VALUES(?,?,?)',(WORKSPACE,'a','target'))
        from pathlib import Path

        root=Path(self.tmp.name)/'seed-assets'
        self.assertTrue(install(self.db,'a',root)['dryRun'])
        self.assertEqual(a.entities(self.db,'a',WORKSPACE,'knowledge'),[])
        install(self.db,'a',root,apply=True);before=self.db.total_changes
        install(self.db,'a',root,apply=True);self.assertEqual(before,self.db.total_changes)
        knowledge=a.entities(self.db,'a',WORKSPACE,'knowledge');self.assertEqual(len(knowledge),6)
        for item in knowledge:
            path,asset=a.asset_content(self.db,'a',item['assetId'],root)
            self.assertTrue(path.read_text());self.assertTrue(item['excerpts'])
            self.assertEqual(item['title'],path.read_text().splitlines()[0][2:].strip())
            self.assertEqual(asset['name'],item['title']+'.md');self.assertEqual(item['version'],1)
        with self.assertRaises(a.AgricultureError):install(self.db,'b',root)
        with self.assertRaises(a.AgricultureError):install(self.db,'a',root,workspace=self.w)
        a.revoke_asset(self.db,'a',knowledge[0]['assetId'])
        with self.assertRaises(a.AgricultureError):install(self.db,'a',root,apply=True)

    @_SKIP_SEED
    def test_legacy_repair_preserves_id_and_rejects_edited(self):
        from pathlib import Path
        self.db.execute('INSERT INTO workspaces VALUES(?,?,?)',(WORKSPACE,'a','target'))
        root=Path(self.tmp.name)/'legacy-assets'
        old=a.insert(self.db,'a',WORKSPACE,'knowledge',LEGACY_PAYLOAD)
        receipt={'workspaceId':WORKSPACE,'sourceDigest':'a'*64}
        self.db.execute('INSERT INTO commands VALUES(?,?,?,?,?)',('a','offline-demo-restore-v1',WORKSPACE,'a'*64,a.encode(receipt)))
        plan=install(self.db,'a',root);self.assertEqual(plan['legacySeed']['id'],old['id'])
        install(self.db,'a',root,apply=True)
        item=a.read(self.db,'a',old['id'],'knowledge',WORKSPACE)
        self.assertEqual(item['version'],2);self.assertTrue(item['assetId']);self.assertNotEqual(item['sourceHash'],old['sourceHash'])
        self.assertEqual(len(a.entities(self.db,'a',WORKSPACE,'knowledge')),7)
        self.assertEqual(install(self.db,'a',root,apply=True)['legacySeed']['state'],'unchanged')
        a.revoke_asset(self.db,'a',item['assetId'])
        with self.assertRaises(a.AgricultureError):install(self.db,'a',root,apply=True)

# Keep only the newly declared tests; baseline executes separately.
for _name in dir(baseline.ServerTests):
    if _name.startswith('test_') and _name not in SkillTests.__dict__:setattr(SkillTests,_name,None)
