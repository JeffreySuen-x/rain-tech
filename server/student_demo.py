"""Create a new synthetic demonstration seed; never read a running installation.

python -m server.student_demo --output seed
The target must not exist. Images are generated illustrations, not field photos.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from . import agriculture as a, agriculture_live_demo as live, workspace_seed
from .app import create_app, connect

OWNER = 'student-demo-owner'
FIXTURE_VERSION = 'student-demo-v1'
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Seed target already exists; existing student data is never overwritten')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.student-seed-', dir=output.parent))
    try:
        assets = temporary / 'assets'
        assets.mkdir()
        fixture_path = ROOT / 'examples/student-demo/fixture.json'
        fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
        inputs = [fixture_path, *sorted((ROOT / 'docs/knowledge/grape').glob('*.md')),
                  *sorted((ROOT / 'examples/student-demo/images').glob('*'))]
        if any(p.is_symlink() or not p.resolve().is_relative_to(ROOT.resolve()) for p in inputs):
            raise ValueError('Fixture symlinks are not allowed')
        if fixture.get('version') != FIXTURE_VERSION or any(Path(name).name != name or name not in {'vineyard.png','grape-leaf.png'} for name in fixture['images']):
            raise ValueError('Unsupported fixture inputs')
        origin=json.loads((ROOT/'examples/student-demo/images/ORIGIN.json').read_text(encoding='utf-8'))
        for image in origin['files']:
            if image['file'] not in fixture['images'] or sha(ROOT/'examples/student-demo/images'/image['file']) != image['sha256']:
                raise ValueError('Illustration provenance hash mismatch')
        create_app(dict(DB_PATH=str(temporary / 'shuyu.sqlite3'), ASSET_ROOT=str(assets), PRODUCTION=False))
        db = connect(temporary / 'shuyu.sqlite3')
        try:
            db.execute('INSERT INTO users VALUES(?,?,?)', (OWNER, 'student-demo', '!student-setup-required'))
            wid = workspace_seed.WORKSPACE
            db.execute('INSERT INTO workspaces VALUES(?,?,?)', (wid, OWNER, fixture['workspace']))
            db.execute('INSERT INTO threads VALUES(?,?,?,?)', ('student-demo-thread', OWNER, wid, fixture['thread']))
        finally:
            db.close()
        db = connect(temporary / 'shuyu.sqlite3')
        try:
            plot = a.create_entity(db, OWNER, wid, 'plot', dict(commandId='student-plot', **fixture['plot']))['plot']
            image_ids = []
            for name in fixture['images']:
                path = ROOT / 'examples/student-demo/images' / name
                result = a.upload(db, OWNER, wid, {'commandId':'student-image-'+name,'kind':'image'}, path.read_bytes(), '【模拟插画】'+name, assets)
                image_ids.append(result['asset']['id'])
            workspace_seed.install(db, OWNER, assets, apply=True)
            live.enable_demo(db, OWNER, wid, at=fixture['observedAt'], asset_ids=image_ids)
            for index, task in enumerate(fixture['tasks']):
                item = a.create_entity(db, OWNER, wid, 'work_item', dict(commandId='student-task-'+str(index), plotId=plot['id'], title=task['title'], description=task['description']))['workItem']
                if task.get('completed'):
                    a.complete_item(db, OWNER, item['id'], dict(commandId='student-complete-'+str(index), note=task['note'], assetIds=image_ids[:1]))
            a.create_entity(db, OWNER, wid, 'report', dict(commandId='student-report', title='【模拟】葡萄园工作简报', plotId=plot['id']), assets)
            # Creation receipts are unnecessary in a portable seed. No raw device tokens.
            db.execute('DELETE FROM commands')
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Seed integrity check failed')
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            counts = {name:db.execute('SELECT count(*) FROM "'+name+'"').fetchone()[0] for name in tables}
            for name in ('sessions','turns','artifacts','commands','agriculture_device_events'):
                if counts.get(name): raise ValueError('Unexpected executable/history rows: '+name)
            asset_manifest = []
            referenced = set()
            for row in db.execute("SELECT * FROM agriculture_entities WHERE kind='asset'"):
                item = a.unpack(row)
                path, _ = a.asset_content(db, OWNER, item['id'], assets)
                referenced.add(path.resolve())
                asset_manifest.append(dict(storageKey=item['storageKey'], sha256=sha(path), byteSize=path.stat().st_size))
            if referenced != {p.resolve() for p in assets.rglob('*') if p.is_file()}:
                raise ValueError('Asset closure mismatch')
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        finally:
            db.close()
        for path in temporary.glob('shuyu.sqlite3-*'): path.unlink()
        manifest = dict(fixtureVersion=FIXTURE_VERSION, owner=OWNER, knowledgeDocuments=6,
                        historicalTutorialsIncluded=0, inputs={str(p.relative_to(ROOT)):sha(p) for p in inputs},
                        tables=counts, assets=sorted(asset_manifest,key=lambda i:i['storageKey']))
        (temporary / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (temporary / 'demo.enabled').write_text(FIXTURE_VERSION+'\n',encoding='utf-8')
        if output.exists(): raise FileExistsError('Seed target appeared during build')
        os.rename(temporary, output)
        return manifest
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    manifest=build(args.output)
    print(json.dumps(dict(output=str(args.output),fixtureVersion=manifest['fixtureVersion'],tables=manifest['tables']),ensure_ascii=False))

if __name__=='__main__': main()
