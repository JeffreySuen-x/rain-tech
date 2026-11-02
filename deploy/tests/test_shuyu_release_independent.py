"""Independent adversarial QA; only temporary synthetic data, no providers."""
import hashlib, importlib.util, io, json, sqlite3, tarfile, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as A
from server.app import create_app
spec=importlib.util.spec_from_file_location('release_independent',Path(__file__).parents[1]/'shuyu_release.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class IndependentReleaseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
 def tearDown(self):self.tmp.cleanup()
 def archive(self, entries, manifest):
  p=self.root/'probe.tar.gz'
  with tarfile.open(p,'w:gz') as t:
   for name,typ,b in entries+[('MANIFEST.json',tarfile.REGTYPE,json.dumps(manifest).encode())]:
    e=tarfile.TarInfo(name);e.type=typ;e.size=len(b) if typ==tarfile.REGTYPE else 0;e.linkname='payload';t.addfile(e,io.BytesIO(b))
  return p
 def test_archive_attacks(self):
  meta={'size':1,'sha256':hashlib.sha256(b'x').hexdigest()}
  cases=[([('payload',tarfile.REGTYPE,b'x'),('payload',tarfile.REGTYPE,b'x')],{'payload':meta}),([('../outside',tarfile.REGTYPE,b'x')],{'../outside':meta}),([('/outside',tarfile.REGTYPE,b'x')],{'/outside':meta}),([('payload',tarfile.SYMTYPE,b'')],{'payload':meta}),([('payload',tarfile.LNKTYPE,b'')],{'payload':meta}),([('payload',tarfile.REGTYPE,b'y')],{'payload':meta}),([('unlisted',tarfile.REGTYPE,b'x')],{}),([] ,{'missing':meta})]
  for entries,listing in cases:
   with self.subTest(entries=entries):
    p=self.archive(entries,{'format':1,'kind':'code','files':listing})
    with self.assertRaises((ValueError,KeyError)):r.verify(A(package=p))
 def test_snapshot_restore_business_preservation(self):
  src=self.root/'source';src.mkdir();assets=src/'assets';assets.mkdir();db=src/'database.sqlite3'
  create_app({'DB_PATH':str(db),'SECRET_KEY':'q'*32,'PUBLIC_ORIGIN':'https://127.0.0.1:8443'})
  key='b'*32;(assets/key).write_bytes(b'historical deleted original')
  with sqlite3.connect(db) as d:
   d.execute("INSERT INTO users VALUES('u','demo','passwordhash-preserve')")
   d.execute("INSERT INTO sessions VALUES('s','u','csrf',9999999999)")
   d.execute("INSERT INTO workspaces VALUES('w','u','garden')")
   d.execute("INSERT INTO threads VALUES('t','u','w','history')")
   for i,status in [('q','queued'),('r','running'),('c','completed'),('n','needs_review')]:d.execute("INSERT INTO turns(id,owner,thread_id,workspace_id,status,payload,created_at,generation,lease_until,dispatched,result) VALUES(?,'u','t','w',?,'{}',1,7,123,1,'immutable-result')",(i,status))
   d.execute("INSERT INTO agent_receipts VALUES('r',7,'call','provider','digest','dispatched','retained')")
   d.execute("INSERT INTO agriculture_entities VALUES('a','u','w','asset',?,NULL,1,1,1)",(json.dumps({'storageKey':key,'byteSize':27,'sha256':r.digest(assets/key)['sha256']}),))
  before=r.digest(db);report=r.db_report(db,assets);p=self.root/'data.tar.gz';r.archive(src,p,'private-data',{'snapshot':report})
  out=self.root/'restored';r.restore(A(package=p,output=out))
  self.assertEqual(r.digest(db),before)
  with sqlite3.connect(out/'database.sqlite3') as d:
   self.assertEqual(d.execute('SELECT password FROM users').fetchone()[0],'passwordhash-preserve')
   self.assertEqual(d.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
   self.assertEqual(d.execute('SELECT * FROM agent_receipts').fetchall(),[('r',7,'call','provider','digest','dispatched','retained')])
   rows=d.execute('SELECT id,status,generation,dispatched,result FROM turns ORDER BY id').fetchall()
   self.assertEqual(rows,[('c','completed',7,1,'immutable-result'),('n','needs_review',7,1,'immutable-result'),('q','needs_review',8,1,'immutable-result'),('r','needs_review',8,1,'immutable-result')])
  audit=json.loads((out/'restore-audit.json').read_text());self.assertEqual({v['id']:v['status'] for v in audit['turns_before']},{'q':'queued','r':'running'})
  self.assertEqual((out/'assets'/key).read_bytes(),b'historical deleted original')
  with self.assertRaises(ValueError):r.restore(A(package=p,output=out))
  with sqlite3.connect(db) as d:d.execute('CREATE TABLE alien(x)')
  with self.assertRaises(ValueError):r.db_report(db,assets)
 def test_render_boundaries_and_escaping(self):
  private=self.root/'private';private.mkdir(mode=0o700);provider=private/'provider-only.json'
  fake={'SHUYU_PROVIDER_URL':'https://example.invalid/v1','SHUYU_PROVIDER_KEY':'FAKE_"\\$TOKEN`ONLY','SHUYU_PROVIDER_MODEL':'fake'}
  r.write_json(provider,fake)
  args=dict(ip='192.0.2.10',allow_cidr=['198.51.100.2/32'],port=8443,code=str(self.root/'code'),data=str(self.root/'data'),provider=provider,output=self.root/'config',node_bin_dir='/usr/local/bin')
  for patch in ({'allow_cidr':['::/0']},{'allow_cidr':['1.2.3.4; deny all;']},{'output':self.root/'code/web/dist/config'},{'data':str(self.root/'code/web/dist/private')},{'output':self.root/'bad;command'},{'output':self.root/'bad\nEnvironment=INJECTED'}):
   with self.subTest(patch=patch),self.assertRaises(ValueError):r.render(A(**{**args,**patch}))
  r.render(A(**args))
  out=self.root/'config';nginx=(out/'nginx-server.conf').read_text();env=(out/'shuyu.env').read_text()
  self.assertIn('https://192.0.2.10:8443',env);self.assertEqual((out/'shuyu.env').stat().st_mode & 0o777,0o600)
  self.assertIn('allow 198.51.100.2/32;',nginx);self.assertIn('deny all;',nginx);self.assertIn('devices/[^/]+/events',nginx)
  self.assertIn('subjectAltName=IP:192.0.2.10',(out/'certificate-commands.txt').read_text())
  for role in ('api','worker'):
   unit=(out/('shuyu-'+role+'.service')).read_text();self.assertIn('EnvironmentFile='+str(out)+'/shuyu.env',unit);self.assertIn('PATH=/usr/local/bin:/usr/bin:/bin',unit)
  self.assertIn('--workers 1 --bind 127.0.0.1:6480',(out/'shuyu-api.service').read_text())
  self.assertFalse(json.loads((out/'render-audit.json').read_text())['worker_enabled'])
 def test_preflight_fail_closed_here(self):
  import platform
  if platform.system()!='Linux':
   with self.assertRaises(ValueError):r.preflight(A(directory=self.root,minimum_free_bytes=1,port=8443))
if __name__=='__main__':unittest.main()
