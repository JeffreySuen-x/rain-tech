"""Offline, fixed synthetic QA workspace import. Dry run is the default.

No account/session/credential import, runtime startup, inference or scheduling.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import uuid
from . import agriculture as ag

SOURCE_USER = 'synthetic-demo-source'
SOURCE_WORKSPACE = 'shuyu-demo-workspace-v1'
SCOPE = 'offline-demo-restore-v1'
TABLES = ('workspaces', 'threads', 'memories', 'turns', 'artifacts', 'agriculture_entities', 'agriculture_device_events', 'agent_runs', 'agent_receipts', 'media_derivations')
JSON_COLUMNS = {'payload', 'sources', 'result', 'provenance'}


def fail(message):
    raise ValueError(message)


def readonly(path):
    path = regular(path)
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('BEGIN')
    return db


def regular(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        fail('Expected a regular non-symlink source file')
    return path


def safe_root(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        fail('Symlink asset root rejected')
    return path


def file_bytes(path):
    path = regular(path)
    if not 0 < path.stat().st_size <= ag.MAX_FILE:
        fail('Invalid asset size')
    return path.read_bytes()


def rewrite_owner(value, old, new):
    if isinstance(value, list):
        return [rewrite_owner(v, old, new) for v in value]
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if k in {'owner', 'ownerId', 'user_id', 'userId'}:
                if v != old:
                    fail('Cross-owner JSON reference')
                result[k] = new
            else:
                result[k] = rewrite_owner(v, old, new)
        return result
    return value


def validate_json_refs(value, known):
    scalar = {'workspaceId':'workspaces','gardenId':'workspaces','threadId':'threads','turnId':'turns','processingTurnId':'turns','artifactId':'artifacts','assetId':'agriculture_entities','mediaAssetId':'agriculture_entities','sourceId':'agriculture_entities','plotId':'agriculture_entities','deviceId':'agriculture_entities','workItemId':'agriculture_entities','alertId':'agriculture_entities','knowledgeId':'agriculture_entities','followUpId':'agriculture_entities','completionRecordId':'agriculture_entities','reportId':'agriculture_entities'}
    plural = {'turnIds':'turns','assetIds':'agriculture_entities','workItemIds':'agriculture_entities','historyMemoryIds':'memories','factIds':'agriculture_entities'}
    if isinstance(value, list):
        for item in value: validate_json_refs(item,known)
    elif isinstance(value, dict):
        if 'id' in value and 'sourceHash' in value and (not isinstance(value['id'],str) or value['id'] not in known['_evidence']):
            fail('Frozen source reference leaves imported workspace')
        for key,item in value.items():
            if key in scalar and item is not None and (not isinstance(item,str) or item not in known[scalar[key]]):
                fail('JSON reference leaves imported workspace')
            if key in plural and (not isinstance(item,list) or any(not isinstance(i,str) or i not in known[plural[key]] for i in item)):
                fail('JSON list reference leaves imported workspace')
            validate_json_refs(item,known)


def json_values(data):
    for records in data.values():
        for row in records:
            for key in JSON_COLUMNS & row.keys():
                if row[key] is not None:
                    try: yield json.loads(row[key])
                    except (TypeError,ValueError): pass


def frozen_hashes(value):
    if isinstance(value, list):
        for item in value: yield from frozen_hashes(item)
    elif isinstance(value, dict):
        if isinstance(value.get('sourceHash'),str): yield value['sourceHash']
        for item in value.values(): yield from frozen_hashes(item)


def rows(db, table, clause, values):
    return [dict(r) for r in db.execute('SELECT * FROM ' + table + ' WHERE ' + clause, values)]


def prepare(source, target, source_assets, target_assets, target_user, prototype_assets):
    """Read all inputs and preflight without changing any file or database."""
    source_assets, target_assets = safe_root(source_assets), safe_root(target_assets)
    prototype_assets = safe_root(prototype_assets)
    old = source.execute('SELECT id FROM users WHERE username=?', (SOURCE_USER,)).fetchone()
    new = target.execute('SELECT id FROM users WHERE username=?', (target_user,)).fetchone()
    if not old or not new:
        fail('Expected existing source and target accounts')
    old, new = old['id'], new['id']
    workspace = rows(source, 'workspaces', 'id=? AND owner=?', (SOURCE_WORKSPACE, old))
    if len(workspace) != 1:
        fail('Synthetic source workspace mismatch')
    data = {'workspaces': workspace}
    for table in ('threads', 'memories', 'turns', 'agriculture_entities'):
        data[table] = rows(source, table, 'workspace_id=?', (SOURCE_WORKSPACE,))
        if any(r['owner'] != old for r in data[table]):
            fail('Cross-owner source row')
    data['artifacts'] = [dict(r) for r in source.execute('SELECT * FROM artifacts') if r['thread_id'] in {t['id'] for t in data['threads']}]
    if any(r['owner'] != old for r in data['artifacts']): fail('Cross-owner artifact')
    turns = {r['id'] for r in data['turns']}
    devices = {r['id'] for r in data['agriculture_entities'] if r['kind'] == 'device'}
    if any(r['status'] not in {'completed', 'failed'} for r in data['turns']):
        fail('Source contains executable turns')
    tables = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ('agent_runs', 'agent_receipts', 'media_derivations'):
        data[table] = [dict(r) for r in source.execute('SELECT * FROM '+table) if r['turn_id'] in turns] if table in tables else []
    if any(r['state'] != 'sealed' for r in data['agent_receipts']):
        fail('Unsealed source receipt')
    data['agriculture_device_events'] = [dict(r) for r in source.execute('SELECT * FROM agriculture_device_events') if r['device_id'] in devices]
    if any(r['owner'] != old for r in data['agriculture_device_events']):
        fail('Cross-owner device event')
    # Validate SQL relationship closure before rewriting any row.
    known = {t: {r.get('id', r.get('turn_id')) for r in rs} for t, rs in data.items()}
    refs = {'workspace_id':'workspaces', 'thread_id':'threads', 'turn_id':'turns', 'source_turn_id':'turns', 'artifact_id':'artifacts', 'device_id':'agriculture_entities'}
    for table, records in data.items():
        for r in records:
            for key, destination in refs.items():
                if r.get(key) and r[key] not in known[destination]:
                    fail('Source relationship leaves imported workspace')
    known['_evidence'] = set().union(*known.values())
    for row in data['agriculture_entities']:
        if row['kind'] == 'device':
            for observation in json.loads(row['payload']).get('latest',{}).values():
                if observation.get('deviceId') == row['id'] and isinstance(observation.get('id'),str): known['_evidence'].add(observation['id'])
    for row in data['agriculture_device_events']:
        for observation in json.loads(row['payload']).get('observations',[]):
            if observation.get('deviceId') != row['device_id']: fail('Cross-device observation')
            if isinstance(observation.get('id'),str): known['_evidence'].add(observation['id'])
    for value in json_values(data): validate_json_refs(value,known)
    referenced_hashes = {h for value in json_values(data) for h in frozen_hashes(value)}
    # Reject changes to any complete entity which is itself frozen as evidence.
    frozen_entities = {}
    for row in data['agriculture_entities']:
        value = ag.unpack(row)
        hashed = ag.digest(value)
        if hashed in referenced_hashes: frozen_entities[row['id']] = hashed
    files = {}
    for r in data['agriculture_entities']:
        if r['kind'] == 'asset':
            p = json.loads(r['payload']); key = p['storageKey']
            if len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
                fail('Invalid source storage key')
            raw = file_bytes(source_assets / key)
            if len(raw) != p['byteSize'] or hashlib.sha256(raw).hexdigest() != p['sha256']:
                fail('Source asset hash mismatch')
            files[key] = raw
    # Identity includes the complete selected records and all asset bytes, never credentials.
    fingerprint = ag.digest({'rows': data, 'assets': {k: hashlib.sha256(v).hexdigest() for k,v in files.items()}, 'prototype': {n: hashlib.sha256(file_bytes(prototype_assets/n)).hexdigest() for n in ('vineyard.png','grape-leaf.png')}})
    receipt = target.execute('SELECT digest,response FROM commands WHERE owner=? AND scope=? AND key=?', (new,SCOPE,SOURCE_WORKSPACE)).fetchone()
    if receipt:
        if receipt['digest'] != fingerprint:
            fail('Import identity conflicts with earlier source')
        return {'noop': True, 'workspaceId': SOURCE_WORKSPACE}, {}, {}, new, fingerprint
    for table, records in data.items():
        for r in records:
            if 'owner' in r: r['owner'] = new
            for key in JSON_COLUMNS & r.keys():
                if r[key] is not None:
                    try: value = json.loads(r[key])
                    except (TypeError, ValueError): continue  # turn.result can be plain text
                    r[key] = ag.encode(rewrite_owner(value, old, new))
            if table == 'workspaces': r['name'] = '我的葡萄园 · 模拟数据（历史演示）'
            if table == 'threads': r['title'] = '【模拟历史】' + r['title']
            if table == 'artifacts': r['title'] = '【模拟历史】' + r['title']
            if table == 'turns': r['lease_until'] = None
            if table == 'agriculture_entities':
                p = json.loads(r['payload'])
                if r['kind'] == 'device':
                    p.pop('credentialHash', None); p['lastSeenAt'] = p['lastDeviceSeenAt'] = None
                    p['name'] = '【模拟】' + p['name']
                if r['kind'] == 'follow_up':
                    p.update(enabled=False,remainingRuns=0,nextDueAt=None,authorizationVersion=0)
                    p.pop('authorizedAt',None)
                if r['kind'] in {'asset','knowledge','report'}:
                    for key in ('name','title'):
                        if key in p: p[key] = '【模拟历史】' + p[key]
                r['payload'] = ag.encode(p)
                if r['id'] in frozen_entities and ag.digest(ag.unpack(r)) != frozen_entities[r['id']]:
                    fail('Import would change frozen evidence hash')
    # Fail before writing on every PK or business-key collision (including composite keys).
    for table, records in data.items():
        source_columns = [r['name'] for r in source.execute('PRAGMA table_info('+table+')')] if table in tables else []
        target_columns = [r['name'] for r in target.execute('PRAGMA table_info('+table+')')]
        if records and source_columns != target_columns: fail('Schema mismatch')
        pk = [r['name'] for r in target.execute('PRAGMA table_info('+table+')') if r['pk']]
        for r in records:
            if target.execute('SELECT 1 FROM '+table+' WHERE '+' AND '.join(k+'=?' for k in pk),tuple(r[k] for k in pk)).fetchone():
                fail('Existing target primary key collision')
    if target.execute('SELECT 1 FROM agriculture_entities WHERE owner=? AND workspace_id=?',(new,SOURCE_WORKSPACE)).fetchone():
        fail('Existing target workspace data collision')
    for key in files:
        if (target_assets / key).exists(): fail('Existing target asset collision')
    return {'noop':False,'workspaceId':SOURCE_WORKSPACE,'rows':{k:len(v) for k,v in data.items()},'assets':len(files)+2,'sourceDigest':fingerprint,'identityMapping':{t:[r.get('id',r.get('turn_id',r.get('source_event_id'))) for r in rs] for t,rs in data.items()},'prototypeHashes':{n:hashlib.sha256(file_bytes(prototype_assets/n)).hexdigest() for n in ('vineyard.png','grape-leaf.png')}}, data, files, new, fingerprint


def supplement(db, owner, wid, root, prototype, created, expected_hashes):
    plot = db.execute("SELECT id FROM agriculture_entities WHERE workspace_id=? AND kind='plot'",(wid,)).fetchone()['id']
    sensor = ag.insert(db,owner,wid,'device',{'name':'模拟温湿度 · 手工演示（未接入）','plotId':plot,'kind':'sensor','source':'test','staleAfterSeconds':3600,'thresholds':{},'ruleVersion':1,'lastSeenAt':None,'lastDeviceSeenAt':None,'latest':{}})
    ag.insert(db,owner,wid,'device',{'name':'模拟摄像头 · 待接入','plotId':plot,'kind':'camera','source':'test','staleAfterSeconds':3600,'thresholds':{},'ruleVersion':1,'lastSeenAt':None,'lastDeviceSeenAt':None,'latest':{}})
    # Frozen historical window, not a live hardware feed.
    end = 1792947600.0
    for index, (temp,humidity) in enumerate(((25.3,80),(25.0,82),(24.8,83),(24.6,84))):
        ag.ingest_event(db,owner,sensor['id'],{'commandId':'demo-observation-'+str(index),'sourceEventId':'demo-'+str(index),'observedAt':end-(3-index)*3600,'source':'test','readings':[{'metric':'temperature','value':temp,'unit':'celsius'},{'metric':'humidity','value':humidity,'unit':'percent'}]})
    for title in ('补拍叶背与整株，检查邻近植株','复核棚内湿度与通风记录'):
        ag.insert(db,owner,wid,'work_item',{'title':'【模拟】'+title,'description':'历史演示待办；需现场核实，不自动跟进。','status':'open','completedAt':None,'plotId':plot,'alertId':None,'dueAt':None,'followUpAt':None})
    for name in ('grape-leaf.png','vineyard.png'):
        raw = file_bytes(Path(prototype)/name)
        if hashlib.sha256(raw).hexdigest() != expected_hashes[name]: fail('Prototype changed after planning')
        key = write_asset(root,raw,created)
        ag.insert(db,owner,wid,'asset',{'kind':'image','name':'模拟原型图片 · '+name,'mediaType':'image/png','byteSize':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'storageKey':key,'status':'stored','error':None,'version':1,'warnings':['模拟原型素材，非现场采集；未执行AI分析。']})
    ag.insert(db,owner,wid,'knowledge',{'title':'【模拟】园区巡查资料','assetId':None,'version':1,'sourceHash':ag.digest('模拟园区巡查演示v1'),'excerpts':[{'locator':'demo:inspection','text':'【模拟演示】巡查时记录叶背、整株、邻株及地块位置；复核棚内湿度与通风记录。24.6°C、84%为固定历史3小时手工模拟趋势，非实时硬件。历史32°C记录保留，不代表当前状态。机器人、土壤接口尚未接入。'}],'warnings':['模拟演示资料，不构成现场事实或诊断。']})


def write_asset(root, raw, created, key=None):
    key = key or uuid.uuid4().hex
    path = root/key
    fd = os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    created.append(path)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(raw).digest(): fail('Written asset hash mismatch')
    return key


def restore(source_db, source_assets, target_db, target_assets, target_user, prototype_assets, apply=False):
    if Path(source_db).resolve() == Path(target_db).resolve(): fail('Source and target must differ')
    if safe_root(source_assets) == safe_root(target_assets): fail('Asset roots must differ')
    with contextlib.closing(readonly(source_db)) as source, contextlib.closing(readonly(target_db)) as target:
        plan,data,files,owner,fingerprint = prepare(source,target,source_assets,target_assets,target_user,prototype_assets)
    if not apply or plan['noop']: return plan
    root = safe_root(target_assets)
    if root.exists() and (stat.S_IMODE(root.stat().st_mode) != 0o700 or root.stat().st_uid != os.getuid()): fail('Target asset directory must be private')
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    target_path = regular(target_db)
    if target_path.stat().st_uid != os.getuid() or stat.S_IMODE(target_path.stat().st_mode) != 0o600: fail('Target database must be private')
    backup = target_path.with_name(target_path.name+'.demo-backup-'+uuid.uuid4().hex+'.sqlite')
    fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd)
    created=[]
    with contextlib.closing(sqlite3.connect(target_path,isolation_level=None)) as db:
        db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        with contextlib.closing(sqlite3.connect(backup)) as copy: db.backup(copy)
        try:
            db.execute('BEGIN IMMEDIATE'); db.execute('PRAGMA defer_foreign_keys=ON')
            # Recheck collisions and receipt under the writer lock.
            with contextlib.closing(readonly(source_db)) as source:
                current,data,files,owner,current_hash=prepare(source,db,source_assets,target_assets,target_user,prototype_assets)
            if current_hash != fingerprint: fail('Source changed after planning')
            if current['noop']:
                db.execute('ROLLBACK'); return current
            for key,raw in files.items(): write_asset(root,raw,created,key)
            for table in TABLES:
                for record in data[table]:
                    names=list(record)
                    db.execute('INSERT INTO '+table+' ('+','.join(names)+') VALUES ('+','.join('?' for _ in names)+')',tuple(record[k] for k in names))
            supplement(db,owner,SOURCE_WORKSPACE,root,prototype_assets,created,current['prototypeHashes'])
            if db.execute('PRAGMA foreign_key_check').fetchone(): fail('Foreign key check failed')
            db.execute('INSERT INTO commands VALUES(?,?,?,?,?)',(owner,SCOPE,SOURCE_WORKSPACE,fingerprint,ag.encode(plan)))
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction: db.execute('ROLLBACK')
            for path in created: path.unlink(missing_ok=True)
            raise
    return {**plan,'backup':str(backup),'applied':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-db','source-assets','target-db','target-assets','target-user','prototype-assets'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--apply',action='store_true',help='Without this flag, only produce a dry-run plan')
    args=vars(parser.parse_args())
    try: print(ag.encode(restore(**args)))
    except (ValueError,OSError,sqlite3.Error,KeyError) as error:
        parser.exit(2,'Demo restore rejected: '+type(error).__name__+' (no private values logged)\n')

if __name__=='__main__': main()
