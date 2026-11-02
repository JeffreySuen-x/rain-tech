import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
from types import SimpleNamespace as A
import unittest
from server.app import create_app

spec = importlib.util.spec_from_file_location('release', Path(__file__).parents[1] / 'shuyu_release.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.data = self.root / 'source'; self.data.mkdir(); self.assets = self.data/'assets'; self.assets.mkdir()
        self.db = self.data/'database.sqlite3'
        create_app({'DB_PATH':str(self.db),'SECRET_KEY':'x'*32,'PUBLIC_ORIGIN':'https://127.0.0.1:8443'})
        key='a'*32; (self.assets/key).write_bytes(b'original')
        with sqlite3.connect(self.db) as d:
            d.execute("INSERT INTO users VALUES('u','demo','hash')")
            d.execute("INSERT INTO sessions VALUES('s','u','csrf',9999999999)")
            d.execute("INSERT INTO workspaces VALUES('w','u','garden')")
            d.execute("INSERT INTO threads VALUES('t','u','w','thread')")
            for ident in ('pending','follow'):
                d.execute("INSERT INTO turns(id,owner,thread_id,workspace_id,status,payload,created_at,generation,lease_until,dispatched,result) VALUES(?,'u','t','w','running','{}',1,4,123,1,'preserved')",(ident,))
            for ident,kind,payload in [('asset','asset',{'storageKey':key,'byteSize':8,'sha256':r.digest(self.assets/key)['sha256']}),('f','follow_up',{'enabled':True,'authorizationVersion':3,'turnIds':['follow'],'remainingRuns':2})]:
                d.execute("INSERT INTO agriculture_entities VALUES(?,'u','w',?,?,NULL,1,1,1)",(ident,kind,json.dumps(payload)))
        d.close()
        self.before = r.digest(self.db); self.assetbefore = r.files(self.assets)
    def tearDown(self): self.tmp.cleanup()
    def package(self):
        p=self.root/'private.tar.gz'; r.archive(self.data,p,'private-data',{'snapshot':r.db_report(self.db,self.assets)}); return p
    def test_restore_preserves_source_and_isolates(self):
        p=self.package(); out=self.root/'restored'; r.restore(A(package=p,output=out))
        self.assertEqual(r.digest(self.db),self.before); self.assertEqual(r.files(self.assets),self.assetbefore)
        with sqlite3.connect(out/'database.sqlite3') as d:
            self.assertEqual(d.execute('select count(*) from sessions').fetchone()[0],0)
            self.assertEqual(d.execute('select id,status,generation,lease_until,result,dispatched from turns order by id').fetchall(),[('follow','cancelled',5,None,'preserved',1),('pending','needs_review',5,None,'preserved',1)])
            follow=json.loads(d.execute("select payload from agriculture_entities where id='f'").fetchone()[0]); self.assertFalse(follow['enabled']); self.assertEqual(follow['turnIds'],['follow']); self.assertEqual(follow['authorizationVersion'],4)
        r.status(A(data=out,command='activation-check'))
        with self.assertRaises(ValueError): r.restore(A(package=p,output=out))
    def test_missing_and_corrupt_assets(self):
        asset=next(self.assets.iterdir()); asset.write_bytes(b'bad')
        with self.assertRaises(ValueError): r.db_report(self.db,self.assets)
        asset.unlink()
        with self.assertRaises(ValueError): r.db_report(self.db,self.assets)
    def test_unknown_schema(self):
        with sqlite3.connect(self.db) as d:d.execute('ALTER TABLE users ADD COLUMN alien TEXT')
        with self.assertRaises(ValueError):r.db_report(self.db,self.assets)
    def test_bad_hash(self):
        p=self.package()
        with tarfile.open(p) as t: entries=[(e,t.extractfile(e).read()) for e in t.getmembers()]
        with tarfile.open(p,'w:gz') as t:
            for e,b in entries:
                if e.name=='database.sqlite3':b=b[:-1]+bytes([b[-1]^1])
                e.size=len(b); t.addfile(e,io.BytesIO(b))
        with self.assertRaises(ValueError):r.verify(A(package=p))
    def test_hostile_archives(self):
        for typ,name in [(tarfile.REGTYPE,'../evil'),(tarfile.REGTYPE,'/evil'),(tarfile.SYMTYPE,'link'),(tarfile.REGTYPE,'duplicate')]:
            p=self.root/'hostile.tar.gz'
            with tarfile.open(p,'w:gz') as t:
                e=tarfile.TarInfo(name); e.type=typ; e.linkname='/etc/passwd'; t.addfile(e,io.BytesIO())
                if name=='duplicate':t.addfile(e,io.BytesIO())
            with self.assertRaises(ValueError):r.verify(A(package=p))
    def test_render_validation_and_permissions(self):
        private=self.root/'secret'; private.mkdir(mode=0o700); provider=private/'provider.json'
        r.write_json(provider,{'SHUYU_PROVIDER_URL':'https://example.invalid/v1','SHUYU_PROVIDER_KEY':'FAKE_KEY_ONLY','SHUYU_PROVIDER_MODEL':'fake'})
        node=self.root/'node-bin'; node.mkdir(); (node/'node').write_text('#!/bin/sh\necho v24.1.0\n'); (node/'node').chmod(0o700)
        args=dict(node_bin_dir=str(node),ip='192.0.2.1',code='/opt/shuyu',data='/var/lib/shuyu',provider=provider,output=self.root/'config',port=8443,allow_cidr=['198.51.100.0/24'])
        for change in ({'allow_cidr':['0.0.0.0/0']},{'allow_cidr':[]},{'ip':'evil;command'},{'code':'/opt/inject;command'}):
            with self.assertRaises(ValueError):r.render(A(**{**args,**change}))
        r.render(A(**args)); env=(self.root/'config/shuyu.env').read_text(); self.assertIn('https://192.0.2.1:8443',env)
        self.assertEqual((self.root/'config/shuyu.env').stat().st_mode & 0o777,0o600)
        self.assertFalse(json.loads((self.root/'config/render-audit.json').read_text())['worker_enabled'])
        self.assertIn('deny all;', (self.root/'config/nginx-server.conf').read_text())
        provider.write_text('{}')
        with self.assertRaises(ValueError):r.render(A(**{**args,'output':self.root/'config2'}))
    def test_activation_blocked(self):
        with self.assertRaises(ValueError):r.status(A(data=self.data,command='activation-check'))
    def test_symlink_rejected(self):
        (self.assets/'link').symlink_to(next(self.assets.iterdir()))
        with self.assertRaises(ValueError):r.files(self.assets)

if __name__=='__main__':unittest.main()
