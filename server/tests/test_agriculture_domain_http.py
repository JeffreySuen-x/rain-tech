"""Exercise real Flask routes, sessions/CSRF and SQLite domain persistence."""
from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from server.app import create_app, connect
from server.tests.test_agriculture_domain import png


class AgricultureHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'DB_PATH': str(Path(self.tmp.name) / 'db'), 'PRODUCTION': False, 'PUBLIC_ORIGIN': 'http://localhost:6480', 'ASSET_ROOT': str(Path(self.tmp.name) / 'assets')})
        self.db = connect(self.app.config['DB_PATH'])
        self.clients = {}
        for owner in ('a', 'b'):
            self.db.execute('INSERT INTO users VALUES(?,?,?)', (owner, owner, 'unused'))
            self.db.execute('INSERT INTO workspaces VALUES(?,?,?)', (owner + '-w', owner, owner + ' Garden'))
            self.db.execute('INSERT INTO threads VALUES(?,?,?,?)', (owner + '-t', owner, owner + '-w', 'Farm conversation'))
            raw = owner + '-synthetic-cookie'
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashlib.sha256(raw.encode()).hexdigest(), owner, owner + '-csrf', time.time()+600))
            client = self.app.test_client()
            client.set_cookie('shuyu_session', raw)
            self.clients[owner] = client
        self.a = self.clients['a']
        self.b = self.clients['b']
    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()
    def post(self, path, data, status=201, owner='a'):
        response = self.clients[owner].post('/api/v1' + path, json=data, headers={'X-CSRF-Token': owner + '-csrf'})
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        return response.get_json()
    def upload(self, data=None, name='field.md', kind='document', key='upload'):
        response = self.a.post('/api/v1/workspaces/a-w/assets', data={'commandId': key, 'kind': kind, 'file': (BytesIO(data or b'Water observations\nField log'), name)}, headers={'X-CSRF-Token': 'a-csrf'})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()
    def test_real_routes_import_complete_report_export_and_ownership(self):
        plot = self.post('/workspaces/a-w/plots', {'commandId': 'plot', 'name': '一号地'})['plot']
        value = self.upload()
        task = self.post('/workspaces/a-w/work-items', {'commandId': 'task', 'title': '检查地块', 'plotId': plot['id']})['workItem']
        self.post('/work-items/' + task['id'] + '/complete', {'commandId': 'done', 'note': '已检查土壤', 'assetIds': [value['asset']['id']]}, status=200)
        report = self.post('/workspaces/a-w/reports', {'commandId': 'report', 'workItemIds': [task['id']]})['report']
        exported = self.post('/workspaces/a-w/exports', {'commandId': 'export', 'reportId': report['id'], 'format': 'docx'})['asset']
        downloaded = self.a.get(exported['contentUrl'])
        self.assertEqual(downloaded.status_code, 200)
        self.assertTrue(downloaded.data.startswith(b'PK'))
        self.assertEqual(downloaded.headers['Cache-Control'], 'no-store')
        self.assertEqual(downloaded.headers['X-Content-Type-Options'], 'nosniff')
        downloaded.close()
        for path in ('/workspaces/a-w/agriculture', value['asset']['contentUrl'].removeprefix('/api/v1'), '/knowledge/' + value['knowledge']['id'], '/reports/' + report['id']):
            self.assertEqual(self.b.get('/api/v1' + path).status_code, 404)
        overview = self.a.get('/api/v1/workspaces/a-w/agriculture').json
        self.assertEqual(overview['workItems'][0]['status'], 'completed')
        self.assertEqual(len(overview['records']), 1)
        self.assertEqual(overview['summary']['knowledgeCount'], 1)
    def test_device_token_scope_csrf_origin_and_no_secret_replay(self):
        plot = self.post('/workspaces/a-w/plots', {'commandId': 'p', 'name': 'Plot'})['plot']
        request = {'commandId': 'd', 'name': 'Device', 'kind': 'sensor', 'plotId': plot['id']}
        result = self.post('/workspaces/a-w/devices', request)
        self.assertNotIn('ingestToken', self.post('/workspaces/a-w/devices', request))
        dev, token = result['device']['id'], result['ingestToken']
        anon = self.app.test_client()
        payload = {'commandId': 'e', 'sourceEventId': 'source-1', 'observedAt': time.time(), 'readings': [{'metric': 'temperature', 'value': 25, 'unit': 'celsius'}], 'source': 'device'}
        url = '/api/v1/devices/' + dev + '/events'
        headers = {'Authorization': 'Bearer ' + token}
        response = anon.post(url, json=payload, headers=headers)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(response.json['observations'][0]['source'], 'device')
        self.assertEqual(anon.get('/api/v1/devices/' + dev + '/readings', headers=headers).status_code, 401)
        self.assertEqual(anon.post(url, json=payload, headers={'Authorization': 'Bearer invalid'}).status_code, 401)
        self.assertEqual(anon.post(url, json=payload, headers={**headers, 'Origin': 'https://evil.test'}).status_code, 403)
        self.assertEqual(self.a.post(url, json={**payload, 'source': 'test'}).status_code, 403)
        self.assertEqual(self.b.post(url, json={**payload, 'source': 'test'}, headers={'X-CSRF-Token': 'b-csrf'}).status_code, 404)
    def test_photo_original_media_failure_and_revocation(self):
        image = self.upload(png(), 'photo.png', 'image')['asset']
        response = self.post('/assets/' + image['id'] + '/analyze', {'commandId': 'analyze', 'threadId': 'a-t'}, status=202)
        turn = response['turn']['id']
        from server.app import run_once
        run_once(self.app)
        failed = self.a.get('/api/v1/turns/' + turn).json
        self.assertEqual(failed['turn']['status'], 'failed')
        self.assertIn(failed['turn']['error']['code'], {'provider_unconfigured', 'capability_unconfigured'})
        original = self.a.get(image['contentUrl'])
        self.assertEqual(original.status_code, 200)
        original.close()
        self.assertEqual(self.b.delete('/api/v1/assets/' + image['id'], headers={'X-CSRF-Token': 'b-csrf'}).status_code, 404)
        self.assertEqual(self.a.delete('/api/v1/assets/' + image['id'], headers={'X-CSRF-Token': 'a-csrf'}).status_code, 204)
        self.assertEqual(self.a.get(image['contentUrl']).status_code, 404)
    def test_real_media_old_replay_cannot_replace_latest_and_enqueue_is_atomic(self):
        from server.app import run_once
        from server import agriculture
        from server.tests.test_agent_runtime import AgentRuntimeTests
        from unittest.mock import patch
        image = self.upload(png(), 'photo.png', 'image')['asset']
        endpoint = '/assets/' + image['id'] + '/analyze'
        requests = []
        with AgentRuntimeTests.http(self, lambda calls: AgentRuntimeTests.answer(self, '分析结果' + str(len(calls)))) as calls:
            first = self.post(endpoint, {'commandId': 'a1', 'threadId': 'a-t'}, status=202)
            self.assertTrue(run_once(self.app))
            second = self.post(endpoint, {'commandId': 'a2', 'threadId': 'a-t'}, status=202)
            self.assertTrue(run_once(self.app))
            before = agriculture.read(self.db, 'a', image['id'], 'asset')
            self.assertEqual(before['processingTurnId'], second['turn']['id'])
            self.assertEqual(before['analysis']['text'], '分析结果2')
            self.assertEqual(first, self.post(endpoint, {'commandId': 'a1', 'threadId': 'a-t'}, status=202))
            displayed = self.a.get('/api/v1/workspaces/a-w/assets').json['assets'][0]
            self.assertEqual(displayed['processingTurnId'], second['turn']['id'])
            self.assertEqual(displayed['analysis']['text'], '分析结果2')
            self.assertEqual(len(calls), 2)
            # Also protect older deployments' runtime-only command receipts.
            self.db.execute('DELETE FROM commands WHERE owner=? AND scope=? AND key=?', ('a', 'agriculture:media-pointer:' + image['id'] + ':analyze', 'a1'))
            self.assertEqual(first, self.post(endpoint, {'commandId': 'a1', 'threadId': 'a-t'}, status=202))
            self.assertEqual(agriculture.read(self.db, 'a', image['id'], 'asset')['processingTurnId'], second['turn']['id'])
            self.post(endpoint, {'commandId': 'a1', 'threadId': 'a-t', 'prompt': 'changed'}, status=409)
            self.app.testing = True
            with patch.object(agriculture, 'update', side_effect=RuntimeError('synthetic pointer write failure')):
                with self.assertRaises(RuntimeError):
                    self.post(endpoint, {'commandId': 'a3', 'threadId': 'a-t'}, status=202)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM turns').fetchone()[0], 2)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM commands WHERE key=?', ('a3',)).fetchone()[0], 0)
            self.assertEqual(agriculture.read(self.db, 'a', image['id'], 'asset')['processingTurnId'], second['turn']['id'])

    def test_forged_internal_admission_and_cross_workspace_followup_rejected(self):
        self.post('/threads/a-t/turns', {'commandId': 'bad', 'prompt': 'x', 'followUp': {'id': 'fake'}, 'agricultureContext': {'workspaceId': 'b-w'}}, status=400)
        task = self.post('/workspaces/a-w/work-items', {'commandId': 'task', 'title': 'Task'})['workItem']
        self.post('/work-items/' + task['id'] + '/follow-up', {'commandId': 'foreign', 'threadId': 'b-t', 'enabled': True, 'nextDueAt': time.time(), 'maxRuns': 1, 'maxModelCalls': 1}, status=404)
        source = self.upload()['knowledge']
        self.post('/knowledge/' + source['id'] + '/learning', {'commandId': 'learn', 'answer': '先核对实际情况'})
        self.post('/knowledge/' + source['id'] + '/learning', {'commandId': 'invalid', 'answer': None}, status=400)


if __name__ == '__main__':
    unittest.main()
