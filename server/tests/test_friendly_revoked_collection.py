"""Implementation regression for revoked-report collection isolation."""
import unittest
from unittest.mock import patch
from server.tests import test_agriculture_domain_http as fixtures
from server import agriculture as a, agriculture_reports as reports

class RevokedCollection(unittest.TestCase):
    setUp=fixtures.AgricultureHTTPTests.setUp
    tearDown=fixtures.AgricultureHTTPTests.tearDown
    post=fixtures.AgricultureHTTPTests.post
    upload=fixtures.AgricultureHTTPTests.upload

    def test_revoked_report_is_redacted_in_collections_but_strict_individually(self):
        imported=self.upload()
        knowledge=imported['knowledge']
        restricted=a.insert(self.db,'a','a-w','report',dict(title='秘密旧标题',body='秘密正文',document={'secret':'不得披露'},sources=[{'kind':'knowledge','id':knowledge['id'],'version':knowledge['version'],'sourceHash':knowledge['sourceHash']}]))
        good=self.post('/workspaces/a-w/reports',{'commandId':'good-report'})['report']
        before=a.read(self.db,'a',restricted['id'],'report')
        a.revoke_asset(self.db,'a',imported['asset']['id'])
        for path in ('/api/v1/workspaces/a-w/agriculture','/api/v1/workspaces/a-w/reports'):
            response=self.a.get(path)
            self.assertEqual(response.status_code,200,response.get_data(as_text=True))
            rows=response.json['reports'];redacted=next(r for r in rows if r['id']==restricted['id'])
            self.assertEqual(set(redacted),{'id','createdAt','title','unavailable','reason'})
            self.assertEqual(redacted['title'],'来源不可用的报告');self.assertTrue(redacted['unavailable'])
            self.assertTrue(next(r for r in rows if r['id']==good['id'])['document'])
            self.assertNotIn('秘密',response.get_data(as_text=True))
        self.assertEqual(self.a.get('/api/v1/reports/'+restricted['id']).status_code,409)
        self.post('/workspaces/a-w/exports',{'commandId':'restricted-export','reportId':restricted['id'],'format':'docx'},status=409)
        self.assertEqual(self.a.get('/api/v1/reports/'+good['id']).status_code,200)
        self.assertEqual(a.read(self.db,'a',restricted['id'],'report'),before)

    def test_collection_does_not_swallow_other_errors(self):
        for code,status in (('not_found',404),('unexpected',500)):
            with patch.object(reports,'present',side_effect=a.AgricultureError(code,'failure',status)):
                with self.assertRaises(a.AgricultureError):reports.present_collection(self.db,'a',{'id':'r','createdAt':1},None)
