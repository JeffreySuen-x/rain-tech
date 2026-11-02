"""Importer acceptance uses isolated SQLite/assets; no model provider.

Set SHUYU_LIBRARY_SOURCE to a tutorial library directory to run these
acceptance tests against an external source; defaults use a synthetic corpus.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from server.tests import test_independent_agriculture_contracts as fixtures
from server import agriculture as a, library_import as lib

from server.tests.library_fixture import source as library_source
SOURCE = library_source()

class LibraryImportTests(unittest.TestCase):
    setUp=fixtures.IndependentAgricultureTests.setUp
    tearDown=fixtures.IndependentAgricultureTests.tearDown
    login=fixtures.IndependentAgricultureTests.login
    post=fixtures.IndependentAgricultureTests.post
    # Reuse fixture setup without inheriting unrelated acceptance cases.
    def install(self, apply=False, source=SOURCE):
        return lib.install(self.db, 'a', self.w, Path(self.tmp.name)/'library-assets', source, apply)

    def test_real_source_integrity_idempotency_and_private_originals(self):
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.rglob('*') if p.is_file()}
        original = self.db.serialize()
        plan = self.install()
        self.assertEqual(plan['counts'], {'MON':77, 'EDU':52, 'BASE':1})
        self.assertEqual(plan['create'],130)
        self.assertEqual(original,self.db.serialize())
        self.assertFalse((Path(self.tmp.name)/'library-assets').exists())
        result=self.install(True)
        self.assertEqual(len(a.entities(self.db,'a',self.w,'knowledge')),130)
        self.assertEqual(self.install(True)['unchanged'],130)
        for item in a.entities(self.db,'a',self.w,'knowledge'):
            path,asset=a.asset_content(self.db,'a',item['assetId'],Path(self.tmp.name)/'library-assets')
            raw=(SOURCE/item['library']['sourceRelativePath']).read_bytes()
            self.assertEqual(path.read_bytes(),raw)
            self.assertEqual(''.join(e['text'] for e in item['excerpts']),raw.decode())
            self.assertLessEqual(len(item['excerpts']),20)
            lines=raw.decode().splitlines(keepends=True)
            for excerpt in item['excerpts']:
                start,end=map(int,excerpt['locator'][1:].split('-L'))
                self.assertEqual(excerpt['text'],''.join(lines[start-1:end]))
                self.assertLessEqual(len(excerpt['text']),2000)
            with self.assertRaises(a.AgricultureError):a.asset_content(self.db,'b',asset['id'],Path(self.tmp.name)/'library-assets')
        self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.rglob('*') if p.is_file()})

    def test_metadata_deletion_original_and_capacity_conflicts(self):
        self.install(True)
        item=a.entities(self.db,'a',self.w,'knowledge')[0]
        original=self.db.execute('SELECT payload FROM agriculture_entities WHERE id=?',(item['id'],)).fetchone()[0]
        a.update(self.db,'a',item['id'],'knowledge',{**item,'summary':'edited'})
        self.assertEqual(self.install()['conflict'],1)
        with self.assertRaises(a.AgricultureError):self.install(True)
        self.db.execute('UPDATE agriculture_entities SET payload=?,deleted=1 WHERE id=?',(original,item['id']))
        with self.assertRaises(a.AgricultureError):self.install(True)
        self.db.execute('UPDATE agriculture_entities SET deleted=0 WHERE id=?',(item['id'],))
        path,_=a.asset_content(self.db,'a',item['assetId'],Path(self.tmp.name)/'library-assets');path.write_bytes(b'corrupt')
        self.assertEqual(self.install()['conflict'],1)

    def test_catalog_snapshot_only_noop_tail_append_and_metadata_conflict(self):
        source=Path(self.tmp.name)/'catalog-source';shutil.copytree(SOURCE,source)
        self.install(True,source)
        before=[tuple(row) for row in self.db.execute('SELECT * FROM agriculture_entities ORDER BY id')]
        catalog_path=source/'topic_map.json'
        catalog=json.loads(catalog_path.read_text())
        catalog['date']='catalog-only-change'
        catalog_path.write_text(json.dumps(catalog,ensure_ascii=False))
        result=self.install(True,source)
        self.assertEqual(result['unchanged'],130)
        self.assertNotEqual(result['catalogHash'],a.entities(self.db,'a',self.w,'knowledge')[0]['library']['catalogHash'])
        self.assertEqual(before,[tuple(row) for row in self.db.execute('SELECT * FROM agriculture_entities ORDER BY id')])
        track=catalog['tracks'][-1];group=track['groups'][-1]
        old_id=group['sections'][-1]['article_ids'][-1]
        record=next(r for r in catalog['articles'] if r['id']==old_id)
        new_id='EDU-999';relative='articles/EDU-999.md'
        raw=(source/record['href']).read_text().replace(old_id,new_id)
        (source/relative).write_text(raw)
        catalog['articles'].append({**record,'id':new_id,'href':relative,'primary_track':track['id'],'primary_group':group['id']})
        group['sections'][-1]['article_ids'].append(new_id);group['article_ids'].append(new_id)
        track['primary_article_count']+=1;catalog['effective_articles']+=1
        catalog_path.write_text(json.dumps(catalog,ensure_ascii=False))
        result=self.install(True,source)
        self.assertEqual((result['create'],result['unchanged']),(1,130))
        catalog['articles'][-1]['version']='changed-version'
        catalog_path.write_text(json.dumps(catalog,ensure_ascii=False))
        self.assertEqual(self.install(False,source)['conflict'],1)
        with self.assertRaises(a.AgricultureError):self.install(True,source)
        catalog['tracks'][0]['primary_article_count']-=1
        catalog_path.write_text(json.dumps(catalog,ensure_ascii=False))
        with self.assertRaises(a.AgricultureError):lib.snapshot(source)

    def test_batch_rollback_source_change_missing_symlink_and_long_line(self):
        with patch.object(a,'insert',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):self.install(True)
        self.assertEqual(a.entities(self.db,'a',self.w,'asset'),[])
        self.assertEqual(list((Path(self.tmp.name)/'library-assets').iterdir()),[])
        snapshot=lib.snapshot
        calls=0
        def changed(source):
            nonlocal calls
            calls+=1
            result=snapshot(source)
            if calls>1:result[0][0]['payload']['summary']='changed'
            return result
        with patch.object(lib,'snapshot',side_effect=changed):
            with self.assertRaises(a.AgricultureError):self.install(True)
        with patch.object(a,'MAX_ASSETS',129):
            self.assertFalse(self.install()['capacity']['asset']['fits'])
            with self.assertRaises(a.AgricultureError):self.install(True)
        copy=Path(self.tmp.name)/'source';shutil.copytree(SOURCE,copy)
        target=next((copy/'articles').glob('MON-054.md'));raw=target.read_bytes();target.unlink()
        with self.assertRaises(a.AgricultureError):lib.snapshot(copy)
        target.symlink_to(SOURCE/'articles/MON-054.md')
        with self.assertRaises(a.AgricultureError):lib.snapshot(copy)
        target.unlink();target.write_bytes(raw)
        duplicate=copy/'articles/MON-054_duplicate.md';duplicate.write_bytes(raw)
        with self.assertRaises(a.AgricultureError):lib.snapshot(copy)
        with self.assertRaises(a.AgricultureError):lib.packed('x'*2001)
