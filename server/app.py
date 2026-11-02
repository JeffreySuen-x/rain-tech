import argparse
import contextlib
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import sys
import time
from pathlib import Path
from flask import Flask, request, jsonify, g, send_from_directory
from .skill import SYSTEM_PROMPT, SKILL_ID, CATALOG, public_catalog
from . import agent_runtime, agriculture
from werkzeug.security import generate_password_hash as _password_hash, check_password_hash

def generate_password_hash(password): return _password_hash(password, method="pbkdf2:sha256:1000000")


def uid(): return secrets.token_hex(16)
def now(): return time.time()
def encode(x): return json.dumps(x, ensure_ascii=False, sort_keys=True)

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),csrf TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS threads(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),workspace_id TEXT NOT NULL REFERENCES workspaces(id),title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),workspace_id TEXT NOT NULL REFERENCES workspaces(id),content TEXT NOT NULL,source_turn_id TEXT,created_at REAL NOT NULL,deleted INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS turns(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),thread_id TEXT NOT NULL REFERENCES threads(id),workspace_id TEXT NOT NULL REFERENCES workspaces(id),status TEXT NOT NULL,payload TEXT NOT NULL,created_at REAL NOT NULL,error TEXT,artifact_id TEXT,generation INTEGER DEFAULT 0,lease_until REAL,dispatched INTEGER DEFAULT 0,result TEXT);
CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),thread_id TEXT NOT NULL REFERENCES threads(id),turn_id TEXT NOT NULL REFERENCES turns(id),title TEXT NOT NULL,body TEXT NOT NULL,sources TEXT NOT NULL,created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS commands(owner TEXT,scope TEXT,key TEXT,digest TEXT,response TEXT,PRIMARY KEY(owner,scope,key));
'''

class APIError(Exception):
    def __init__(self,code,message,status=400): self.code,self.message,self.status=code,message,status


def connect(path):
    fresh=not Path(path).exists()
    db=sqlite3.connect(path,timeout=15,isolation_level=None)
    if fresh:os.chmod(path,0o600)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL'); db.execute('PRAGMA foreign_keys=ON')
    return db

@contextlib.contextmanager
def transaction(db):
    db.execute('BEGIN IMMEDIATE')
    try: yield db; db.execute('COMMIT')
    except BaseException: db.execute('ROLLBACK'); raise


def create_app(config=None):
    app=Flask(__name__)
    mode=os.environ.get('SHUYU_ENV','production')
    app.config.update(DB_PATH=os.environ.get('SHUYU_DB','./.runtime/shuyu.sqlite3'),PRODUCTION=mode!='development',PUBLIC_ORIGIN=os.environ.get('SHUYU_PUBLIC_ORIGIN','http://127.0.0.1:5180' if mode=='development' else ''),SECRET_KEY=os.environ.get('SHUYU_SECRET',''),MAX_CONTENT_LENGTH=20*1024*1024+65536,ASSET_ROOT=os.environ.get('SHUYU_ASSET_ROOT','./.runtime/assets'),PROVIDER_CAPABILITIES=os.environ.get('SHUYU_PROVIDER_CAPABILITIES','text'),PROVIDER_THINKING=os.environ.get('SHUYU_PROVIDER_THINKING',''),PROVIDER_ASR_ADAPTER=os.environ.get('SHUYU_PROVIDER_ASR_ADAPTER','transcriptions'),PROVIDER_VISION_MODEL=os.environ.get('SHUYU_PROVIDER_VISION_MODEL',''),PROVIDER_ASR_MODEL=os.environ.get('SHUYU_PROVIDER_ASR_MODEL',''),PROVIDER_URL=os.environ.get('SHUYU_PROVIDER_URL',''),PROVIDER_KEY=os.environ.get('SHUYU_PROVIDER_KEY',''),PROVIDER_MODEL=os.environ.get('SHUYU_PROVIDER_MODEL',''))
    if config: app.config.update(config)
    app.config.setdefault('STATIC_DIR', os.environ.get('SHUYU_STATIC_DIR',''))
    if app.config['PRODUCTION'] and (len(app.config['SECRET_KEY'])<32 or not app.config['PUBLIC_ORIGIN'].startswith('https://')):
        raise ValueError('Production requires SHUYU_SECRET (32+ characters) and HTTPS SHUYU_PUBLIC_ORIGIN')
    Path(app.config['DB_PATH']).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with contextlib.closing(connect(app.config['DB_PATH'])) as db:
        db.executescript(SCHEMA); agriculture.migrate(db); agent_runtime.migrate(db)
    @app.before_request
    def before():
        g.db=connect(app.config['DB_PATH']); g.user=None; g.session=None
        sid=request.cookies.get('shuyu_session','')
        s=g.db.execute('SELECT * FROM sessions WHERE id=? AND expires>?',(hashlib.sha256(sid.encode()).hexdigest(),now())).fetchone()
        if s:
            g.session=s
            if s['user_id']: g.user=g.db.execute('SELECT id,username FROM users WHERE id=?',(s['user_id'],)).fetchone()
        device_event=request.method=='POST' and request.path.startswith('/api/v1/devices/') and request.path.endswith('/events') and request.headers.get('Authorization','').startswith('Bearer ')
        if request.method in ('POST','DELETE','PUT','PATCH'):
            origin=request.headers.get('Origin')
            if origin and origin!=app.config['PUBLIC_ORIGIN']: raise APIError('origin_rejected','请求来源不受信任',403)
            token=request.headers.get('X-CSRF-Token','')
            if not device_event and (not s or not token.isascii() or not hmac.compare_digest(s['csrf'],token)): raise APIError('csrf_rejected','请刷新页面后重试',403)
        if request.path.startswith('/api/v1/') and request.path not in ('/api/v1/auth/login','/api/v1/auth/csrf','/api/v1/health') and not g.user and not device_event:
            raise APIError('unauthorized','请先登录',401)
    @app.after_request
    def response_headers(response):
        if request.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
            response.headers['X-Content-Type-Options']='nosniff'
        return response
    @app.teardown_request
    def close(error):
        if hasattr(g,'db'): g.db.close()
    @app.errorhandler(APIError)
    def err(e): return jsonify(error={'code':e.code,'message':e.message}),e.status
    @app.errorhandler(413)
    def large(e): return jsonify(error={'code':'too_large','message':'请求内容过长'}),413
    @app.errorhandler(400)
    def malformed(e): return jsonify(error={'code':'invalid_json','message':'请求格式错误'}),400
    def body():
        if request.content_length is not None and request.content_length>128*1024:raise APIError('too_large','JSON请求超过128KB',413)
        value=request.get_json(silent=False)
        if not isinstance(value,dict): raise APIError('invalid_request','需要 JSON 对象')
        return value
    def string(b,key,maximum=16000):
        v=b.get(key)
        if not isinstance(v,str) or not v.strip() or len(v)>maximum: raise APIError('invalid_request',key+' 无效')
        return v.strip()
    def owned(table,id):
        r=g.db.execute(f'SELECT * FROM {table} WHERE id=? AND owner=?',(id,g.user['id'])).fetchone()
        if not r: raise APIError('not_found','资料不存在',404)
        return r
    def session_response(payload,user=None,status=200):
        raw=secrets.token_urlsafe(32); token=secrets.token_urlsafe(32)
        with transaction(g.db):
            if g.session: g.db.execute('DELETE FROM sessions WHERE id=?',(g.session['id'],))
            g.db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(raw.encode()).hexdigest(),user,token,now()+86400*7))
        payload['csrfToken']=token
        response=jsonify(payload); response.status_code=status
        response.set_cookie('shuyu_session',raw,httponly=True,secure=app.config['PRODUCTION'],samesite='Lax',max_age=86400*7)
        return response
    def idem(scope,b,make):
        key=string(b,'commandId',200); digest=hashlib.sha256(encode(b).encode()).hexdigest()
        old=g.db.execute('SELECT * FROM commands WHERE owner=? AND scope=? AND key=?',(g.user['id'],scope,key)).fetchone()
        if old:
            if old['digest']!=digest: raise APIError('command_conflict','同一命令编号的内容已改变',409)
            return json.loads(old['response'])
        result=make()
        g.db.execute('INSERT INTO commands VALUES(?,?,?,?,?)',(g.user['id'],scope,key,digest,encode(result)))
        return result
    @app.get('/api/v1/health')
    def health(): return jsonify(status='ok')
    @app.get('/api/v1/auth/csrf')
    def csrf():
        if g.session: return jsonify(csrfToken=g.session['csrf'])
        return session_response({})
    @app.post('/api/v1/auth/login')
    def login():
        b=body(); u=g.db.execute('SELECT * FROM users WHERE username=?',(string(b,'username',100),)).fetchone()
        password=b.get('password')
        if not isinstance(password,str) or not password or len(password)>1024: raise APIError('invalid_request','password 无效')
        if not u or not check_password_hash(u['password'],password): raise APIError('invalid_credentials','账号或密码错误',401)
        return session_response({'user':{'id':u['id'],'username':u['username']}},u['id'])
    @app.get('/api/v1/auth/me')
    def me(): return jsonify(user=dict(g.user),csrfToken=g.session['csrf'])
    @app.post('/api/v1/auth/logout')
    def logout():
        g.db.execute('DELETE FROM sessions WHERE id=?',(g.session['id'],)); r=app.make_response(('',204)); r.delete_cookie('shuyu_session'); return r
    @app.route('/api/v1/workspaces',methods=['GET','POST'])
    def workspaces():
        if request.method=='GET': return jsonify(workspaces=[dict(r) for r in g.db.execute('SELECT id,name FROM workspaces WHERE owner=?',(g.user['id'],))])
        b=body()
        def make():
            w={'id':uid(),'name':string(b,'name',200)}
            g.db.execute('INSERT INTO workspaces VALUES(?,?,?)',(w['id'],g.user['id'],w['name']));return {'workspace':w}
        with transaction(g.db):result=idem('workspace',b,make) if 'commandId' in b else make()
        return jsonify(result),201
    @app.route('/api/v1/workspaces/<wid>/threads',methods=['GET','POST'])
    def threads(wid):
        owned('workspaces',wid)
        if request.method=='GET': return jsonify(threads=[{'id':r['id'],'workspaceId':wid,'title':r['title']} for r in g.db.execute('SELECT * FROM threads WHERE workspace_id=? AND owner=?',(wid,g.user['id']))])
        b=body()
        def make():
            t={'id':uid(),'workspaceId':wid,'title':string(b,'title',200)}
            g.db.execute('INSERT INTO threads VALUES(?,?,?,?)',(t['id'],g.user['id'],wid,t['title']));return {'thread':t}
        with transaction(g.db):result=idem('thread:'+wid,b,make) if 'commandId' in b else make()
        return jsonify(result),201
    @app.get('/api/v1/threads/<tid>')
    def thread(tid):
        t=owned('threads',tid); turns=g.db.execute('SELECT * FROM turns WHERE thread_id=? AND owner=? ORDER BY created_at',(tid,g.user['id'])).fetchall(); messages=[]
        for v in turns:
            payload=json.loads(v['payload']);asset_ids=[]
            for reference in payload.get('agricultureContext',{}).get('assets',[]):
                try:
                    asset=agriculture.read(g.db,g.user['id'],reference.get('id'),'asset',t['workspace_id'])
                    if asset.get('kind')!='image' or asset.get('version')!=reference.get('version') or asset.get('sha256')!=reference.get('sourceHash'):continue
                    agriculture.asset_content(g.db,g.user['id'],asset['id'],Path(app.config['ASSET_ROOT']))
                except (agriculture.AgricultureError,OSError):continue
                if asset['id'] not in asset_ids:asset_ids.append(asset['id'])
            messages.append({'id':v['id']+'-user','role':'user','content':payload['prompt'],'createdAt':v['created_at'],'assetIds':asset_ids})
            if v['artifact_id']:
                a=owned('artifacts',v['artifact_id']); messages.append({'id':a['id'],'role':'assistant','content':a['body'],'createdAt':a['created_at']})
        return jsonify(thread={'id':tid,'workspaceId':t['workspace_id'],'title':t['title']},messages=messages,turns=[turn_json(v) for v in turns])
    @app.get('/api/v1/skills')
    def skills(): return jsonify(skills=public_catalog())
    @app.post('/api/v1/threads/<tid>/turns')
    def submit(tid):
        b=body()
        if set(b)-{'commandId','prompt','background','memoryIds','agricultureContext','includeHistory','skillId'}:raise APIError('invalid_request','请求字段无效')
        with transaction(g.db): result=enqueue_turn(g.db,g.user['id'],tid,b,b.get('commandId'),'turn:'+tid)
        return jsonify(result),202
    @app.get('/api/v1/turns/<id>')
    def turn(id):
        t=owned('turns',id); result={'turn':turn_json(t)}
        result['turn']['toolEvents']=[{'callId':r['call_id'],'status':r['state'],'kind':r['kind'],'name':json.loads(r['result']).get('_toolName') if r['kind']=='tool' and r['result'] else None} for r in g.db.execute('SELECT * FROM agent_receipts WHERE turn_id=? ORDER BY rowid',(id,))]
        if t['artifact_id']: result['artifact']=artifact_json(owned('artifacts',t['artifact_id']))
        return jsonify(result)
    @app.post('/api/v1/turns/<id>/cancel')
    def cancel(id):
        b=body()
        with transaction(g.db):
            owned('turns',id)
            def make():
                g.db.execute("UPDATE turns SET status='cancelled',generation=generation+1,lease_until=NULL WHERE id=? AND status IN ('queued','running')",(id,))
                return {'turn':turn_json(owned('turns',id))}
            result=idem('cancel:'+id,b,make)
        return jsonify(result)
    @app.get('/api/v1/artifacts/<id>')
    def artifact(id): return jsonify(artifact=artifact_json(owned('artifacts',id)))
    @app.route('/api/v1/workspaces/<wid>/memories',methods=['GET','POST'])
    def memories(wid):
        owned('workspaces',wid)
        if request.method=='GET': return jsonify(memories=[memory_json(r) for r in g.db.execute('SELECT * FROM memories WHERE owner=? AND workspace_id=? AND deleted=0',(g.user['id'],wid))])
        b=body()
        with transaction(g.db):
            def make():
                content=string(b,'content'); source=b.get('sourceTurnId')
                if source is not None and not isinstance(source,str): raise APIError('invalid_source','来源任务无效')
                if source:
                    t=owned('turns',source)
                    if t['workspace_id']!=wid or t['status']!='completed': raise APIError('invalid_source','来源任务不可用')
                id=uid(); g.db.execute('INSERT INTO memories VALUES(?,?,?,?,?,?,0)',(id,g.user['id'],wid,content,source,now()))
                return {'memory':memory_json(owned('memories',id))}
            result=idem('memory:'+wid,b,make)
            current=owned('memories',result['memory']['id'])
            if current['deleted']: raise APIError('memory_revoked','该记忆已删除',409)
        return jsonify(result),201
    @app.delete('/api/v1/memories/<id>')
    def delete_memory(id):
        with transaction(g.db):
            owned('memories',id); g.db.execute("UPDATE memories SET deleted=1,content='' WHERE id=?",(id,))
        return '',204
    def request_media(db,owner,asset,operation,b):
        kind='image_analysis' if operation in ('analyze','image_analysis') else 'audio_transcription'
        raw={**b,'prompt':b.get('prompt') or ('请分析照片并说明证据与不确定性' if kind=='image_analysis' else '请转写录音为可编辑文字草稿'),'processingKind':kind,'mediaAssetId':asset['id'],'agricultureContext':{'assetIds':[asset['id']]}}
        with agriculture.atomic(db):return enqueue_turn(db,owner,b.get('threadId'),raw,b.get('commandId'),'media:'+asset['id']+':'+operation)
    def cancel_turn(db,owner,turn_id):
        db.execute("UPDATE turns SET status='cancelled',generation=generation+1,lease_until=NULL WHERE id=? AND owner=? AND status IN ('queued','running')",(turn_id,owner))
    agriculture.register_routes(app,{'APIError':APIError,'transaction':transaction,'uid':uid,'now':now,'encode':encode,'owned':owned,'idem':idem,'body':body,'string':string,'enqueue_turn':enqueue_turn,'request_media':request_media,'asset_root':Path(app.config['ASSET_ROOT']),'cancel_turn':cancel_turn})
    static_dir=app.config.get('STATIC_DIR') or ''
    if static_dir:
        static_root=Path(static_dir).resolve()
        if not static_root.is_dir(): raise ValueError('static directory missing')
        @app.get('/')
        def _desktop_index(): return send_from_directory(static_root,'index.html')
        @app.get('/<path:path>')
        def _desktop_asset(path):
            if path.startswith('api/'): return jsonify(error={'code':'not_found','message':'接口不存在'}),404
            try: target=(static_root/path).resolve(); target.relative_to(static_root)
            except (OSError,ValueError): return jsonify(error={'code':'not_found','message':'资源不存在'}),404
            if target.is_file(): return send_from_directory(static_root,path)
            return send_from_directory(static_root,'index.html')
    return app



def enqueue_turn(db,owner,thread_id,b,command_id,scope):
    if not isinstance(command_id,str) or not command_id.strip() or len(command_id)>200: raise APIError('invalid_request','commandId 无效')
    t=db.execute('SELECT * FROM threads WHERE id=? AND owner=?',(thread_id,owner)).fetchone()
    if not t: raise APIError('not_found','对话不存在',404)
    digest=hashlib.sha256(encode(b).encode()).hexdigest()
    old=db.execute('SELECT * FROM commands WHERE owner=? AND scope=? AND key=?',(owner,scope,command_id)).fetchone()
    if old:
        if old['digest']!=digest:raise APIError('command_conflict','同一命令编号的内容已改变',409)
        return json.loads(old['response'])
    if db.execute("SELECT id FROM turns WHERE thread_id=? AND owner=? AND status IN ('queued','running')",(thread_id,owner)).fetchone():raise APIError('thread_busy','该对话已有执行中的任务',409)
    selected_id=({'image_analysis':'shuyu.image.v1','audio_transcription':'shuyu.audio.v1'}.get(b.get('processingKind'),SKILL_ID) if scope.startswith('media:') else (SKILL_ID if scope=='agriculture-followup' else b.get('skillId',SKILL_ID)))
    skill=CATALOG.get(selected_id) if isinstance(selected_id,str) else None
    if not skill or (not scope.startswith('media:') and skill['kind']!='chat'):raise APIError('invalid_request','技能无效')
    prompt=b.get('prompt');background=b.get('background','');ids=b.get('memoryIds',[])
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>16000 or not isinstance(background,str) or len(background)>32000 or not isinstance(ids,list) or len(ids)>30 or any(not isinstance(i,str) for i in ids):raise APIError('invalid_request','问题、背景或记忆无效')
    memories=[]
    for mid in dict.fromkeys(ids):
        m=db.execute('SELECT * FROM memories WHERE id=? AND owner=? AND workspace_id=? AND deleted=0',(mid,owner,t['workspace_id'])).fetchone()
        if not m:raise APIError('not_found','记忆不可用',404)
        memories.append({'id':mid,'kind':'memory','title':'明确选择的记忆','content':m['content']})
    include_history=b.get('includeHistory',False)
    if not isinstance(include_history,bool):raise APIError('invalid_request','includeHistory必须是布尔值')
    include_history=include_history and not (scope.startswith('media:') or scope=='agriculture-followup')
    history=[];dependencies=[];agri_dependencies=[]
    for prev in db.execute("SELECT * FROM turns WHERE owner=? AND thread_id=? AND status='completed' ORDER BY created_at DESC LIMIT 6",(owner,thread_id)) if include_history else []:
        pp=json.loads(prev['payload']);deps=pp.get('memories',[])+pp.get('historyMemoryIds',[])
        if any(not db.execute('SELECT id FROM memories WHERE id=? AND owner=? AND deleted=0',(m['id'],owner)).fetchone() for m in deps):continue
        try:
            for frozen in ([pp['agricultureContext']] if pp.get('agricultureContext') else [])+pp.get('historyAgricultureContexts',[]):agriculture.validate_context(db,owner,t['workspace_id'],frozen)
        except (agriculture.AgricultureError,OSError):continue
        for frozen in ([pp['agricultureContext']] if pp.get('agricultureContext') else [])+pp.get('historyAgricultureContexts',[]):
            if frozen not in agri_dependencies:agri_dependencies.append(frozen)
        answer=prev['result'] or ''
        history.append({'id':prev['id'],'kind':'history','title':'此前已完成对话','prompt':pp['prompt'],'answer':answer[:6000],'answerFullLength':len(answer),'answerIncludedLength':min(6000,len(answer)),'excerptOnly':len(answer)>6000})
        for m in deps:
            if m['id'] not in [x['id'] for x in dependencies]:dependencies.append({'id':m['id']})
    selection=b.get('agricultureContext',{})
    # Internal followups carry an already frozen, validated source snapshot.
    snapshot=selection if scope=='agriculture-followup' else agriculture.snapshot_context(db,owner,t['workspace_id'],selection)
    if scope.startswith('media:'):
        snapshot.pop('liveDemo',None)
        snapshot['sources']=[s for s in snapshot.get('sources',[]) if s.get('kind')!='live_demo']
    agriculture.validate_context(db,owner,t['workspace_id'],snapshot)
    payload={'includeHistory':include_history,'skillId':selected_id,'skillVersion':skill['version'],'skillPolicy':{k:skill[k] for k in ('instruction','allowedToolNames')},'prompt':prompt.strip(),'background':background,'memories':memories,'history':list(reversed(history)),'historyMemoryIds':dependencies,'historyAgricultureContexts':agri_dependencies,'agricultureContext':snapshot,'processingKind':b.get('processingKind','chat') if scope.startswith('media:') else 'chat'}
    for key in ('mediaAssetId','budget','followUp'):
        if key in b and (scope=='agriculture-followup' or scope.startswith('media:')):payload[key]=b[key]
    agent_runtime.budget_for(payload)
    if len(encode(payload).encode())>96000:raise APIError('too_large','问题与资料超过96KB',413)
    id=uid();db.execute('INSERT INTO turns(id,owner,thread_id,workspace_id,status,payload,created_at) VALUES(?,?,?,?,?,?,?)',(id,owner,thread_id,t['workspace_id'],'queued',encode(payload),now()))
    result={'turn':{'id':id,'status':'queued','processingKind':payload['processingKind']}}
    db.execute('INSERT INTO commands VALUES(?,?,?,?,?)',(owner,scope,command_id,digest,encode(result)))
    return result


def turn_json(r):
    payload=json.loads(r['payload']); extra={'skillId':payload.get('skillId',SKILL_ID),'processingKind':payload.get('processingKind','chat'),'sources':payload.get('agricultureContext',{}).get('sources',[])}
    return {**extra,'id':r['id'],'threadId':r['thread_id'],'status':r['status'],'error':json.loads(r['error']) if r['error'] else None,'artifactId':r['artifact_id'],'createdAt':r['created_at']}
def artifact_json(r): return {'id':r['id'],'threadId':r['thread_id'],'turnId':r['turn_id'],'title':r['title'],'body':r['body'],'sources':json.loads(r['sources']),'createdAt':r['created_at']}
def memory_json(r): return {'id':r['id'],'content':r['content'],'sourceTurnId':r['source_turn_id'],'createdAt':r['created_at']}


def claim(db,lease=120):
    with transaction(db):
        db.execute("UPDATE turns SET status='queued',generation=generation+1,dispatched=0 WHERE status='running' AND lease_until<? AND result IS NULL AND EXISTS (SELECT 1 FROM agent_receipts ar WHERE ar.turn_id=turns.id) AND NOT EXISTS (SELECT 1 FROM agent_receipts ar WHERE ar.turn_id=turns.id AND ar.state!='sealed')",(now(),))
        db.execute("UPDATE turns SET status='needs_review',error=?,generation=generation+1 WHERE status='running' AND lease_until<? AND dispatched=1 AND result IS NULL",(encode({'code':'provider_uncertain','message':'模型请求结果未知，请人工核查；不会自动重发'}),now()))
        db.execute("UPDATE turns SET status='queued',generation=generation+1 WHERE status='running' AND lease_until<? AND dispatched=0",(now(),))
        r=db.execute("SELECT * FROM turns WHERE status='queued' OR (status='running' AND result IS NOT NULL AND lease_until<?) ORDER BY created_at LIMIT 1",(now(),)).fetchone()
        if not r: return None
        db.execute("UPDATE turns SET status='running',generation=generation+1,lease_until=? WHERE id=?",(now()+lease,r['id']))
        return db.execute('SELECT * FROM turns WHERE id=?',(r['id'],)).fetchone()


def fence(db,t):
    return db.execute("SELECT * FROM turns WHERE id=? AND status='running' AND generation=? AND lease_until>?",(t['id'],t['generation'],now())).fetchone()


def provider(config,payload):
    # Compatibility API; all provider transport lives in one bounded adapter.
    from .agent_provider import complete
    return complete(config,{'messages':[{'role':'user','content':encode(agent_runtime.model_input_view(payload))}]})['body']


def run_once(app,call=None,after_dispatch=None,after_seal=None):
    with contextlib.closing(connect(app.config['DB_PATH'])) as db:
        from . import agriculture_live_demo
        agriculture_live_demo.advance(db,now())
        agriculture.due_followups(db,now(),enqueue_turn)
        t=claim(db)
        if t is None: return False
        payload=json.loads(t['payload'])
        if t['result'] is None:
            with transaction(db):
                if not fence(db,t): return True
                if any(not db.execute('SELECT id FROM memories WHERE id=? AND owner=? AND workspace_id=? AND deleted=0',(m['id'],t['owner'],t['workspace_id'])).fetchone() for m in payload['memories']+payload.get('historyMemoryIds',[])):
                    db.execute("UPDATE turns SET status='failed',error=? WHERE id=?",(encode({'code':'memory_revoked','message':'使用的记忆已删除，请重新提交'}),t['id'])); return True
                if call:db.execute('UPDATE turns SET dispatched=1 WHERE id=?',(t['id'],))
            if after_dispatch: after_dispatch()
            try:
                if call: result=call(payload)
                else: result=agent_runtime.run(app,db,t,payload,{'connect':connect,'transaction':transaction,'fence':fence,'now':now,'encode':encode})
            except Exception as error:
                code=getattr(error,'code','provider_uncertain'); message=getattr(error,'message','模型请求未确认完成；不会自动重发，请核查提供商记录')
                status='needs_review' if code=='provider_uncertain' else 'failed'
                with transaction(db):
                    if fence(db,t): db.execute("UPDATE turns SET status=?,error=? WHERE id=?",(status,encode({'code':code,'message':message}),t['id']))
                return True
            with transaction(db):
                if not fence(db,t): return True
                db.execute('UPDATE turns SET result=? WHERE id=?',(result,t['id']))
            if after_seal: after_seal()
        with transaction(db):
            current=fence(db,t)
            if not current: return True
            for m in payload['memories']+payload.get('historyMemoryIds',[]):
                valid=db.execute('SELECT id FROM memories WHERE id=? AND owner=? AND workspace_id=? AND deleted=0',(m['id'],t['owner'],t['workspace_id'])).fetchone()
                if not valid:
                    db.execute("UPDATE turns SET status='failed',result=NULL,error=? WHERE id=?",(encode({'code':'memory_revoked','message':'使用的记忆已删除，本次成果不再发布'}),t['id'])); return True
            try:
                for frozen in ([payload['agricultureContext']] if payload.get('agricultureContext') else [])+payload.get('historyAgricultureContexts',[]):agriculture.validate_context(db,t['owner'],t['workspace_id'],frozen)
            except agriculture.AgricultureError as error:
                db.execute("UPDATE turns SET status='failed',result=NULL,error=? WHERE id=?",(encode({'code':error.code,'message':error.message}),t['id']));return True
            agriculture.seal_media(db,t,current['result'])
            aid=uid(); sources=[{'id':t['id']+'-prompt','kind':'prompt','title':'原始问题','content':payload['prompt']}]
            if payload['background']: sources.append({'id':t['id']+'-background','kind':'background','title':'独立背景','content':payload['background']})
            sources+=payload['memories']+payload.get('history',[])+payload.get('agricultureContext',{}).get('sources',[])
            for receipt in db.execute("SELECT result FROM agent_receipts WHERE turn_id=? AND kind='tool' AND state='sealed'",(t['id'],)):
                tool_result=json.loads(receipt['result'])
                for source in tool_result.get('sources',[]) if isinstance(tool_result,dict) else []:
                    if source not in sources:sources.append(source)
            db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?)',(aid,t['owner'],t['thread_id'],t['id'],payload['prompt'][:80],current['result'],encode(sources),now()))
            db.execute("UPDATE turns SET status='completed',artifact_id=?,lease_until=NULL WHERE id=?",(aid,t['id']))
        return True


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--config'); sub=parser.add_subparsers(dest='command',required=True)
    user=sub.add_parser('create-user'); user.add_argument('username'); user.add_argument('--password-stdin',action='store_true')
    recovery=sub.add_parser('recover-owner-access'); recovery.add_argument('--workspace',required=True); recovery.add_argument('--expected-user-id',required=True); recovery.add_argument('--password-stdin',action='store_true')
    serve=sub.add_parser('serve'); serve.add_argument('--port',type=int,default=6480)
    worker=sub.add_parser('worker'); worker.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if args.config:
        from .local_config import load_config
        try: load_config(args.config)
        except ValueError as error: parser.error(str(error))
    if args.command=='recover-owner-access':
        from .account_recovery import recover_owner_access
        password=sys.stdin.readline().rstrip('\n') if args.password_stdin else getpass.getpass('New password: ')
        try: recover_owner_access(os.environ.get('SHUYU_DB','./.runtime/shuyu.sqlite3'),args.workspace,args.expected_user_id,password)
        except (ValueError,sqlite3.Error): parser.error('Owner access recovery failed; verify target and local database')
        print('Owner access recovered; existing sessions revoked')
        return
    app=create_app()
    if args.command=='create-user':
        password=sys.stdin.readline().rstrip('\n') if args.password_stdin else getpass.getpass('Password: ')
        if not args.username.strip() or len(args.username.strip())>100: parser.error('Username must contain 1–100 characters')
        if len(password)<12 or len(password)>1024: parser.error('Password must contain 12–1024 characters')
        with contextlib.closing(connect(app.config['DB_PATH'])) as db: db.execute('INSERT INTO users VALUES(?,?,?)',(uid(),args.username.strip(),generate_password_hash(password)))
        print('User created')
    elif args.command=='serve': app.run(host='127.0.0.1',port=args.port,debug=False)
    else:
        while True:
            worked=run_once(app)
            if args.once: break
            if not worked: time.sleep(1)

if __name__=='__main__': main()
