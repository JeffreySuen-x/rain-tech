import subprocess, sys, threading, time, unittest
from unittest.mock import patch
from server.agriculture_materials import extract
from server.agriculture import AgricultureError

class IndependentMaterial(unittest.TestCase):
    def test_faults_reaped_and_next_read(self):
        real=subprocess.Popen
        for code in ('import time;time.sleep(10)', 'while True: pass', 'print("bad-json")', 'print("x"*5000000)', 'raise SystemExit(7)'):
            children=[]
            def spawn(args, **kwargs):
                child=real([sys.executable,'-c',code],**kwargs);children.append(child);return child
            started=time.monotonic()
            with self.subTest(code=code), patch('subprocess.Popen',spawn), patch('server.agriculture_materials.MATERIAL_TIMEOUT',.2):
                with self.assertRaises(AgricultureError):extract(b'synthetic','x.txt')
            self.assertLess(time.monotonic()-started,1.7)
            self.assertTrue(children)
            for child in children:
                self.assertIsNotNone(child.returncode)
                self.assertIsNotNone(child.poll())
            self.assertFalse(any(t.name.startswith('material-') for t in threading.enumerate()))
            self.assertEqual(extract(b'next','x.txt')[0][0]['text'],'next')

from pathlib import Path
import tempfile
from server.tests.test_agriculture_domain import DomainTests
from server import agriculture as agriculture

class IndependentMaterialPrivacy(unittest.TestCase):
    setUp=DomainTests.setUp
    tearDown=DomainTests.tearDown

    def test_parent_cleans_worker_original_failure_and_next_upload(self):
        real=subprocess.Popen
        for tail in ('import time;time.sleep(10)', 'raise SystemExit(7)'):
            with self.subTest(tail=tail), tempfile.TemporaryDirectory() as evidence:
                marker=Path(evidence)/'directory'
                code=('import sys,json,pathlib;h=json.loads(sys.stdin.buffer.readline());'
                      'raw=sys.stdin.buffer.read();d=pathlib.Path(h["directory"]);'
                      '(d/("material"+h["suffix"])).write_bytes(raw);'
                      f'pathlib.Path({str(marker)!r}).write_text(str(d));'+tail)
                children=[]
                def spawn(args,**kwargs):
                    child=real([sys.executable,'-c',code],**kwargs);children.append(child);return child
                before=self.db.serialize()
                with patch('subprocess.Popen',spawn), patch('server.agriculture_materials.MATERIAL_TIMEOUT',.4):
                    with self.assertRaises(AgricultureError):
                        agriculture.upload(self.db,'a','w',{'commandId':'fail-'+str(len(tail)),'kind':'document'},b'private synthetic original','x.txt',self.root)
                self.assertTrue(marker.exists(),'worker actually wrote original')
                self.assertFalse(Path(marker.read_text()).exists(),'parent removed directory after reap')
                self.assertEqual(self.db.serialize(),before,'no asset or knowledge or command mutation')
                self.assertTrue(all(c.returncode is not None for c in children))
                self.assertFalse(any(t.name.startswith('material-') for t in threading.enumerate()))
        result=agriculture.upload(self.db,'a','w',{'commandId':'next-success','kind':'document'},b'next readable','next.txt',self.root)
        self.assertTrue(result['asset']['id'])

# Avoid unittest collecting the fixture class's unrelated implementation tests.
del DomainTests
