import io
import unittest
import threading
from unittest.mock import patch
from server.agriculture_materials import extract
from server.agriculture import AgricultureError

class MaterialWorker(unittest.TestCase):
    def test_six_formats(self):
        for suffix in ('txt','md','csv'):
            self.assertEqual(extract(b'hello', 'x.'+suffix)[0][0]['text'], 'hello')
        from docx import Document
        doc=Document();doc.add_paragraph('hello');out=io.BytesIO();doc.save(out)
        self.assertIn('hello', str(extract(out.getvalue(), 'x.docx')))
        from pptx import Presentation
        deck=Presentation();slide=deck.slides.add_slide(deck.slide_layouts[1]);slide.shapes.title.text='hello'
        out=io.BytesIO();deck.save(out)
        self.assertIn('hello', str(extract(out.getvalue(), 'x.pptx')))
        # Minimal textual PDF, generated synthetically with correct offsets.
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
        stream=b'BT /F1 12 Tf 20 100 Td (hello) Tj ET';objects.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
        raw=b'%PDF-1.4\n';offsets=[0]
        for i,obj in enumerate(objects,1):
            offsets.append(len(raw));raw+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
        xref=len(raw);raw+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{n:010} 00000 n \n'.encode() for n in offsets[1:])+b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(xref).encode()+b'\n%%EOF'
        self.assertIn('hello', str(extract(raw,'x.pdf')))

    def test_timeout_and_next(self):
        with patch('server.agriculture_materials.MATERIAL_TIMEOUT', 0):
            with self.assertRaises(AgricultureError): extract(b'hello', 'x.txt')
        self.assertFalse(any(t.name.startswith('material-') for t in threading.enumerate()))
        self.assertEqual(extract(b'next','x.txt')[0][0]['text'],'next')

    def test_parent_removes_written_original_after_kill(self):
        import subprocess
        import tempfile
        from pathlib import Path
        real_popen, real_temp = subprocess.Popen, tempfile.TemporaryDirectory
        directories, children, originals = [], [], []
        observed = threading.Event()
        def directory(*args, **kwargs):
            result = real_temp(*args, **kwargs)
            directories.append(result.name)
            return result
        def launch(args, **kwargs):
            # Exercise actual worker: hang only once its closed original exists.
            script = ("import time; import server.agriculture_materials as m; "
                      "m.extract_segments=lambda path: time.sleep(30); "
                      "from server.material_worker import main; main()")
            child = real_popen([args[0], '-c', script], **kwargs)
            children.append(child)
            def observe():
                import time
                for _ in range(100):
                    path = Path(directories[-1]) / 'material.txt'
                    if path.exists():
                        originals.append(path.read_bytes()); observed.set(); return
                    if child.poll() is not None: return
                    time.sleep(.005)
            watcher = threading.Thread(target=observe)
            watcher.start()
            children[-1]._test_watcher = watcher
            return child
        with patch('server.agriculture_materials.tempfile.TemporaryDirectory', side_effect=directory), patch('subprocess.Popen', side_effect=launch), patch('server.agriculture_materials.MATERIAL_TIMEOUT', .7):
            with self.assertRaises(AgricultureError): extract(b'private synthetic original', 'x.txt')
        for child in children: child._test_watcher.join(1)
        self.assertTrue(observed.is_set())
        self.assertEqual(originals, [b'private synthetic original'])
        self.assertTrue(directories)
        self.assertTrue(all(not Path(path).exists() for path in directories))
        self.assertTrue(all(child.poll() is not None for child in children))
        self.assertEqual(extract(b'next', 'x.txt')[0][0]['text'], 'next')
