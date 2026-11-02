"""Bounded, explicitly enabled virtual scene; shares the existing SQLite worker."""
import copy
import json
import math
import time
import uuid
from . import agriculture as a

LABEL = '演示模式 · 设备与画面为模拟'
SCENARIOS = {'normal', 'humidity_change', 'leaf_anomaly'}

def migrate(db):
    db.execute('CREATE TABLE IF NOT EXISTS agriculture_live_demo(workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id),owner TEXT NOT NULL REFERENCES users(id),enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),version INTEGER NOT NULL,state TEXT NOT NULL CHECK(json_valid(state)),updated_at REAL NOT NULL)')

def save(db, row, state, at):
    db.execute('UPDATE agriculture_live_demo SET state=?,version=version+1,updated_at=? WHERE workspace_id=? AND owner=?', (a.encode(state), at, row['workspace_id'], row['owner']))

def event(s, at, kind, message):
    s['events'].append(dict(id=uuid.uuid4().hex,plotId=s['plotIds'][0],kind=kind,severity='warning' if kind!='normal' else 'info',message=message,observedAt=at,origin='demo'))
    s['events']=s['events'][-30:]

def enable_demo(db, owner, workspace_id, at=None, asset_ids=None):
    """Local administrative entry point. Never exposed by HTTP."""
    at=time.time() if at is None else a.timestamp(at)
    with a.atomic(db):
        a.workspace(db,owner,workspace_id)
        if db.execute('SELECT 1 FROM agriculture_live_demo WHERE workspace_id=?',(workspace_id,)).fetchone():return
        plots=a.entities(db,owner,workspace_id,'plot')
        if not plots:a.invalid('演示需要已有地块。')
        assets=[a.read(db,owner,i,'asset',workspace_id) for i in asset_ids] if asset_ids is not None else [x for x in a.entities(db,owner,workspace_id,'asset') if '模拟原型图片' in x.get('name','')]
        if any(x.get('kind')!='image' for x in assets):a.invalid('演示画面必须是图片。')
        plot=plots[0]['id']; route=[dict(x=.1,y=.2),dict(x=.9,y=.2),dict(x=.9,y=.8),dict(x=.1,y=.2)]
        s=dict(paused=False,lastTickAt=at,scenario='normal',scenarioStartedAt=at,sampleSequence=0,plotIds=[plot],samples=[],events=[],captures=[],cameras=[dict(id='demo-camera-'+str(i+1),plotId=plot,name=['棚区全景','作物近景'][i],assetId=assets[i%len(assets)]['id'],status='online',observedAt=at) for i in range(2)] if assets else [],robot=dict(id='demo-robot-1',plotId=plot,name='巡检机器人',state='idle',position=route[0],route=route,battery=100,progress=0,observedAt=at))
        sample(s,at)
        db.execute('INSERT INTO agriculture_live_demo VALUES(?,?,1,1,?,?)',(workspace_id,owner,a.encode(s),at))

def sample(s,at):
    s['sampleSequence']+=1
    previous=s['samples'][-1]['humidity'] if s['samples'] else 68
    target=88 if s['scenario']=='humidity_change' else 68
    humidity=round(previous+max(-2,min(2,target-previous)),1)
    for plot in s['plotIds']:s['samples'].append(dict(plotId=plot,observedAt=at,temperature=round(25.4+math.sin(s['sampleSequence']/6)*.6,1),humidity=humidity,soil_moisture=round(42+math.sin(s['sampleSequence']/9),1)))
    s['samples']=s['samples'][-120*len(s['plotIds']):]
    for c in s['cameras']:c['observedAt']=at
    r=s['robot']; r['observedAt']=at
    if r['battery']<=15 and r['state']=='patrolling':r['state']='returning'
    if r['state'] in {'patrolling','returning'}:
        r['progress']=min(100,r['progress']+4) if r['state']=='patrolling' else max(0,r['progress']-4)
        p=r['progress']/100*3; index=min(2,int(p)); f=p-index
        r['position']={k:round(r['route'][index][k]*(1-f)+r['route'][index+1][k]*f,4) for k in ('x','y')}
        r['battery']=max(0,round(r['battery']-.15,2))
        if r['progress'] in (0,100):
            r['state']='docked'; event(s,at,'normal','演示机器人已到基站。')
    elif r['state']=='docked':r['battery']=min(100,round(r['battery']+.1,2))

def advance(db,at=None):
    at=time.time() if at is None else at
    with a.atomic(db):
        for row in db.execute('SELECT * FROM agriculture_live_demo WHERE enabled=1').fetchall():
            s=json.loads(row['state'])
            if s['paused'] or at-s['lastTickAt']<5:continue
            s['lastTickAt']=at; sample(s,at); save(db,row,s,at)

def view(db,owner,wid,plot_id=None,at=None):
    at=time.time() if at is None else at
    a.workspace(db,owner,wid); a.relation(db,owner,wid,plot_id,'plot')
    row=db.execute('SELECT * FROM agriculture_live_demo WHERE workspace_id=? AND owner=? AND enabled=1',(wid,owner)).fetchone()
    if not row:return None
    s=json.loads(row['state']); observed=s['samples'][-1]['observedAt'] if s['samples'] else None
    result=dict(mode='demo',enabled=True,label=LABEL,version=row['version'],paused=s['paused'],scenario=s['scenario'],observedAt=observed,serverTime=at,staleAfterSeconds=20,status='paused' if s['paused'] else ('disconnected' if observed is None else ('stale' if at-observed>20 else 'online')),origin='demo')
    valid_plots={p['id'] for p in a.entities(db,owner,wid,'plot')}
    for key in ('samples','events','captures','cameras'):
        result[key]=[x for x in s[key] if x['plotId'] in valid_plots and (plot_id is None or x['plotId']==plot_id)]
    for c in result['cameras']+result['captures']:
        try:
            asset=a.read(db,owner,c['assetId'],'asset',wid)
            if asset.get('demoSourceAssetId'):a.read(db,owner,asset['demoSourceAssetId'],'asset',wid)
        except a.AgricultureError:c['assetId']=None;c['status']='disconnected'
    result['robot']=s['robot'] if s['robot']['plotId'] in valid_plots and (plot_id is None or s['robot']['plotId']==plot_id) else None
    result['inventory']=inventory(s,result,valid_plots,plot_id)
    return result

def action(db,owner,wid,data,root,at=None):
    at=time.time() if at is None else at
    a.fields(data,{'commandId','action','plotId','scenario','cameraId'},{'commandId','action'})
    allowed={'demo.pause','demo.resume','scenario.set','robot.start','robot.pause','robot.return','camera.capture'}
    if not isinstance(data['action'],str) or data['action'] not in allowed:a.invalid()
    if ('scenario' in data)!=(data['action']=='scenario.set') or ('cameraId' in data)!=(data['action']=='camera.capture'):a.invalid()
    if data['action']=='scenario.set' and (not isinstance(data['scenario'],str) or data['scenario'] not in SCENARIOS):a.invalid()
    created=[]
    try:
        with a.atomic(db):
            a.workspace(db,owner,wid); a.relation(db,owner,wid,data.get('plotId'),'plot')
            def make():
                row=db.execute('SELECT * FROM agriculture_live_demo WHERE workspace_id=? AND owner=? AND enabled=1',(wid,owner)).fetchone()
                if not row:raise a.AgricultureError('demo_unavailable','演示尚未启用。',409)
                s=json.loads(row['state']); op=data['action'];r=s['robot']
                if data.get('plotId') and data['plotId'] not in s['plotIds']:a.missing()
                if op.startswith('demo.'):
                    s['paused']=op=='demo.pause'
                    if op=='demo.resume':s['lastTickAt']=at
                elif op=='scenario.set':
                    s['scenario']=data['scenario'];s['scenarioStartedAt']=at
                    event(s,at,s['scenario'],{'normal':'演示恢复正常巡检。','humidity_change':'预设湿度变化场景。','leaf_anomaly':'预设叶片外观异常，待核实。'}[s['scenario']])
                elif op=='robot.start':
                    if r['state'] in {'idle','docked'}:r['progress']=0;r['position']=r['route'][0];r['state']='patrolling'
                    elif r['state']=='paused':r['state']=r.pop('resumeState','patrolling')
                elif op=='robot.pause':
                    if r['state'] in {'patrolling','returning'}:r['resumeState']=r['state'];r['state']='paused'
                elif op=='robot.return':
                    if r['state']!='docked':r['state']='returning'
                else:
                    c=next((c for c in s['cameras'] if c['id']==data['cameraId'] and (not data.get('plotId') or c['plotId']==data['plotId'])),None)
                    if not c:a.missing()
                    source=a.read(db,owner,c['assetId'],'asset',wid);path,source=a.asset_content(db,owner,source['id'],root)
                    if len(a.entities(db,owner,wid,'asset',201))>=200:raise a.AgricultureError('too_large','园区资产已达上限。',413)
                    key=a.save_file(root,path.read_bytes());created.append(key)
                    asset=a.insert(db,owner,wid,'asset',{k:source[k] for k in ('kind','mediaType','byteSize','sha256')}|dict(name='演示抓拍',storageKey=key,status='stored',version=1,error=None,warnings=[],demoSourceAssetId=source['id']))
                    s['captures'].append(dict(id=uuid.uuid4().hex,cameraId=c['id'],plotId=c['plotId'],assetId=asset['id'],observedAt=at,origin='demo'));s['captures']=s['captures'][-12:]
                    event(s,at,'capture','已保存演示抓拍，尚未进行AI分析。')
                save(db,row,s,at)
                return {'liveDemo':view(db,owner,wid,data.get('plotId'),at)}
            return a.command(db,owner,'live-demo:'+wid,data,make)
    except BaseException:
        from pathlib import Path
        for key in created:(Path(root)/key).unlink(missing_ok=True)
        raise

def source(facts,wid):
    summary={k:copy.deepcopy(facts[k]) for k in ('origin','scenario','paused','observedAt','robot','events')}
    summary['samples']=facts['samples'][-1:];summary['events']=summary['events'][-3:]
    return dict(id='live-demo:'+wid+':'+str(facts['version']),kind='live_demo',title='演示现场事实',origin='demo',observedAt=facts['observedAt'],version=facts['version'],sourceHash=a.digest(summary),locator='live-demo:'+wid+':'+str(facts['version']),excerpt=a.encode(summary))


def inventory(state,view,valid_plots,plot_id=None):
    """Read-only projection from the same persisted sample; never request-clock values."""
    plots=[p for p in state['plotIds'] if p in valid_plots and (plot_id is None or p==plot_id)]
    if not plots:return []
    plot=plots[0]; samples=[x for x in state['samples'] if x['plotId']==plot]
    if not samples:return []
    sample=samples[-1]; sequence=state['sampleSequence']
    def metric(key,label,value,unit=''):return dict(key=key,label=label,value=value,unit=unit)
    definitions=[
      ('weather','葡萄园微气象站','环境感知',[metric('temperature','空气温度',sample['temperature'],'°C'),metric('humidity','空气湿度',sample['humidity'],'%')],'对照天气事件与巡田记录，安排重点观察。',['https://wine.wsu.edu/viticulture-enology-extension-news-spring-2023/']),
      ('leaf-wetness','叶面湿度传感器','环境感知',[metric('wetness','叶面湿润指数',round(sample['humidity']/100,2))],'观察冠层表面湿润过程，结合叶片巡查复核。',['https://metos.global/en/leaf-sensors/', 'https://extension.psu.edu/backyard-grape-growing']),
      ('soil-profile','土壤剖面传感器','环境感知',[metric('soil_moisture','表层土壤水分',sample['soil_moisture'],'%'),metric('deep_moisture','深层土壤水分',round(sample['soil_moisture']+3,1),'%')],'比较不同土层对降雨和灌水的响应。',['https://extension.umn.edu/natural-resources/conservation/agricultural-soil-and-water/irrigation/soil-moisture-sensors-for-irrigation-scheduling']),
      ('irrigation','灌溉流量与阀门','水肥灌溉',[metric('valve','阀门状态','关闭'),metric('flow','流量',0,'L/min')],'核查分区供水与漏堵线索，复查实际出水。',['https://www.netafim.co/bynder/28dea0b8-8ef1-4037-9ea133d578881e27-drip-irrigation-system-handbook.pdf']),
      ('fertigation','水肥监测单元','水肥灌溉',[metric('ec','模拟电导率',round(1.2+(sequence%5)*.01,2),'mS/cm'),metric('pump','泵状态','待命')],'观察水肥供液性质，记录探头维护与校准。',['https://www.netafim.co/bynder/28dea0b8-8ef1-4037-9ea133d578881e27-drip-irrigation-system-handbook.pdf']),
      ('insect-camera','虫情观察相机','视觉监测',[metric('captures','演示图像序号',sequence),metric('review','观察结果','待人工核查')],'追踪指定诱捕对象，图像与捕获数由人工复核。',['https://metos.global/en/iscout/', 'https://ipm.ucanr.edu/agriculture/grape/']),
      ('frost-fan','防霜风机','田间作业',[metric('rotation','转速',0,'rpm'),metric('state','作业状态','待命')],'结合不同高度气温、逆温与地形核查防霜条件。',['https://www.ontario.ca/page/wind-machines-minimizing-cold-injury-horticultural-crops']),
      ('multispectral-drone','多光谱巡查无人机','视觉监测',[metric('state','作业状态','待命'),metric('battery','模拟电量',95,'%')],'寻找冠层空间差异，安排地面复查。',['https://www.dji.com/newsroom/news/dji-launches-the-mavic-3-multispectral']),
    ]
    return [dict(id='demo-'+kind,name=name,kind=kind,category=category,plotId=plot,origin='demo',status=view['status'],observedAt=sample['observedAt'],metrics=metrics,summary=summary,sources=sources) for kind,name,category,metrics,summary,sources in definitions]
