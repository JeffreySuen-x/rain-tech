"""Real isolated SQLite domain contracts; no provider or production data."""
import concurrent.futures
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import time
import unittest
import zipfile
import zlib
from server import agriculture as a
from server import agriculture_materials as m

BASE = '''
CREATE TABLE users(id TEXT PRIMARY KEY);
CREATE TABLE workspaces(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id),name TEXT);
CREATE TABLE threads(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id),workspace_id TEXT REFERENCES workspaces(id));
CREATE TABLE turns(id TEXT PRIMARY KEY,owner TEXT,thread_id TEXT,workspace_id TEXT,status TEXT,payload TEXT,generation INTEGER DEFAULT 0,lease_until REAL,artifact_id TEXT);
CREATE TABLE artifacts(id TEXT PRIMARY KEY,owner TEXT,body TEXT,sources TEXT);
CREATE TABLE commands(owner TEXT,scope TEXT,key TEXT,digest TEXT,response TEXT,PRIMARY KEY(owner,scope,key));
INSERT INTO users VALUES('a'),('b');
INSERT INTO workspaces VALUES('w','a','Garden'),('w2','a','Other Garden'),('foreign','b','Other owner');
INSERT INTO threads VALUES('t','a','w'),('t2','a','w2'),('bt','b','foreign');
INSERT INTO commands VALUES('a','legacy','key','old-digest','{"kept":true}');
'''


def connect(path):
    db = sqlite3.connect(path, isolation_level=None, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    return db


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\x20\x40\x60')) + chunk(b'IEND', b'')


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'db.sqlite')
        self.root = Path(self.tmp.name) / 'assets'
        self.db = connect(self.path)
        self.db.executescript(BASE)
        a.migrate(self.db)
        self.plot = a.create_entity(self.db, 'a', 'w', 'plot', {'commandId': 'plot', 'name': '一号地', 'crop': '葡萄'})['plot']
    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()
    def document(self, key='doc', raw=b'temperature needs observation\nwater only after checking soil'):
        return a.upload(self.db, 'a', 'w', {'commandId': key, 'kind': 'document'}, raw, 'field.md', self.root)
    def task(self, key='task', **extra):
        return a.create_entity(self.db, 'a', 'w', 'work_item', {'commandId': key, 'title': '检查地块', 'plotId': self.plot['id'], **extra})['workItem']
    def device(self):
        return a.create_entity(self.db, 'a', 'w', 'device', {'commandId': 'device', 'name': 'Sensor', 'kind': 'sensor', 'plotId': self.plot['id'], 'staleAfterSeconds': 60, 'thresholds': {'humidity': {'max': 80}}})
    def event(self, device, key, at, value, **extra):
        return a.ingest_event(self.db, 'a', device, {'commandId': key, 'sourceEventId': key, 'observedAt': at, 'readings': [{'metric': 'humidity', 'value': value, 'unit': 'percent'}], 'source': 'test', **extra})
    def test_malformed_enum_values_are_domain_errors(self):
        device = self.device()['device']['id']
        for bad in ([], {}):
            calls = [
                lambda: a.upload(self.db, 'a', 'w', {'commandId': 'bad', 'kind': bad}, b'x', 'x.txt', self.root),
                lambda: a.export_report(self.db, 'a', 'w', {'commandId': 'bad', 'reportId': 'missing', 'format': bad}, self.root),
                lambda: self.event(device, 'bad', time.time(), 50, source=bad),
                lambda: self.event(device, 'bad', time.time(), 50, readings=[{'metric': bad, 'value': 50, 'unit': 'percent'}]),
                lambda: a.create_entity(self.db, 'a', 'w', 'device', {'commandId': 'bad', 'name': 'sensor', 'plotId': self.plot['id'], 'kind': bad}),
            ]
            for call in calls:
                with self.subTest(value=bad, call=call), self.assertRaises(a.AgricultureError):
                    call()

    def test_migration_backup_reapply_future_version_preserves_legacy(self):
        a.migrate(self.db)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0], 2)
        self.assertEqual(self.db.execute("SELECT response FROM commands WHERE scope='legacy'").fetchone()[0], '{"kept":true}')
        backup = connect(str(Path(self.tmp.name) / 'backup.sqlite'))
        self.db.backup(backup)
        self.assertEqual(backup.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(backup.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(backup.execute('SELECT COUNT(*) FROM agriculture_entities').fetchone()[0], 1)
        backup.close()
        self.db.execute('UPDATE agriculture_schema_meta SET version=99')
        with self.assertRaises(RuntimeError):
            a.migrate(self.db)
        self.assertEqual(self.db.execute('SELECT version FROM agriculture_schema_meta').fetchone()[0], 99)
    def test_cross_owner_and_workspace_relations(self):
        uploaded = self.document()
        device = self.device()['device']
        task = self.task()
        report = a.create_entity(self.db, 'a', 'w', 'report', {'commandId': 'r'})['report']
        for kind, identifier in [('plot', self.plot['id']), ('asset', uploaded['asset']['id']), ('knowledge', uploaded['knowledge']['id']), ('device', device['id']), ('work_item', task['id']), ('report', report['id'])]:
            with self.assertRaises(a.AgricultureError) as error:
                a.read(self.db, 'b', identifier, kind)
            self.assertEqual(error.exception.status, 404)
            with self.assertRaises(a.AgricultureError):
                a.read(self.db, 'a', identifier, kind, 'w2')
        with self.assertRaises(a.AgricultureError):
            a.create_entity(self.db, 'a', 'w2', 'work_item', {'commandId': 'foreign', 'title': 'x', 'plotId': self.plot['id']})
    def test_upload_source_learning_revoke_and_no_original_path_exposure(self):
        value = self.document()
        self.assertNotIn('storageKey', value['asset'])
        path, asset = a.asset_content(self.db, 'a', value['asset']['id'], self.root)
        self.assertEqual(path.read_bytes(), b'temperature needs observation\nwater only after checking soil')
        snapshot = a.snapshot_context(self.db, 'a', 'w', {'knowledgeIds':[value['knowledge']['id']]})
        self.assertTrue(a.validate_context(self.db, 'a', 'w', snapshot))
        turn = {'owner': 'a', 'workspace_id': 'w', 'payload': a.encode({'agricultureContext': snapshot})}
        found = a.execute_tool(self.db, turn, 'search_knowledge', {'query': 'temperature'}, 'operation')
        self.assertEqual(found['sources'][0]['sourceHash'], value['knowledge']['sourceHash'])
        self.assertEqual(found['sources'][0]['locator'], 'L1')
        record = a.learn(self.db, 'a', value['knowledge']['id'], {'commandId': 'learning', 'answer': '我会先检查土壤'})['learningRecord']
        self.assertEqual(record['answer'], '我会先检查土壤')
        a.revoke_asset(self.db, 'a', value['asset']['id'])
        with self.assertRaises(a.AgricultureError) as error:
            a.validate_context(self.db, 'a', 'w', snapshot)
        self.assertEqual(error.exception.code, 'asset_revoked')
        with self.assertRaises(a.AgricultureError):
            a.asset_content(self.db, 'a', value['asset']['id'], self.root)
        self.assertTrue(path.exists(), 'revocation must not falsely claim deletion of all historical originals')
    def test_document_image_validation_and_atomic_failures(self):
        self.assertEqual(m.validate_png(png()), 'image/png')
        with self.assertRaises(a.AgricultureError):
            m.validate_png(png()[:-3])
        with self.assertRaises(a.AgricultureError):
            m.validate_png(b'<svg><script/></svg>')
        with self.assertRaises(a.AgricultureError):
            self.document('bad', b'\xff\xfe\x00')
        out = BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('word/document.xml', 'x' * 2000000)
        with self.assertRaises(a.AgricultureError):
            a.upload(self.db, 'a', 'w', {'commandId': 'bomb', 'kind': 'document'}, out.getvalue(), 'bomb.docx', self.root)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM agriculture_entities WHERE kind='asset'").fetchone()[0], 0)
        image = a.upload(self.db, 'a', 'w', {'commandId': 'png', 'kind': 'image'}, png(), 'photo.png', self.root)['asset']
        self.assertEqual(image['status'], 'stored')
        self.assertNotIn('analysis', image)
    def test_common_photo_decoding_damage_bomb_and_pdf_text(self):
        from PIL import Image
        for fmt, name, mime in [('JPEG', 'phone.jpg', 'image/jpeg'), ('WEBP', 'phone.webp', 'image/webp'), ('PNG', 'phone.png', 'image/png')]:
            output = BytesIO()
            Image.new('RGB', (8, 5), color=(30, 100, 50)).save(output, format=fmt)
            raw = output.getvalue()
            self.assertEqual(m.validate_image(raw), mime)
            value = a.upload(self.db, 'a', 'w', {'commandId': name, 'kind': 'image'}, raw, name, self.root)['asset']
            self.assertEqual(value['mediaType'], mime)
            with self.assertRaises(a.AgricultureError):
                m.validate_image(raw[:20])
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
        bomb = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 5001, 5001, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'')) + chunk(b'IEND', b'')
        with self.assertRaises(a.AgricultureError):
            m.validate_image(bomb)
        # A real PDF text stream with offsets/xref, rather than mocking parser.
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
        stream = b'BT /F1 12 Tf 10 150 Td (Field observation) Tj ET'
        objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
        pdf, offsets = b'%PDF-1.4\n', [0]
        for i, obj in enumerate(objects, 1):
            offsets.append(len(pdf))
            pdf += str(i).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
        start = len(pdf)
        pdf += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(f'{n:010} 00000 n \n'.encode() for n in offsets[1:]) + b'trailer << /Size 6 /Root 1 0 R >>\nstartxref\n' + str(start).encode() + b'\n%%EOF'
        excerpts, warnings = m.extract(pdf, 'field.pdf')
        self.assertIn('Field observation', excerpts[0]['text'])
        self.assertEqual(excerpts[0]['locator'], 'page:1')

    def test_command_conflict_and_real_concurrent_idempotency(self):
        value = {'commandId': 'same', 'title': 'check'}
        first = a.create_entity(self.db, 'a', 'w', 'work_item', value)
        self.assertEqual(first, a.create_entity(self.db, 'a', 'w', 'work_item', value))
        with self.assertRaises(a.AgricultureError) as error:
            a.create_entity(self.db, 'a', 'w', 'work_item', {**value, 'title': 'changed'})
        self.assertEqual(error.exception.status, 409)
        def create_concurrently(_):
            db = connect(self.path)
            try:
                return a.create_entity(db, 'a', 'w', 'work_item', {'commandId': 'parallel', 'title': 'parallel'})['workItem']['id']
            finally:
                db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            ids = list(pool.map(create_concurrently, range(12)))
        self.assertEqual(len(set(ids)), 1)
    def test_device_duplicate_order_offline_recovery_and_token_once(self):
        result = self.device()
        dev, token = result['device'], result['ingestToken']
        replay = self.device()
        self.assertNotIn('ingestToken', replay)
        self.assertEqual(a.device_token_owner(self.db, dev['id'], token), 'a')
        self.assertNotIn(token, self.db.execute("SELECT response FROM commands WHERE scope=?", ('agriculture:device:w',)).fetchone()[0])
        at = time.time() - 5
        first = self.event(dev['id'], 'e1', at, 90)
        self.assertEqual(len(first['alerts']), 1)
        self.assertTrue(self.event(dev['id'], 'e1-retry', at, 90, sourceEventId='e1')['duplicate'])
        with self.assertRaises(a.AgricultureError):
            self.event(dev['id'], 'conflict', at, 20, sourceEventId='e1')
        self.event(dev['id'], 'old', at - 100, 20)
        self.assertEqual(a.read(self.db, 'a', dev['id'], 'device')['latest']['humidity']['value'], 90)
        self.assertEqual(a.public(a.read(self.db, 'a', dev['id'], 'device'), at=at+100)['connectionStatus'], 'unconnected')
        restored = self.event(dev['id'], 'normal', at+1, 50)
        self.assertEqual(restored['alerts'][0]['status'], 'resolved')
        new = self.event(dev['id'], 'again', at+2, 95)
        self.assertNotEqual(new['alerts'][0]['id'], first['alerts'][0]['id'])
        observations = a.device_readings(self.db, 'a', dev['id'])['observations']
        self.assertEqual([o['observedAt'] for o in observations], sorted(o['observedAt'] for o in observations))
        with self.assertRaises(a.AgricultureError):
            self.event(dev['id'], 'nan', at, float('nan'))
    def test_manual_measurements_never_establish_or_refresh_device_presence(self):
        dev = self.device()['device']
        at = time.time() - 10
        result = self.event(dev['id'], 'manual', at, 90)
        self.assertEqual(result['observations'][0]['source'], 'test')
        self.assertEqual(result['alerts'][0]['status'], 'open')
        stored = a.read(self.db, 'a', dev['id'], 'device')
        self.assertIsNone(stored['lastSeenAt'])
        self.assertEqual(a.public(stored, at=at+1)['connectionStatus'], 'unconnected')
        self.event(dev['id'], 'hardware', at+1, 60, source='device')
        stored = a.read(self.db, 'a', dev['id'], 'device')
        self.assertEqual(stored['lastSeenAt'], at+1)
        self.assertEqual(a.public(stored, at=at+2)['connectionStatus'], 'online')
        self.event(dev['id'], 'manual-later', at+2, 85)
        stored = a.read(self.db, 'a', dev['id'], 'device')
        self.assertEqual(stored['lastSeenAt'], at+1)
        self.assertEqual(stored['latest']['humidity']['source'], 'test')
        self.assertEqual(a.public(stored, at=at+100)['connectionStatus'], 'offline')
        self.event(dev['id'], 'old-hardware', at-10, 50, source='device')
        self.assertEqual(a.read(self.db, 'a', dev['id'], 'device')['lastSeenAt'], at+1)
        # Old saved test-only state must also stop claiming hardware presence.
        legacy = {**stored, 'source': 'test', 'lastSeenAt': at+2}
        legacy.pop('lastDeviceSeenAt')
        self.assertIsNone(a.public(legacy, at=at+3)['lastSeenAt'])
        self.assertEqual(a.public(legacy, at=at+3)['connectionStatus'], 'unconnected')

    def test_completion_report_learning_and_office_roundtrip(self):
        task = self.task()
        done = a.complete_item(self.db, 'a', task['id'], {'commandId': 'done', 'note': '已实地检查，叶片无新增斑点'})
        replay = a.complete_item(self.db, 'a', task['id'], {'commandId': 'done2', 'note': '重复完成'})
        self.assertEqual(done['record']['id'], replay['record']['id'])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM agriculture_entities WHERE kind='activity_record'").fetchone()[0], 1)
        report = a.create_entity(self.db, 'a', 'w', 'report', {'commandId': 'report', 'workItemIds': [task['id']]})['report']
        self.assertIn('已实地检查', report['body'])
        self.assertEqual(report['sources'][0]['id'], done['record']['id'])
        for fmt in ('docx', 'pptx'):
            exported = a.export_report(self.db, 'a', 'w', {'commandId': fmt, 'reportId': report['id'], 'format': fmt}, self.root)['asset']
            path, _ = a.asset_content(self.db, 'a', exported['id'], self.root)
            segments, warnings = m.extract(path.read_bytes(), 'report.' + fmt)
            self.assertIn('已实地检查', '\n'.join(e['text'] for e in segments))
    def test_unknown_or_cancelled_previous_followup_never_enqueues_next(self):
        task = self.task()
        a.configure_followup(self.db, 'a', task['id'], {'commandId': 'enable', 'threadId': 't', 'enabled': True, 'nextDueAt': 100, 'maxRuns': 2, 'intervalSeconds': 60, 'maxModelCalls': 1})
        def enqueue(db, owner, tid, payload, command_id, scope):
            db.execute('INSERT INTO turns(id,owner,thread_id,workspace_id,status,payload) VALUES(?,?,?,?,?,?)', ('unknown', owner, tid, 'w', 'queued', a.encode(payload)))
            return {'turn': {'id': 'unknown'}}
        self.assertEqual(a.due_followups(self.db, 100, enqueue), 1)
        self.db.execute("UPDATE turns SET status='needs_review' WHERE id='unknown'")
        self.assertEqual(a.due_followups(self.db, 300, lambda *args: self.fail('unknown result was resent')), 0)
        follow = a.entities(self.db, 'a', 'w', 'follow_up')[0]
        self.assertFalse(follow['enabled'])
        self.assertEqual(follow['status'], 'needs_review')

    def test_followup_authorization_scan_restart_budget_disable(self):
        task = self.task(followUpAt=10)
        follow = a.entities(self.db, 'a', 'w', 'follow_up')[0]
        self.assertFalse(follow['enabled'])
        queued = []
        def enqueue(db, owner, tid, payload, command_id, scope):
            identifier = 'turn-' + str(len(queued))
            db.execute('INSERT INTO turns(id,owner,thread_id,workspace_id,status,payload) VALUES(?,?,?,?,?,?)', (identifier, owner, tid, 'w', 'queued', a.encode(payload)))
            queued.append(payload)
            return {'turn': {'id': identifier, 'status': 'queued'}}
        self.assertEqual(a.due_followups(self.db, 100, enqueue), 0)
        configured = a.configure_followup(self.db, 'a', task['id'], {'commandId': 'enable', 'threadId': 't', 'enabled': True, 'nextDueAt': 100, 'maxRuns': 2, 'intervalSeconds': 60, 'maxModelCalls': 3})['followUp']
        self.assertEqual(a.due_followups(self.db, 100, enqueue), 1)
        self.assertEqual(a.due_followups(self.db, 100, enqueue), 0)
        self.db.close()
        self.db = connect(self.path)
        self.assertEqual(a.due_followups(self.db, 160, enqueue), 1)
        self.assertEqual(a.due_followups(self.db, 300, enqueue), 0)
        self.assertEqual(len(queued), 2)
        self.assertEqual(queued[0]['budget']['maxModelCalls'], 3)
        snapshot = queued[0]['agricultureContext']
        a.configure_followup(self.db, 'a', task['id'], {'commandId': 'disable', 'threadId': 't', 'enabled': False})
        self.assertTrue(all(r['status'] == 'cancelled' for r in self.db.execute('SELECT status FROM turns')))
        with self.assertRaises(a.AgricultureError):
            a.validate_context(self.db, 'a', 'w', snapshot)
        self.assertEqual(a.due_followups(self.db, 500, enqueue), 0)


if __name__ == '__main__':
    unittest.main()
