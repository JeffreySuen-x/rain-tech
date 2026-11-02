"""Explicit local tutorial import. No source paths are accepted over HTTP."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from . import agriculture as a

LIBRARY_ID = 'ai-agriculture-tutorials-v1'
DECLARATION = '来源教程与合成练习，非现场农艺处方。'
EXPECTED = {'MON': 77, 'EDU': 52, 'BASE': 1}

def fail(message):
    raise a.AgricultureError('library_conflict', message, 409)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def safe_file(root, relative):
    path = root / relative
    relative_parts = Path(relative).parts
    if Path(relative).is_absolute() or '..' in relative_parts or any((root.joinpath(*relative_parts[:index])).is_symlink() for index in range(len(relative_parts) + 1)):
        fail('源路径不得包含符号链接：' + relative)
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        fail('源文件缺失或越界：' + relative)
    return path

def packed(text):
    lines = text.splitlines(keepends=True)
    blocks, current, start = [], '', 1
    for number, line in enumerate(lines, 1):
        if len(line) > 2000:
            fail('单行超过2000字符，需要显式分页。')
        if current and len(current) + len(line) > 2000:
            blocks.append({'locator': f'L{start}-L{number-1}', 'text': current})
            current, start = '', number
        current += line
    if current:
        blocks.append({'locator': f'L{start}-L{len(lines)}', 'text': current})
    if not blocks or len(blocks) > 20:
        fail('正文为空或超过20块，需要显式分页。')
    return blocks

def snapshot(source):
    root = Path(source).absolute()
    catalog_raw = safe_file(root, 'topic_map.json').read_bytes()
    try:
        catalog = json.loads(catalog_raw.decode('utf-8'))
    except (ValueError, UnicodeError):
        fail('目录必须为UTF-8 JSON。')
    memberships = {}
    order = 0
    if len(set(catalog['shared_entry'])) != len(catalog['shared_entry']):
        fail('共同基础重复引用。')
    for identifier in catalog['shared_entry']:
        order += 1
        memberships.setdefault(identifier, []).append(dict(trackId='shared', trackTitle='共同基础', groupId='shared', groupTitle='共同基础', sectionLabel='共同基础', order=order))
    if len(catalog['tracks']) != 2:
        fail('需要两个学习方向。')
    track_ids = [track['id'] for track in catalog['tracks']]
    if len(set(track_ids)) != len(track_ids) or 'shared' in track_ids or any(not isinstance(i, str) or not i for i in track_ids):
        fail('学习方向ID无效或重复。')
    for track in catalog['tracks']:
        group_ids_unique = [group['id'] for group in track['groups']]
        if len(set(group_ids_unique)) != len(group_ids_unique) or any(not isinstance(i, str) or not i for i in group_ids_unique):
            fail('分组ID无效或重复。')
        if len(track['groups']) != 6 or track.get('group_count') != len(track['groups']):
            fail('每个方向需要六组。')
        for group in track['groups']:
            group_ids = []
            for section in group['sections']:
                if len(section['article_ids']) != len(set(section['article_ids'])):
                    fail('section重复文章ID。')
                for identifier in section['article_ids']:
                    order += 1
                    member = dict(trackId=track['id'], trackTitle=track['title'], groupId=group['id'], groupTitle=group['title'], sectionLabel=section['label'], order=order)
                    if group.get('reading_goal'):
                        member['readingGoal'] = group['reading_goal']
                    memberships.setdefault(identifier, []).append(member)
                    group_ids.append(identifier)
            if set(group.get('article_ids', group_ids)) != set(group_ids):
                fail('组目录与section引用不一致。')
    files = {}
    articles = root / 'articles'
    if articles.is_symlink() or not articles.is_dir():
        fail('articles目录不可用。')
    for path in sorted(articles.iterdir()):
        if path.suffix.lower() != '.md':
            continue
        safe_file(root, 'articles/' + path.name)
        if path.name == 'README.md':
            continue
        match = re.match(r'^(MON|EDU|BASE)-[0-9]+(?=_|\.|$)', path.name)
        if not match:
            fail('未知文章文件名：' + path.name)
        identifier = match.group()
        if identifier == 'BASE-001':
            continue
        if identifier in files:
            fail('重复文章ID：' + identifier)
        files[identifier] = path
    counts = {prefix: sum(i.startswith(prefix + '-') for i in files) for prefix in EXPECTED}
    if not 1 <= len(files) <= 200 or set(files) != set(memberships) or catalog.get('effective_articles') != len(files):
        fail('实物、目录与effective_articles计数不一致（须1至200篇）。')
    records = catalog.get('articles', [])
    article_map = {record['id']: record for record in records}
    if len(article_map) != len(records) or set(article_map) != set(files):
        fail('articles目录索引不一致。')
    for track in catalog['tracks']:
        actual = sum(record.get('primary_track') == track['id'] for record in records)
        if type(track.get('primary_article_count')) is not int or track['primary_article_count'] != actual:
            fail('学习方向primary_article_count不一致。')
    for record in records:
        identifier = record['id']
        primary = record.get('primary_track')
        if primary not in track_ids + ['shared'] or not any(m['trackId'] == primary for m in memberships[identifier]):
            fail('文章primary_track与导航引用不一致。')
        if primary != 'shared' and not any(m['trackId'] == primary and m['groupId'] == record.get('primary_group') for m in memberships[identifier]):
            fail('文章primary_group与导航引用不一致。')
        if primary == 'shared' and identifier not in catalog['shared_entry']:
            fail('共同基础归属不一致。')
    plans = []
    for identifier, path in sorted(files.items()):
        record = article_map[identifier]
        if record.get('href') != 'articles/' + path.name or not isinstance(record.get('version'), str) or not record['version']:
            fail('目录路径或版本无效：' + identifier)
        raw = path.read_bytes()
        try:
            text = raw.decode('utf-8')
        except UnicodeError:
            fail('文章必须为UTF-8：' + identifier)
        if not raw or len(raw) > a.MAX_FILE or not text.strip():
            fail('正文为空或过大：' + identifier)
        front = {}
        body = text
        if text.startswith('---\n') and '\n---' in text[4:]:
            header, body = text[4:].split('\n---', 1)
            for line in header.splitlines():
                if ':' in line:
                    key, value = line.split(':', 1)
                    front[key.strip()] = value.strip().strip('\"\'')
        if front.get('stableID', identifier) != identifier:
            fail('frontmatter ID不一致：' + identifier)
        heading = re.search(r'^#\s+(.+)$', body, re.M)
        title = front.get('title') or (heading.group(1).strip() if heading else '')
        if not title or len(title) > 200 or not body.strip():
            fail('标题或正文无效：' + identifier)
        summary = ' '.join(line.strip() for line in body.splitlines() if line.strip() and not line.lstrip().startswith(('#', '<!--')))[:240]
        library = dict(id=LIBRARY_ID, articleId=identifier, sourceRelativePath='articles/' + path.name, catalogHash=sha(catalog_raw), contentType='tutorial', memberships=memberships[identifier], sourceVersion=record['version'])
        payload = dict(title=title, sourceHash=sha(raw), version=1, excerpts=packed(text), warnings=[DECLARATION], summary=summary, category=memberships[identifier][0]['trackTitle'], library=library)
        plans.append(dict(key=LIBRARY_ID + ':' + identifier, raw=raw, payload=payload))
    return plans, counts

def comparable(payload):
    return {**{k: v for k, v in payload.items() if k not in {'assetId', 'library'}},
            'library': {k: v for k, v in payload.get('library', {}).items() if k != 'catalogHash'}}

def inspect(db, owner, workspace, root, plans):
    a.workspace(db, owner, workspace)
    states = []
    for plan in plans:
        rows = db.execute("SELECT * FROM agriculture_entities WHERE owner=? AND workspace_id=? AND kind='knowledge' AND business_key=?", (owner, workspace, plan['key'])).fetchall()
        state, reason = 'create', None
        if rows:
            state = 'unchanged'
            try:
                if len(rows) != 1 or rows[0]['deleted']:
                    fail('已删除或身份冲突')
                item = json.loads(rows[0]['payload'])
                if comparable(item) != comparable(plan['payload']):
                    fail('内容或用户元数据改变')
                path, asset = a.asset_content(db, owner, item['assetId'], root)
                if asset['workspaceId'] != workspace or asset['sha256'] != plan['payload']['sourceHash']:
                    fail('原件归属或哈希改变')
            except (a.AgricultureError, KeyError, ValueError) as error:
                state, reason = 'conflict', str(error)
        entry = dict(articleId=plan['payload']['library']['articleId'], sourceRelativePath=plan['payload']['library']['sourceRelativePath'], sha256=plan['payload']['sourceHash'], state=state, reason=reason)
        if state == 'unchanged':
            entry.update(knowledgeId=rows[0]['id'], assetId=item['assetId'])
        states.append(entry)
    creates = sum(s['state'] == 'create' for s in states)
    capacity = {}
    for kind, maximum in [('asset', a.MAX_ASSETS), ('knowledge', a.MAX_KNOWLEDGE)]:
        used = db.execute('SELECT count(*) FROM agriculture_entities WHERE owner=? AND workspace_id=? AND kind=? AND deleted=0', (owner, workspace, kind)).fetchone()[0]
        capacity[kind] = dict(used=used, additional=creates, maximum=maximum, fits=used + creates <= maximum)
    return states, capacity

def install(db, owner, workspace, root, source, apply=False):
    if Path(root).resolve().is_relative_to(Path(source).resolve()):
        fail('私有资产目录不得位于只读源目录内。')
    plans, counts = snapshot(source)
    states, capacity = inspect(db, owner, workspace, root, plans)
    report = dict(dryRun=not apply, libraryId=LIBRARY_ID, catalogHash=plans[0]['payload']['library']['catalogHash'], counts=counts, items=states, capacity=capacity, **{state: sum(s['state'] == state for s in states) for state in ('create', 'unchanged', 'conflict')})
    if not apply:
        return report
    if report['conflict'] or not all(c['fits'] for c in capacity.values()):
        fail('导入冲突或容量不足；整批停止。')
    created = []
    try:
        with a.atomic(db):
            if snapshot(source) != (plans, counts) or inspect(db, owner, workspace, root, plans) != (states, capacity):
                fail('源文件、身份或容量在计划后改变。')
            for plan, state in zip(plans, states):
                if state['state'] == 'unchanged':
                    continue
                key = a.save_file(root, plan['raw'])
                created.append(key)
                payload = plan['payload']
                asset = a.insert(db, owner, workspace, 'asset', dict(kind='document', name=Path(payload['library']['sourceRelativePath']).name, mediaType='text/markdown', byteSize=len(plan['raw']), sha256=payload['sourceHash'], storageKey=key, status='ready', error=None, version=1, warnings=payload['warnings']))
                item = a.insert(db, owner, workspace, 'knowledge', {**payload, 'assetId': asset['id']}, business_key=plan['key'])
                state.update(assetId=asset['id'], knowledgeId=item['id'])
            if snapshot(source) != (plans, counts):
                fail('源文件在提交前改变。')
        return report
    except BaseException:
        for key in created:
            (Path(root).resolve() / key).unlink(missing_ok=True)
        raise

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('db', 'assets', 'owner', 'workspace', 'source'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    # Dry-run must not create a missing database or initialize schema.
    if not Path(args.db).is_file():
        parser.error('database must already exist')
    if Path(args.db).resolve().is_relative_to(Path(args.source).resolve()):
        parser.error('database must be outside the read-only source directory')
    import sqlite3
    db = sqlite3.connect('file:' + str(Path(args.db).resolve()) + ('?mode=rw' if args.apply else '?mode=ro'), uri=True, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        print(json.dumps(install(db, args.owner, args.workspace, args.assets, args.source, args.apply), ensure_ascii=False, indent=2))
    finally:
        db.close()

if __name__ == '__main__':
    main()
