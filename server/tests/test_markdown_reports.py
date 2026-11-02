"""Synthetic Markdown exports preserve report source authorization."""
import unittest
from server.tests import test_agriculture_domain as fixtures
from server import agriculture as a, agriculture_materials as m

class MarkdownReports(unittest.TestCase):
    setUp = fixtures.DomainTests.setUp
    tearDown = fixtures.DomainTests.tearDown
    task = fixtures.DomainTests.task

    def test_snapshot_replay_and_revocation(self):
        task=self.task()
        photo=a.upload(self.db,'a','w',{'commandId':'photo','kind':'image'},fixtures.png(),'葡萄.png',self.root)['asset']
        a.complete_item(self.db,'a',task['id'],{'commandId':'done','note':'巡视 *完整*\n<script>','assetIds':[photo['id']]})
        report=a.create_entity(self.db,'a','w','report',{'commandId':'report','workItemIds':[task['id']]},self.root)['report']
        args={'commandId':'md','reportId':report['id'],'format':'md'}
        result=a.export_report(self.db,'a','w',args,self.root)
        self.assertEqual(result,a.export_report(self.db,'a','w',args,self.root))
        asset=result['asset'];path,_=a.asset_content(self.db,'a',asset['id'],self.root)
        text=path.read_text('utf8')
        self.assertTrue(asset['name'].endswith('.md'));self.assertEqual(asset['mediaType'],'text/markdown; charset=utf-8')
        for phrase in ('任务完成情况','已有完成记录','监测事实','不含原图','葡萄','&lt;script&gt;','状态：已完成','来源：用户提供','类型：activity'):self.assertIn(phrase,text)
        self.assertNotIn('<script>',text);self.assertNotIn('data:image',text);self.assertNotIn('/api/',text)
        with self.assertRaises(a.AgricultureError):a.export_report(self.db,'other','w',args,self.root)
        a.revoke_asset(self.db,'a',photo['id'])
        with self.assertRaises(a.AgricultureError):a.export_report(self.db,'a','w',args,self.root)
        with self.assertRaises(a.AgricultureError):a.asset_content(self.db,'a',asset['id'],self.root)

    def test_changed_photo_blocks_markdown(self):
        task=self.task()
        photo=a.upload(self.db,'a','w',{'commandId':'photo','kind':'image'},fixtures.png(),'leaf.png',self.root)['asset']
        a.complete_item(self.db,'a',task['id'],{'commandId':'done','note':'巡视','assetIds':[photo['id']]})
        report=a.create_entity(self.db,'a','w','report',{'commandId':'report','workItemIds':[task['id']]},self.root)['report']
        path,_=a.asset_content(self.db,'a',photo['id'],self.root);path.write_bytes(b'changed')
        with self.assertRaises(a.AgricultureError):a.export_report(self.db,'a','w',{'commandId':'md','reportId':report['id'],'format':'md'},self.root)

    def test_historical_unicode_and_markdown(self):
        text=m.export_bytes({'title':'历史 # 葡萄','body':'第一行\n[链接](javascript:x) <img> `代码`','sources':[]},'md').decode('utf8')
        self.assertIn('历史',text);self.assertIn('第一行',text);self.assertIn('未保存结构化文档',text)
        self.assertNotIn('[链接](javascript:x)',text);self.assertNotIn('<img>',text)

    def test_readable_frozen_projection_preserves_unknown_values(self):
        report=a.create_entity(self.db,'a','w','report',{'commandId':'empty'},self.root)['report']
        report['plotId']='0123456789abcdef0123456789abcdef'
        doc=report['document']
        doc['tasks']=[{'title':'待巡视','status':'open'}, {'title':'自定义','status':'custom'}]
        doc['observations']=[{'deviceId':'demo:plot','metric':'humidity','unit':'percent','source':'demo','observedAt':0,'value':50,'quality':'simulated'}]
        text=m.export_bytes(report,'md').decode('utf8')
        body, appendix=text.split('## 来源')
        for phrase in ('待处理','状态：custom','演示模拟数据','质量：模拟数据','标识末8位：89abcdef'):self.assertIn(phrase,body)
        self.assertNotIn(report['plotId'],body)
        self.assertIn(report['plotId'],appendix)
