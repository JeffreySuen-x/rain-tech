"""Independent real HTTP collection redaction and persistence acceptance."""
import unittest
from unittest.mock import patch
from server.tests import test_agriculture_domain_http as fixtures
from server import agriculture as a, agriculture_reports as r
class IndependentCollection(unittest.TestCase):
    setUp=fixtures.AgricultureHTTPTests.setUp
    tearDown=fixtures.AgricultureHTTPTests.tearDown
    upload=fixtures.AgricultureHTTPTests.upload
    post=fixtures.AgricultureHTTPTests.post
    def test_all_unavailable_then_mixed_exact_redaction_and_history(self):
        uploaded=self.upload();k=uploaded['knowledge']
        hidden=a.insert(self.db,'a','a-w','report',{'title':'SECRET-TITLE','body':'SECRET-BODY','document':{'secret':'SECRET-DOCUMENT'},'sources':[{'kind':'knowledge','id':k['id'],'sourceHash':k['sourceHash'],'excerpt':'SECRET-SOURCE'}]})
        before=self.db.execute('SELECT payload FROM agriculture_entities WHERE id=?',(hidden['id'],)).fetchone()[0]
        a.revoke_asset(self.db,'a',uploaded['asset']['id'])
        for mixed in (False,True):
            if mixed:good=self.post('/workspaces/a-w/reports',{'commandId':'good'})['report']
            for endpoint in ('agriculture','reports'):
                response=self.a.get('/api/v1/workspaces/a-w/'+endpoint);self.assertEqual(response.status_code,200)
                rows=response.json['reports'];self.assertEqual(len(rows),2 if mixed else 1)
                redacted=next(v for v in rows if v['id']==hidden['id'])
                self.assertEqual(set(redacted),{'id','createdAt','title','unavailable','reason'})
                self.assertEqual(redacted['title'],'来源不可用的报告');self.assertTrue(redacted['unavailable'])
                self.assertNotIn('SECRET',response.get_data(as_text=True));self.assertNotIn(k['sourceHash'],response.get_data(as_text=True))
                if mixed:self.assertEqual(next(v for v in rows if v['id']==good['id'])['document']['schemaVersion'],'agriculture.report.v1')
            self.assertEqual(self.a.get('/api/v1/reports/'+hidden['id']).status_code,409)
            self.post('/workspaces/a-w/exports',{'commandId':'bad-export-'+str(mixed),'reportId':hidden['id'],'format':'pptx'},status=409)
        self.assertEqual(self.db.execute('SELECT payload FROM agriculture_entities WHERE id=?',(hidden['id'],)).fetchone()[0],before)
        self.assertEqual(self.b.get('/api/v1/workspaces/a-w/reports').status_code,404)
    def test_only_revocation_error_can_be_placeholder(self):
        for error in (a.AgricultureError('not_found','x',404),a.AgricultureError('unexpected','x',500),RuntimeError('unexpected')):
            with patch.object(r,'present',side_effect=error):
                with self.assertRaises(type(error)):r.present_collection(self.db,'a',{'id':'x','createdAt':1},None)
