"""Independent full-source acceptance; only ephemeral SQLite/assets are mutated.

Defaults use a synthetic corpus; SHUYU_LIBRARY_SOURCE opts into an external source.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server import agriculture as a, library_import as lib
from server.tests.test_agriculture_domain import BASE, connect

from server.tests.library_fixture import source as library_source
SOURCE = library_source()

class IndependentLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='library-independent-')
        self.root=Path(self.tmp.name)/'assets'
        self.db=connect(str(Path(self.tmp.name)/'fixture.db'));self.db.executescript(BASE);a.migrate(self.db)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def install(self,**kw):return lib.install(self.db,'a','w',self.root,kw.pop('source',SOURCE),**kw)
    def tree(self):return sorted((str(p.relative_to(self.root)),hashlib.sha256(p.read_bytes()).hexdigest()) for p in self.root.rglob('*') if p.is_file()) if self.root.exists() else []
    def copied(self):
        dest=Path(self.tmp.name)/'source';shutil.copytree(SOURCE,dest);return dest
    def test_all_130_bytes_locators_tail_search_and_frozen_tools(self):
        source_before={str(p):lib.sha(p.read_bytes()) for p in SOURCE.rglob('*') if p.is_file()}
        old=a.insert(self.db,'a','w','knowledge',{'title':'existing','assetId':None,'version':1,'sourceHash':'old','excerpts':[{'locator':'old','text':'keep'}],'warnings':[]})
        before=self.db.serialize();report=self.install();self.assertEqual(before,self.db.serialize());self.assertEqual(self.tree(),[])
        self.assertEqual((report['create'],report['counts']),(130,{'MON':77,'EDU':52,'BASE':1}))
        self.install(apply=True);items=a.entities(self.db,'a','w','knowledge');self.assertEqual(len(items),131)
        self.assertEqual(len(a.entities(self.db,'a','w','asset')),130);self.assertEqual(a.read(self.db,'a',old['id'],'knowledge'),old)
        for item in items:
            if not item.get('library'):continue
            raw=(SOURCE/item['library']['sourceRelativePath']).read_bytes();text=raw.decode();lines=text.splitlines(keepends=True)
            path,asset=a.asset_content(self.db,'a',item['assetId'],self.root);self.assertEqual(path.read_bytes(),raw);self.assertEqual(asset['sha256'],lib.sha(raw))
            self.assertEqual(''.join(e['text'] for e in item['excerpts']),text);self.assertLessEqual(len(item['excerpts']),20)
            for e in item['excerpts']:
                match=re.fullmatch(r'L(\d+)-L(\d+)',e['locator']);self.assertIsNotNone(match)
                start,end=map(int,match.groups());self.assertEqual(e['text'],''.join(lines[start-1:end]));self.assertLessEqual(len(e['text']),3000)
            frozen=a.snapshot_context(self.db,'a','w',{'knowledgeIds':[item['id']]})
            turn={'owner':'a','workspace_id':'w','payload':{'agricultureContext':frozen}}
            result=a.execute_tool(self.db,turn,'read_source',{'sourceId':item['id']},'independent')
            self.assertEqual(''.join(s['excerpt'] for s in result['sources']),text)
            tail=next(line.strip() for line in reversed(lines) if line.strip())
            found=a.execute_tool(self.db,turn,'search_knowledge',{'query':tail[:190]},'search')
            self.assertTrue(found['sources'],item['library']['articleId'])
            with self.assertRaises(a.AgricultureError):a.execute_tool(self.db,turn,'read_source',{'sourceId':old['id']},'forbidden')
            with self.assertRaises(a.AgricultureError):a.asset_content(self.db,'b',item['assetId'],self.root)
        before=self.db.serialize();files=self.tree();self.assertEqual(self.install(apply=True)['unchanged'],130);self.assertEqual(before,self.db.serialize());self.assertEqual(files,self.tree())
        self.assertEqual(source_before,{str(p):lib.sha(p.read_bytes()) for p in SOURCE.rglob('*') if p.is_file()})
    def test_partial_write_rollback_and_target_ownership(self):
        for owner,wid in [('b','w'),('a','foreign')]:
            with self.assertRaises(a.AgricultureError):lib.install(self.db,owner,wid,self.root,SOURCE,True)
        before=self.db.serialize();real=a.insert;count=0
        def explode(*args,**kw):
            nonlocal count
            count+=1
            if count==9:raise RuntimeError('independent injected failure')
            return real(*args,**kw)
        with patch.object(a,'insert',side_effect=explode):
            with self.assertRaises(RuntimeError):self.install(apply=True)
        self.assertEqual(before,self.db.serialize());self.assertEqual(self.tree(),[])
    def test_source_symlink_missing_and_catalog_counts(self):
        source=self.copied();article=next((source/'articles').glob('MON*.md'));raw=article.read_bytes();article.unlink();article.symlink_to(SOURCE/'articles'/article.name)
        with self.assertRaises(a.AgricultureError):self.install(source=source,apply=True)
        article.unlink();article.write_bytes(raw);article.unlink()
        with self.assertRaises(a.AgricultureError):self.install(source=source,apply=True)
        # Mismatched declarations fail; consistent smaller libraries are permitted.
        article.write_bytes(raw);catalog=json.loads((source/'topic_map.json').read_text());identifier=re.match(r'^(MON-\d+)',article.name).group();article.unlink()
        catalog['effective_articles']=129;catalog['articles']=[r for r in catalog['articles'] if r['id']!=identifier]
        for track in catalog['tracks']:
            for group in track['groups']:
                if 'article_ids' in group:group['article_ids']=[i for i in group['article_ids'] if i!=identifier]
                for section in group['sections']:section['article_ids']=[i for i in section['article_ids'] if i!=identifier]
        (source/'topic_map.json').write_text(json.dumps(catalog))
        with self.assertRaises(a.AgricultureError):self.install(source=source,apply=True)
        for track in catalog['tracks']:
            track['primary_article_count']=sum(r.get('primary_track')==track['id'] for r in catalog['articles'])
        (source/'topic_map.json').write_text(json.dumps(catalog))
        self.assertEqual(self.install(source=source,apply=True)['create'],129)
    def test_revocation_corruption_and_transaction_source_race(self):
        self.install(apply=True);item=a.entities(self.db,'a','w','knowledge')[0];snapshot=a.snapshot_context(self.db,'a','w',{'knowledgeIds':[item['id']]})
        self.db.execute('UPDATE agriculture_entities SET deleted=1 WHERE id=?',(item['id'],));before=self.db.serialize()
        with self.assertRaises(a.AgricultureError):self.install(apply=True)
        with self.assertRaises(a.AgricultureError):a.validate_context(self.db,'a','w',snapshot)
        self.assertEqual(before,self.db.serialize())
    def test_capacity_and_source_race_preserve_existing_records(self):
        for n in range(71):a.insert(self.db,'a','w','knowledge',{'title':str(n),'excerpts':[]})
        before=self.db.serialize()
        self.assertFalse(self.install()['capacity']['knowledge']['fits'])
        with self.assertRaises(a.AgricultureError):self.install(apply=True)
        self.assertEqual(before,self.db.serialize());self.assertEqual(self.tree(),[])
    def test_changed_source_during_transaction_leaves_no_partial_import(self):
        source=self.copied();real=lib.snapshot;calls=0
        def changed(path):
            nonlocal calls
            result=real(path);calls+=1
            if calls==1:
                article=next((source/'articles').glob('MON*.md'));article.write_bytes(article.read_bytes()+b'\nINDEPENDENT_RACE\n')
            return result
        before=self.db.serialize()
        with patch.object(lib,'snapshot',side_effect=changed):
            with self.assertRaises(a.AgricultureError):self.install(source=source,apply=True)
        self.assertEqual(before,self.db.serialize());self.assertEqual(self.tree(),[])
    def test_tampered_original_and_catalog_conflict_are_atomic(self):
        source=self.copied();self.install(source=source,apply=True)
        item=a.entities(self.db,'a','w','knowledge')[0];path,_=a.asset_content(self.db,'a',item['assetId'],self.root);original=path.read_bytes();path.write_bytes(original+b'CORRUPTED')
        before=self.db.serialize();files=self.tree()
        with self.assertRaises(a.AgricultureError):self.install(source=source,apply=True)
        self.assertEqual(before,self.db.serialize());self.assertEqual(files,self.tree());path.write_bytes(original)
        catalog=source/'topic_map.json';catalog.write_bytes(catalog.read_bytes()+b'\n')
        report=self.install(source=source,apply=True)
        self.assertEqual(report['unchanged'],130);self.assertEqual(report['catalogHash'],lib.sha(catalog.read_bytes()))
        self.assertEqual(before,self.db.serialize())
        data=json.loads(catalog.read_text());data['articles'][0]['version']='v999';catalog.write_text(json.dumps(data))
        with self.assertRaises(a.AgricultureError):self.install(source=source,apply=True)
        self.assertEqual(before,self.db.serialize())
    def test_transaction_capacity_race_rechecked_without_losing_competing_records(self):
        real=lib.inspect;calls=0
        def competing(*args):
            nonlocal calls
            result=real(*args);calls+=1
            if calls==1:
                for n in range(71):a.insert(self.db,'a','w','knowledge',{'title':'competitor-'+str(n),'excerpts':[]})
            return result
        with patch.object(lib,'inspect',side_effect=competing):
            with self.assertRaises(a.AgricultureError):self.install(apply=True)
        items=a.entities(self.db,'a','w','knowledge');self.assertEqual(len(items),71);self.assertTrue(all(i['title'].startswith('competitor-') for i in items));self.assertEqual(self.tree(),[])
