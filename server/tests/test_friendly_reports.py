"""Implementation checks on disposable fixture; independent QA remains separate."""
from datetime import datetime
from zoneinfo import ZoneInfo
import copy
from io import BytesIO
import unittest
import zipfile
from unittest.mock import patch
from server.tests.test_agriculture_domain import DomainTests, png
from server import agriculture as a
from server import agriculture_reports as r
from server import agriculture_materials as m
from server.agriculture_calendar import presentation

class FriendlyReports(DomainTests):
    def test_freeze_exports_revocation_replay(self):
        task=self.task();device=self.device()['device'];self.event(device['id'],'friendly-event',__import__('time').time(),75)
        asset=a.upload(self.db,'a','w',{'commandId':'photo','kind':'image'},png(),'leaf.png',self.root)['asset']
        a.complete_item(self.db,'a',task['id'],{'commandId':'done','note':'人工巡视','assetIds':[asset['id']]})
        report=a.create_entity(self.db,'a','w','report',{'commandId':'report','workItemIds':[task['id']]},self.root)['report']
        frozen=copy.deepcopy(report['document'])
        self.assertEqual(frozen['schemaVersion'],'agriculture.report.v1');self.assertEqual(len(frozen['photos']),1);self.assertEqual(frozen['observations'][0]['source'],'test')
        self.event(device['id'],'friendly-later',__import__('time').time(),90)
        self.assertEqual(a.read(self.db,'a',report['id'],'report')['document'],frozen)
        for fmt in ('docx','pptx'):
            exported=a.export_report(self.db,'a','w',{'commandId':'export-'+fmt,'reportId':report['id'],'format':fmt},self.root)['asset']
            path,_=a.asset_content(self.db,'a',exported['id'],self.root)
            with zipfile.ZipFile(path) as archive:
                self.assertTrue(any('/media/' in name for name in archive.namelist()))
                self.assertIn('人工巡视', ''.join(archive.read(n).decode('utf8') for n in archive.namelist() if n.endswith('.xml')))
        a.revoke_asset(self.db,'a',asset['id'])
        self.assertFalse(r.present(self.db,'a',report,self.root)['document']['photos'][0]['available'])
        with self.assertRaises(a.AgricultureError) as ctx:a.export_report(self.db,'a','w',{'commandId':'export-docx','reportId':report['id'],'format':'docx'},self.root)
        self.assertEqual(ctx.exception.status,409)
    def test_date_and_fallback(self):
        result=presentation(datetime(2026,10,26,tzinfo=ZoneInfo('Asia/Shanghai')))['calendar']
        if result['status']=='available':
            self.assertEqual(result['lunarDate'],'二〇二六年九月十七');self.assertEqual(result['jieQi'],'');self.assertEqual(result['season'],'霜降')
        with patch.dict('sys.modules',{'lunar_python':None}):self.assertEqual(presentation()['calendar']['status'],'unavailable')
    def test_old_report_export_and_empty_document(self):
        report=a.create_entity(self.db,'a','w','report',{'commandId':'empty'},self.root)['report']
        self.assertEqual(report['document']['observations'],[])
        self.assertEqual(report['document']['photos'],[])
        for fmt in ('docx','pptx'):self.assertTrue(m.export_bytes({'title':'历史','body':'原正文','sources':[]},fmt))

    def test_live_demo_snapshot_is_read_only_and_labelled(self):
        from server import agriculture_live_demo as live
        live.enable_demo(self.db,'a','w')
        before=self.db.execute('SELECT state FROM agriculture_live_demo').fetchone()[0]
        report=a.create_entity(self.db,'a','w','report',{'commandId':'live-report'},self.root)['report']
        self.assertEqual(before,self.db.execute('SELECT state FROM agriculture_live_demo').fetchone()[0])
        self.assertTrue(report['document']['observations'])
        self.assertTrue(all(row['source']=='demo' and row['quality']=='simulated' for row in report['document']['observations']))
        self.assertTrue(any(s['kind']=='live_demo' for s in report['sources']))
