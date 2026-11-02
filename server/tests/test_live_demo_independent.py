"""Independent acceptance: temporary SQLite/files only; no service or provider."""
import json
import unittest
from server import agriculture as a, agriculture_live_demo as live
import test_live_demo as fixture


class IndependentLiveAcceptance(unittest.TestCase):
    setUp = fixture.LiveDemoTests.setUp
    tearDown = fixture.LiveDemoTests.tearDown
    act = fixture.LiveDemoTests.act

    def test_enable_is_explicit_idempotent_and_disabled_tick_is_readonly(self):
        before = self.db.serialize()
        live.enable_demo(self.db, 'a', 'w', 999, [])
        self.assertEqual(before, self.db.serialize())
        self.assertIsNone(live.view(self.db, 'a', 'w2', at=100))
        self.db.execute('UPDATE agriculture_live_demo SET enabled=0')
        before = self.db.serialize()
        live.advance(self.db, 999)
        self.assertEqual(before, self.db.serialize())
        self.assertIsNone(live.view(self.db, 'a', 'w', at=999))

    def test_clock_rollback_and_resume_never_fill_pause_history(self):
        before = self.db.serialize()
        live.advance(self.db, 50)
        self.assertEqual(before, self.db.serialize())
        self.act('demo.pause')
        live.advance(self.db, 9999)
        live.action(self.db, 'a', 'w', dict(commandId='resume-later', action='demo.resume'), self.root, 10000)
        self.assertEqual(live.view(self.db, 'a', 'w', at=10000)['observedAt'], 100)
        live.advance(self.db, 10005)
        facts = live.view(self.db, 'a', 'w', at=10005)
        self.assertEqual([x['observedAt'] for x in facts['samples']], [100, 10005])

    def test_capture_ring_and_original_bytes_are_preserved(self):
        original_path, original = a.asset_content(self.db, 'a', self.asset['id'], self.root)
        original_bytes = original_path.read_bytes()
        for index in range(14):
            self.act('camera.capture', 'independent-snap-'+str(index), cameraId='demo-camera-1')
        facts = live.view(self.db, 'a', 'w', at=110)
        self.assertEqual(len(facts['captures']), 12)
        self.assertEqual(len({x['assetId'] for x in facts['captures']}), 12)
        self.assertEqual(original_path.read_bytes(), original_bytes)
        self.assertEqual(a.read(self.db, 'a', original['id'], 'asset', 'w'), original)

    def test_device_filtered_tool_cannot_expand_plot_scope(self):
        device = a.create_entity(self.db, 'a', 'w', 'device', dict(commandId='independent-device', name='other sensor', kind='sensor', plotId=self.other))['device']
        snapshot = a.snapshot_context(self.db, 'a', 'w', dict(plotId=self.plot))
        turn = dict(owner='a', workspace_id='w', payload=dict(agricultureContext=snapshot))
        result = a.execute_tool(self.db, turn, 'read_observations', dict(deviceId=device['id']), 'independent-read')['data']
        self.assertEqual(result['devices'], [])
        self.assertNotIn('liveDemo', result)
        turn['payload']['processingKind'] = 'audio_transcription'
        with self.assertRaises(a.AgricultureError) as caught:
            a.execute_tool(self.db, turn, 'read_observations', {}, 'independent-media')
        self.assertEqual(caught.exception.status, 403)

    def test_revoked_capture_source_blocks_frozen_publish_and_analysis_tool(self):
        capture = self.act('camera.capture', 'independent-frozen-cap', cameraId='demo-camera-1')['captures'][0]
        snapshot = a.snapshot_context(self.db, 'a', 'w', dict(assetIds=[capture['assetId']]))
        self.assertEqual(next(s for s in snapshot['sources'] if s['id'] == capture['assetId'])['origin'], 'demo')
        self.db.execute('UPDATE agriculture_entities SET deleted=1 WHERE id=?', (self.asset['id'],))
        with self.assertRaises(a.AgricultureError) as caught:
            a.validate_context(self.db, 'a', 'w', snapshot)
        self.assertEqual(caught.exception.code, 'asset_revoked')
        turn = dict(owner='a', workspace_id='w', payload=dict(agricultureContext=snapshot))
        with self.assertRaises(a.AgricultureError) as caught:
            a.execute_tool(self.db, turn, 'read_asset_analysis', dict(assetId=capture['assetId']), 'independent-revoked')
        self.assertEqual(caught.exception.code, 'asset_revoked')
