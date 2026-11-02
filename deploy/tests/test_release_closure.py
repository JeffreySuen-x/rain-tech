"""Exercise the runtime seed from only the files selected for release."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('closure_release', ROOT / 'deploy/shuyu_release.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class ReleaseClosureTests(unittest.TestCase):
    def test_selected_tree_builds_seed_and_preserves_input_hashes(self):
        with tempfile.TemporaryDirectory(prefix='release-closure-') as tmp:
            tree = Path(tmp) / 'code'; tree.mkdir()
            selected = r.select_code(ROOT)
            names = {p.relative_to(ROOT).as_posix() for p in selected}
            self.assertNotIn('README.md', names)
            self.assertFalse(any(name.startswith('docs/reviews/') for name in names))
            for path in selected:
                dest = tree / path.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
            output = Path(tmp) / 'seed'
            result = subprocess.run([sys.executable, '-m', 'server.student_demo', '--output', str(output)],
                cwd=tree, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['knowledgeDocuments'], 6)
            knowledge = [name for name in manifest['inputs'] if name.startswith('docs/knowledge/grape/')]
            self.assertEqual(len(knowledge), 6)
            self.assertEqual(len(manifest['inputs']), 10)
            for name, digest in manifest['inputs'].items():
                self.assertIn(name, names)
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
                self.assertEqual(hashlib.sha256((tree / name).read_bytes()).hexdigest(), digest)
