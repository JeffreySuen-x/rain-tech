"""Independent QA: generated fixtures only; no live database or credentials."""
import json
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from server.tests import test_demo_restore as fixtures
from server.local_config import load_config
from server import agriculture as ag
from server.demo_restore import SOURCE_WORKSPACE

class IndependentRestoreTests(unittest.TestCase):
    setUp = fixtures.DemoRestoreTests.setUp
    tearDown = fixtures.DemoRestoreTests.tearDown
    run_restore = fixtures.DemoRestoreTests.run_restore

    def target_snapshot(self):
        with sqlite3.connect(self.target) as db:
            return list(db.iterdump())

    def test_executable_turn_and_dangling_json_rejected_without_mutation(self):
        before = self.target_snapshot()
        with sqlite3.connect(self.source) as db:
            db.execute("UPDATE turns SET status='queued'")
        with self.assertRaises(ValueError): self.run_restore(apply=True)
        self.assertEqual(before, self.target_snapshot())
        with sqlite3.connect(self.source) as db:
            db.execute("UPDATE turns SET status='completed'")
            db.row_factory=sqlite3.Row
            ag.insert(db, 'old', SOURCE_WORKSPACE, 'knowledge', {'title':'invalid','assetId':'outside-workspace','sourceHash':'x','version':1,'excerpts':[]})
        with self.assertRaises(ValueError): self.run_restore(apply=True)
        self.assertEqual(before, self.target_snapshot())

    def test_frozen_sources_plain_id_cannot_escape_workspace(self):
        before=self.target_snapshot()
        with sqlite3.connect(self.source) as db:
            db.execute("UPDATE turns SET payload=? WHERE id='turn'",(json.dumps({'sources':{'assets':[{'id':'outside-workspace','version':1,'sourceHash':'x'}],'knowledge':[]}}),))
        with self.assertRaises(ValueError): self.run_restore(apply=True)
        self.assertEqual(before,self.target_snapshot())

    def test_source_identity_change_rejected_and_original_rows_untouched(self):
        self.run_restore(apply=True)
        after = self.target_snapshot()
        with sqlite3.connect(self.source) as db: db.execute("UPDATE turns SET result='changed source'")
        with self.assertRaises(ValueError): self.run_restore(apply=True)
        self.assertEqual(after, self.target_snapshot())

    def test_asset_symlink_and_public_destination_fail_closed(self):
        asset = self.assets/('a'*32)
        raw = asset.read_bytes(); asset.unlink()
        elsewhere=self.root/'elsewhere'; elsewhere.write_bytes(raw); asset.symlink_to(elsewhere)
        before = self.target_snapshot()
        with self.assertRaises(ValueError): self.run_restore(apply=True)
        self.assertEqual(before, self.target_snapshot())
        asset.unlink(); asset.write_bytes(raw)
        self.dest.mkdir(mode=0o755); self.dest.chmod(0o755)
        with self.assertRaises(ValueError): self.run_restore(apply=True)
        self.assertEqual(before, self.target_snapshot())

    def test_credentials_sessions_old_commands_not_imported(self):
        with sqlite3.connect(self.source) as db:
            db.row_factory=sqlite3.Row
            db.execute("INSERT INTO sessions VALUES('old-session','old','secret-csrf',9999999999)")
            db.execute("INSERT INTO commands VALUES('old','old-scope','old-key','old-digest','old-secret-response')")
            ag.insert(db,'old',SOURCE_WORKSPACE,'device',{'name':'old camera','kind':'camera','credentialHash':'never-copy-token','lastSeenAt':100,'lastDeviceSeenAt':100,'latest':{}})
        result=self.run_restore(apply=True)
        with sqlite3.connect(self.target) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            self.assertIsNone(db.execute("SELECT 1 FROM commands WHERE scope='old-scope'").fetchone())
            self.assertNotIn('never-copy-token','\n'.join(db.iterdump()))

    def test_frozen_whole_entity_hash_change_is_rejected(self):
        with sqlite3.connect(self.source) as db:
            db.row_factory=sqlite3.Row
            asset=ag.read(db,'old',self.asset,'asset')
            db.execute("UPDATE turns SET result=? WHERE id='turn'",(json.dumps({'sources':[{'id':self.asset,'sourceHash':ag.digest(asset)}]}),))
        before=self.target_snapshot()
        with self.assertRaisesRegex(ValueError,'frozen evidence hash'): self.run_restore(apply=True)
        self.assertEqual(before,self.target_snapshot())

    def test_backup_consistent_private_and_mock_readings(self):
        before = self.target_snapshot()
        result=self.run_restore(apply=True)
        backup=Path(result['backup'])
        self.assertEqual(backup.stat().st_mode&0o777,0o600)
        with sqlite3.connect(backup) as db: self.assertEqual(before,list(db.iterdump()))
        with sqlite3.connect(self.target) as db:
            db.row_factory=sqlite3.Row
            devices=ag.entities(db,'new',result['workspaceId'],'device')
            sensor=next(d for d in devices if '手工' in d['name'])
            self.assertEqual(sensor['latest']['temperature']['value'],24.6)
            self.assertEqual(sensor['latest']['humidity']['value'],84)
            self.assertEqual(sensor['latest']['temperature']['source'],'test')
            self.assertIsNone(sensor['lastDeviceSeenAt'])
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())

class IndependentConfigTests(unittest.TestCase):
    def test_bad_inputs_atomic_and_secret_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); p=root/'local.json'
            for content in ('{"SHUYU_PROVIDER_KEY":"SENTINEL","BAD":"SENTINEL"}', '{"SHUYU_ENV":"a","SHUYU_ENV":"b"}', '[]', '{"SHUYU_PROVIDER_KEY":42}', '{broken-SENTINEL'):
                p.write_text(content); p.chmod(0o600); env={'UNCHANGED':'yes'}
                with self.assertRaises(ValueError) as caught: load_config(p,env)
                self.assertNotIn('SENTINEL',str(caught.exception))
                self.assertEqual(env,{'UNCHANGED':'yes'})
            p.write_text('{"SHUYU_PROVIDER_KEY":"SENTINEL"}'); p.chmod(0o600)
            root.chmod(0o755)
            with self.assertRaises(ValueError): load_config(p,{})
            root.chmod(0o700)
            linked=root/'alias'; linked.symlink_to(root,target_is_directory=True)
            with self.assertRaises(ValueError): load_config(linked/'local.json',{})
