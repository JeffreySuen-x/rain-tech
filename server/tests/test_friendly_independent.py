"""Independent friendly-workbench acceptance; disposable SQLite/files only."""
import copy
import json
import time
import unittest
import zipfile
from io import BytesIO
from unittest.mock import patch
from server.tests import test_agriculture_domain as fixtures
png=fixtures.png
from server import agriculture as a, agriculture_live_demo as live, agriculture_reports as reports

class FriendlyIndependent(unittest.TestCase):
    setUp=fixtures.DomainTests.setUp
    tearDown=fixtures.DomainTests.tearDown
    task=fixtures.DomainTests.task
    device=fixtures.DomainTests.device
    event=fixtures.DomainTests.event

    def report(self, command='r', **extra):
        return a.create_entity(self.db,'a','w','report',{'commandId':command,**extra},self.root)['report']

    def test_saved_demo_full_digest_readonly_and_freeze(self):
        now=time.time()
        live.enable_demo(self.db,'a','w',at=now-70)
        live.advance(self.db,at=now-40)
        live.advance(self.db,at=now-10)
        before=tuple(self.db.execute('SELECT version,state FROM agriculture_live_demo').fetchone())
        document=self.report()['document']
        self.assertEqual(tuple(self.db.execute('SELECT version,state FROM agriculture_live_demo').fetchone()),before)
        samples=json.loads(before[1])['samples']
        source=next(s for s in document['sources'] if s['kind']=='live_demo')
        self.assertEqual(source['sourceHash'],a.digest(samples))
        self.assertEqual(source['origin'],'demo')
        self.assertEqual(source['sampleCount'],len(samples))
        self.assertEqual(len(document['observations']),len(samples)*3)
        for row in document['observations']:
            self.assertEqual(row['plotId'],self.plot['id'])
            self.assertEqual(row['liveDemoVersion'],before[0])
            self.assertEqual(row['source'],'demo')
            self.assertEqual(row['quality'],'simulated')
        old=copy.deepcopy(document)
        live.advance(self.db,at=now+20)
        self.assertEqual(a.read(self.db,'a',self.report()['id'],'report')['document'],old)
        self.assertTrue(any('120' in text and '7' in text for text in document['limitations']))

    def test_period_filter_selection_photo_privacy_and_disk_tamper(self):
        device=self.device()['device'];now=time.time()
        self.event(device['id'],'old',now-8*86400,40)
        self.event(device['id'],'current',now-10,55)
        chosen=self.task('chosen');other=self.task('other')
        photo=a.upload(self.db,'a','w',{'commandId':'photo','kind':'image'},png(),'selected.png',self.root)['asset']
        extra=a.upload(self.db,'a','w',{'commandId':'extra','kind':'image'},png(),'unselected.png',self.root)['asset']
        a.complete_item(self.db,'a',chosen['id'],{'commandId':'done','note':'人工记录','assetIds':[photo['id']]})
        a.complete_item(self.db,'a',other['id'],{'commandId':'otherdone','note':'不应出现','assetIds':[extra['id']]})
        report=self.report(workItemIds=[chosen['id']]);doc=report['document']
        self.assertEqual([p['assetId'] for p in doc['photos']],[photo['id']])
        self.assertEqual([x['sourceEventId'] for x in doc['observations']],['current'])
        self.assertAlmostEqual(doc['period']['to']-doc['period']['from'],7*86400)
        self.assertNotIn('storageKey',a.encode(doc))
        with self.assertRaises(a.AgricultureError):a.read(self.db,'b',report['id'],'report')
        export=a.export_report(self.db,'a','w',{'commandId':'export','reportId':report['id'],'format':'docx'},self.root)['asset']
        path,_=a.asset_content(self.db,'a',export['id'],self.root)
        with zipfile.ZipFile(path) as z:self.assertTrue(any('/media/' in n for n in z.namelist()))
        rawpath,_=a.asset_content(self.db,'a',photo['id'],self.root)
        raw=rawpath.read_bytes();rawpath.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
        self.assertFalse(reports.present(self.db,'a',report,self.root)['document']['photos'][0]['available'])
        with self.assertRaises(a.AgricultureError) as ctx:a.export_report(self.db,'a','w',{'commandId':'export','reportId':report['id'],'format':'docx'},self.root)
        self.assertEqual(ctx.exception.status,409)

    def test_legacy_without_sources_keeps_body_and_exports(self):
        legacy=a.insert(self.db,'a','w','report',{'title':'旧报告','body':'历史正文','generationType':'agent_followup','version':1})
        shown=reports.present(self.db,'a',legacy,self.root)
        self.assertNotIn('document',shown)
        self.assertEqual(shown['body'],'历史正文')
        for fmt in ('docx','pptx'):
            self.assertTrue(a.export_report(self.db,'a','w',{'commandId':'old-'+fmt,'reportId':legacy['id'],'format':fmt},self.root)['asset'])

    def test_demo_derived_photo_revoked_original_and_replay(self):
        original=a.upload(self.db,'a','w',{'commandId':'demo-original','kind':'image'},png(),'模拟原型图片.png',self.root)['asset']
        live.enable_demo(self.db,'a','w',asset_ids=[original['id']])
        facts=live.action(self.db,'a','w',{'commandId':'capture','action':'camera.capture','cameraId':'demo-camera-1'},self.root)['liveDemo']
        derived=facts['captures'][-1]['assetId']
        task=self.task()
        a.complete_item(self.db,'a',task['id'],{'commandId':'done-demo','note':'模拟巡视','assetIds':[derived]})
        report=self.report(workItemIds=[task['id']])
        self.assertEqual(report['document']['photos'][0]['origin'],'demo')
        self.assertIn('演示图片',report['document']['photos'][0]['caption'])
        a.export_report(self.db,'a','w',{'commandId':'demo-export','reportId':report['id'],'format':'pptx'},self.root)
        a.revoke_asset(self.db,'a',original['id'])
        self.assertFalse(reports.present(self.db,'a',report,self.root)['document']['photos'][0]['available'])
        with self.assertRaises(a.AgricultureError) as ctx:
            a.export_report(self.db,'a','w',{'commandId':'demo-export','reportId':report['id'],'format':'pptx'},self.root)
        self.assertEqual(ctx.exception.status,409)

    def test_calendar_day_boundary_fallback_and_explicit_weather_demo(self):
        from datetime import datetime, timezone
        from server.agriculture_calendar import presentation
        result=presentation(datetime(2026,10,25,16,1,tzinfo=timezone.utc))
        self.assertEqual(result['calendar']['date'],'2026-10-26')
        self.assertEqual(result['calendar']['status'],'available')
        self.assertEqual(result['calendar']['jieQi'],'')
        self.assertEqual(result['calendar']['season'],'霜降')
        self.assertEqual(result['weather']['mode'],'demo')
        self.assertEqual(len(result['weather']['forecast']),3)
        self.assertNotIn('observedAt',result['weather'])
        self.assertEqual(result['weather']['location'],'园区天气')
        with patch.dict('sys.modules',{'lunar_python':None}):
            missing=presentation(datetime(2026,10,26,tzinfo=timezone.utc))
            self.assertEqual(missing['calendar']['status'],'unavailable')
            self.assertNotIn('lunarDate',missing['calendar'])
            self.assertEqual(missing['weather']['mode'],'demo')

if __name__=='__main__':unittest.main()
