"""Explicit local-only, dry-run-first original reference installer.
Run: python -m server.workspace_seed --db PATH --assets PATH --owner ID [--apply]
"""
import argparse
import hashlib
import json
from pathlib import Path
from . import agriculture as a
# Public fixture identity, deliberately unrelated to any existing installation.
WORKSPACE='shuyu-demo-workspace-v1'
def install(db,owner,root,source=None,workspace=WORKSPACE,apply=False):
    if workspace!=WORKSPACE:a.invalid('仅允许固定演示园区。')
    a.workspace(db,owner,workspace)
    source=Path(source or Path(__file__).resolve().parents[1]/'docs/knowledge/grape')
    files=sorted(source.glob('*.md'))
    if len(files)!=6:a.invalid('需要完整六篇原创资料。')
    legacy=legacy_plan(db,owner,workspace,root)
    plans=[]
    for path in files:
        raw=path.read_bytes()
        first=raw.decode('utf-8').splitlines()[0]
        title=first[2:].strip() if first.startswith('# ') else ''
        if not title or len(title)>197 or any(c in title for c in ('/',chr(92),chr(0))) or title in {'.','..'}:a.invalid('原创资料首行标题无效。')
        digest=hashlib.sha256(raw).hexdigest(); key='shuyu-original-v1:'+path.stem
        rows=db.execute('SELECT * FROM agriculture_entities WHERE owner=? AND workspace_id=? AND business_key=?',(owner,workspace,key)).fetchall()
        if len(rows)>1:a.invalid('seed身份冲突。')
        state='create'
        if rows:
            row=rows[0]; item=a.unpack(row)
            if row['deleted']:raise a.AgricultureError('seed_conflict','已撤销的seed不会自动恢复。',409)
            if item.get('sourceHash')!=digest:raise a.AgricultureError('seed_conflict','内容版本改变，需要显式升级。',409)
            a.asset_content(db,owner,item['assetId'],root); state='unchanged'
        plans.append(dict(file=path.name,title=title,key=key,state=state,sha256=digest))
    if not apply:return {'dryRun':True,'items':plans,'legacySeed':legacy}
    created=[]
    try:
        with a.atomic(db):
            if legacy_plan(db,owner,workspace,root)!=legacy:raise a.AgricultureError('seed_conflict','历史seed在计划后发生改变。',409)
            for planned in plans:
                current=db.execute('SELECT * FROM agriculture_entities WHERE owner=? AND workspace_id=? AND business_key=?',(owner,workspace,planned['key'])).fetchall()
                if planned['state']=='create':
                    if current:raise a.AgricultureError('seed_conflict','seed在计划后发生改变。',409)
                elif len(current)!=1 or current[0]['deleted'] or a.unpack(current[0]).get('sourceHash')!=planned['sha256']:
                    raise a.AgricultureError('seed_conflict','seed在计划后发生改变。',409)
                else:a.asset_content(db,owner,a.unpack(current[0])['assetId'],root)
            if legacy["state"]=="repair":repair_legacy(db,owner,workspace,root,legacy,created)
            for plan,path in zip(plans,files):
                if plan['state']=='unchanged':continue
                result=a.upload(db,owner,workspace,{'commandId':plan['key']+':'+plan['sha256'],'kind':'document'},path.read_bytes(),plan['title']+'.md',root)
                created.append(a.read(db,owner,result['asset']['id'],'asset',workspace)['storageKey'])
                a.update(db,owner,result['knowledge']['id'],'knowledge',{**result['knowledge'],'title':plan['title']})
                db.execute('UPDATE agriculture_entities SET business_key=? WHERE id=?',(plan['key'],result['knowledge']['id']))
        return {'dryRun':False,'items':plans,'legacySeed':legacy}
    except BaseException:
        # Outer rollback also rolls upload commands back; remove only orphan files.
        for key in created:
            if key:(Path(root)/key).unlink(missing_ok=True)
        raise
LEGACY_KEY='shuyu-legacy-inspection-v2'
LEGACY_PAYLOAD={'title':'【模拟】园区巡查资料','assetId':None,'version':1,'sourceHash':a.digest('模拟园区巡查演示v1'),'excerpts':[{'locator':'demo:inspection','text':'【模拟演示】巡查时记录叶背、整株、邻株及地块位置；复核棚内湿度与通风记录。24.6°C、84%为固定历史3小时手工模拟趋势，非实时硬件。历史32°C记录保留，不代表当前状态。机器人、土壤接口尚未接入。'}],'warnings':['模拟演示资料，不构成现场事实或诊断。']}
def legacy_plan(db,owner,wid,root):
    rows=db.execute("SELECT * FROM agriculture_entities WHERE owner=? AND workspace_id=? AND kind='knowledge'",(owner,wid)).fetchall()
    migrated=[r for r in rows if r['business_key']==LEGACY_KEY]
    if migrated:
        if len(migrated)!=1 or migrated[0]['deleted']:raise a.AgricultureError('seed_conflict','历史seed已撤销或身份冲突。',409)
        item=a.unpack(migrated[0]);a.asset_content(db,owner,item['assetId'],root)
        return dict(state='unchanged',id=item['id'])
    receipt=db.execute("SELECT * FROM commands WHERE owner=? AND scope='offline-demo-restore-v1' AND key=?",(owner,wid)).fetchone()
    if not receipt:return dict(state='absent')
    try:
        response=json.loads(receipt['response'])
        if response.get('workspaceId')!=wid or response.get('sourceDigest')!=receipt['digest'] or len(receipt['digest'])!=64:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise a.AgricultureError('seed_conflict','恢复回执损坏。',409)
    matching=[r for r in rows if json.loads(r['payload'])==LEGACY_PAYLOAD]
    if len(matching)!=1 or matching[0]['deleted']:raise a.AgricultureError('seed_conflict','历史seed已编辑、删除或身份歧义。',409)
    return dict(state='repair',id=matching[0]['id'],oldPayloadHash=a.digest(LEGACY_PAYLOAD))
def repair_legacy(db,owner,wid,root,plan,created):
    from .agriculture_materials import extract
    raw=('# 历史演示巡查档案\n\n版本：2。原历史模拟正文归档，不代表当前在线设备或当前园区事实。\n\n'+LEGACY_PAYLOAD['excerpts'][0]['text']+'\n').encode()
    excerpts,warnings=extract(raw,'legacy-demo-inspection.md')
    if len(a.entities(db,owner,wid,'asset',201))>=200:raise a.AgricultureError('too_large','资产已达上限。',413)
    key=a.save_file(root,raw);created.append(key);hashed=hashlib.sha256(raw).hexdigest()
    asset=a.insert(db,owner,wid,'asset',dict(kind='document',name='历史演示巡查档案.md',mediaType='text/markdown',byteSize=len(raw),sha256=hashed,storageKey=key,status='ready',error=None,version=1,warnings=warnings))
    item={**LEGACY_PAYLOAD,'assetId':asset['id'],'version':2,'sourceHash':hashed,'excerpts':excerpts,'warnings':['历史演示档案；设备未接入等描述仅为旧版本背景，不代表当前事实。'],'upgrade':{'fromVersion':1,'fromPayloadHash':plan['oldPayloadHash'],'reason':'明确恢复seed补齐可追溯原件'}}
    a.update(db,owner,plan['id'],'knowledge',item)
    db.execute('UPDATE agriculture_entities SET business_key=? WHERE id=?',(LEGACY_KEY,plan['id']))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--assets',required=True);p.add_argument('--owner',required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
    from .app import connect
    import json
    db=connect(args.db)
    try:print(json.dumps(install(db,args.owner,Path(args.assets),apply=args.apply),ensure_ascii=False,indent=2))
    finally:db.close()
