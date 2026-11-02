"""Office projection volume and immutable-snapshot checks."""
import copy
from io import BytesIO
import unittest
from pptx import Presentation
from docx import Document
from server.agriculture_materials import export_bytes, document_sections

class OfficeSummary(unittest.TestCase):
    def test_369_points_are_summarised_not_printed(self):
        rows=[]
        for group in range(6):
            for i in range(62 if group<3 else 61):
                rows.append(dict(id=f'{group}:{i}',deviceId='device-'+str(group),metric='temperature',unit='celsius',value=20+i/10,observedAt=1793020000+i*5,source='demo'))
        sources=[dict(id=r['id'],kind='observation',source='demo',sourceHash='a'*64) for r in rows]
        sources += [dict(id='r'+str(i),kind='activity_record',excerpt='人工巡查记录'+str(i)) for i in range(3)]
        document=dict(schemaVersion='agriculture.report.v1',generatedAt=1793027566,timezone='Asia/Shanghai',period={'from':1792422766,'to':1793027566},summary=dict(taskCount=5,completedTaskCount=3,recordCount=3),tasks=[dict(id=str(i),title='园区巡查'+str(i),status='completed' if i<3 else 'open',completedAt=1793020000 if i<3 else None) for i in range(5)],observations=rows,photos=[],sources=sources,limitations=['既有模拟序列，非完整7日。'])
        report=dict(id='report-fixture',title='园区工作简报',document=document)
        before=copy.deepcopy(report)
        sections=document_sections(report)
        self.assertEqual(len(next(lines for title,lines in sections if title=='监测摘要')),6)
        deck=Presentation(BytesIO(export_bytes(report,'pptx')))
        self.assertLessEqual(len(deck.slides),18)
        word=Document(BytesIO(export_bytes(report,'docx')))
        self.assertLess(len(word.paragraphs),70)
        text='\n'.join(p.text for p in word.paragraphs)
        self.assertIn('上海时间',text);self.assertIn('逐点记录、完整来源',text);self.assertIn('agriculture.report.v1',text)
        self.assertNotIn('1793027566',text)
        self.assertEqual(report,before)

    def test_ppt_hash_and_datetime_are_indivisible_tokens(self):
        from server.agriculture_materials import office_lines
        sha='abcdef0123456789'*4
        lines=office_lines('照片来源 SHA-256：'+sha+'；覆盖2026-10-26 23:12')
        self.assertTrue(any(line==sha for line in lines))
        self.assertTrue(any('2026-10-26 23:12' in line for line in lines))
        self.assertEqual(''.join(lines),'照片来源 SHA-256：'+sha+'；覆盖2026-10-26 23:12')
