"""Private DSH process and durable callbacks; turns remain the sole queue."""
import contextlib
import hashlib
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from .agent_provider import complete, configured

DEFAULT_BUDGET={'maxModelCalls':6,'maxToolCalls':16,'deadlineSeconds':180,'maxInputBytes':24*1024*1024,'maxOutputBytes':256000}

def migrate(db):
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS agent_schema_meta(version INTEGER NOT NULL)')
        version=db.execute('SELECT version FROM agent_schema_meta').fetchone()
        if version and version[0] not in (1,2): raise ValueError('unknown agent schema version')
        db.execute('CREATE TABLE IF NOT EXISTS agent_receipts(turn_id TEXT NOT NULL REFERENCES turns(id),generation INTEGER NOT NULL,call_id TEXT NOT NULL,kind TEXT NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL,result TEXT,PRIMARY KEY(turn_id,call_id))')
        db.execute('CREATE TABLE IF NOT EXISTS agent_runs(turn_id TEXT PRIMARY KEY REFERENCES turns(id),started_at REAL NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS media_derivations(turn_id TEXT PRIMARY KEY REFERENCES turns(id),provenance TEXT NOT NULL)')
        if not version: db.execute('INSERT INTO agent_schema_meta VALUES(2)')
        elif version[0]==1: db.execute('UPDATE agent_schema_meta SET version=2')
        db.execute('COMMIT')
    except BaseException: db.execute('ROLLBACK');raise

class AgentError(Exception):
    def __init__(self,code,message,uncertain=False): self.code,self.message,self.uncertain=code,message,uncertain

def budget_for(payload):
    budget={**DEFAULT_BUDGET,**payload.get('budget',{})}
    for k,v in budget.items():
        if k not in DEFAULT_BUDGET or not isinstance(v,(int,float)) or isinstance(v,bool) or not 0<v<=({'maxModelCalls':8}.get(k,DEFAULT_BUDGET[k])): raise AgentError('invalid_request','执行预算无效')
    return budget

CHILD_ENV_KEYS={'PATH','LANG','LC_ALL','LC_CTYPE','TMPDIR','TMP','TEMP','SystemRoot'}

def child_environment():
    return {k:v for k,v in os.environ.items() if k in CHILD_ENV_KEYS}

# Explicit field projection applies recursively to tool data. Internal snapshots
# and receipts retain full provenance; only this public evidence enters DSH.
MODEL_FIELDS=set("liveDemo mode origin paused scenario serverTime samples soil_moisture cameras captures events robot position x y route battery progress cameraId enabled label asset temperature humidity min max id kind title name crop stage plotId deviceId workItemId status description dueAt completedAt note metric value unit observedAt receivedAt source latest readings thresholds staleAfterSeconds lastSeenAt state severity message text draft operation analysis transcription version sourceHash assetId locator excerpt sources sourcePolicy devices alerts workItems records generationType persisted proposal data gardenName prompt answer content question background memories history processingKind byteSize mediaType warnings error code _toolName".split())

def model_tool_view(value):
    if isinstance(value,dict):return {k:model_tool_view(v) for k,v in value.items() if k in MODEL_FIELDS and k != 'inventory'}
    if isinstance(value,list):return [model_tool_view(v) for v in value]
    return value

def model_input_view(payload):
    context=payload.get('agricultureContext',{})
    sources=[model_tool_view(x) for x in context.get('sources',[])]
    is_media=payload.get('processingKind') in {'image_analysis','audio_transcription'}
    if is_media:
        sources=[s for s in sources if s.get('kind')!='live_demo']
        sources=[{k:v for k,v in source.items() if k in {'id','kind','assetId','sourceHash','version','origin'}} for source in sources]
    return {'prompt':payload.get('prompt',''),'background':payload.get('background',''),
            'memories':[{'content':m.get('content','')} for m in payload.get('memories',[])],
            'history':[{'question':h.get('prompt',''),'answer':h.get('answer','')} for h in payload.get('history',[])] if payload.get('includeHistory') is True else [],
            'processingKind':payload.get('processingKind','chat'),
            'agricultureContext':({'sources':sources} if is_media else {'gardenName':context.get('gardenName',''),'plotId':context.get('plotId'),'sources':sources,**({'liveDemo':model_tool_view(context['liveDemo'])} if context.get('liveDemo') else {})})}

def run(app,db,t,payload,api):
    from . import agriculture
    budget=budget_for(payload)
    with api['transaction'](db):
        if not api['fence'](db,t):raise AgentError('cancelled','任务已停止')
        db.execute('INSERT OR IGNORE INTO agent_runs VALUES(?,?)',(t['id'],api['now']()))
        epoch=db.execute('SELECT started_at FROM agent_runs WHERE turn_id=?',(t['id'],)).fetchone()[0]
    remaining=budget['deadlineSeconds']-max(0,api['now']()-epoch)
    if remaining<=0:raise AgentError('budget_exceeded','执行时间超出预算')
    started=time.monotonic(); stopped=threading.Event(); cancelled=threading.Event()
    media=None
    if payload.get('mediaAssetId'):
        path,asset=agriculture.asset_content(db,t['owner'],payload['mediaAssetId'],Path(app.config['ASSET_ROOT']))
        media={'kind':payload['processingKind'],'bytes':path.read_bytes(),'mime':asset['mediaType']}
        if media['kind']=='image_analysis':
            from .agriculture_materials import outbound_image
            image,mime,provenance=outbound_image(media['bytes'])
            media.update(bytes=image,mime=mime)
            # Deterministic derivation is recorded separately from model input.
            with api['transaction'](db):
                if not api['fence'](db,t):raise AgentError('cancelled','任务已停止')
                db.execute('INSERT OR IGNORE INTO media_derivations VALUES(?,?)',(t['id'],api['encode'](provenance)))
        if media['kind']=='audio_transcription' and app.config.get('PROVIDER_ASR_ADAPTER','transcriptions')=='input_audio' and media['mime'] not in ('audio/wav','audio/mpeg'):raise AgentError('unsupported_media','此音频adapter只支持WAV/MP3')
    from .skill import frozen_policy
    try: policy=frozen_policy(payload)
    except ValueError: raise AgentError('invalid_skill_policy','技能策略无效')
    frame={'trustedSkillPolicy':policy,'turnId':t['id'],'generation':t['generation'],'inputSnapshot':model_input_view(payload),'toolSchemas':[] if media else [d for d in agriculture.tool_definitions() if d['function']['name'] in policy['allowedToolNames']],'budget':budget}
    if len(api['encode'](frame).encode())>budget['maxInputBytes']:raise AgentError('budget_exceeded','输入超出预算')
    launcher=Path(__file__).resolve().parents[1]/'runtime/dsh/src/worker.mjs'
    process=None;maintenance=None;reader=None;writer=None
    chunks=queue.Queue(maxsize=2);writes=queue.Queue(maxsize=1)
    def heartbeat():
        with contextlib.closing(api['connect'](app.config['DB_PATH'])) as connection:
            while not stopped.wait(.5):
                try:
                    current=api['fence'](connection,t)
                    if not current:cancelled.set();process.terminate();return
                    connection.execute("UPDATE turns SET lease_until=? WHERE id=? AND generation=? AND status='running'",(api['now']()+120,t['id'],t['generation']))
                except Exception:cancelled.set();process.terminate();return
    def read_stdout():
        # Windows select() cannot wait on subprocess pipes. This bounded buffer
        # only transports bytes; SQLite turns/receipts remain the execution authority.
        while not stopped.is_set():
            try: item=process.stdout.read(65536)
            except (OSError,ValueError) as error: item=error
            while not stopped.is_set():
                try: chunks.put(item,timeout=.2);break
                except queue.Full:continue
            if not item or isinstance(item,Exception):return
    def check_progress():
        if cancelled.is_set():raise AgentError('cancelled','任务已停止')
        if time.monotonic()-started>remaining:raise AgentError('budget_exceeded','执行时间超出预算')
    def write_stdin():
        while not stopped.is_set():
            try:data,done,errors=writes.get(timeout=.2)
            except queue.Empty:continue
            try:
                view=memoryview(data)
                while view and not stopped.is_set():
                    size=process.stdin.write(view)
                    if not size:raise OSError('Agent input pipe closed')
                    view=view[size:]
                process.stdin.flush()
            except (OSError,ValueError) as error:errors.append(error)
            finally:done.set()
    def send(value):
        # Input can exceed an OS pipe buffer, so a stalled child must not block
        # the owner thread from enforcing the same deadline/cancellation fence.
        check_progress();done=threading.Event();errors=[]
        writes.put(((api['encode'](value)+'\n').encode(),done,errors))
        while not done.wait(.2):check_progress()
        check_progress()
        if errors:raise AgentError('runtime_unavailable','Agent输入写入失败')
    buffer=b'';total=0;last_body='';counts={'model':0,'tool':0};input_bytes=0;provider_output_bytes=sum(len(r[0].encode()) for r in db.execute("SELECT result FROM agent_receipts WHERE turn_id=? AND kind='model' AND state='sealed'",(t['id'],)));model_index=0
    try:
        process=subprocess.Popen(['node',str(launcher)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0,env=child_environment())
        maintenance=threading.Thread(target=heartbeat,daemon=True);maintenance.start()
        reader=threading.Thread(target=read_stdout,daemon=True);reader.start()
        writer=threading.Thread(target=write_stdin,daemon=True);writer.start()
        send(frame)
        while True:
            check_progress()
            try:chunk=chunks.get(timeout=.2)
            except queue.Empty:continue
            if isinstance(chunk,Exception):raise AgentError('runtime_unavailable','Agent输出读取失败')
            if not chunk:raise AgentError('runtime_unavailable','Agent没有返回成果')
            buffer+=chunk;total+=len(chunk)
            if total>budget['maxOutputBytes']:raise AgentError('budget_exceeded','输出超出预算')
            while b'\n' in buffer:
                line,buffer=buffer.split(b'\n',1)
                try: event=json.loads(line)
                except Exception:raise AgentError('runtime_unavailable','Agent协议无效')
                if not isinstance(event,dict):raise AgentError('runtime_unavailable','Agent协议无效')
                if event.get('type')=='finish':
                    if not last_body.strip():raise AgentError('runtime_unavailable','Agent没有完成回答')
                    return last_body
                if event.get('type')!='callback' or event.get('kind') not in ('model','tool') or not isinstance(event.get('callId'),str) or len(event['callId'])>100:raise AgentError('runtime_unavailable','Agent回调无效')
                kind=event['kind'];call_id=event['callId']
                if kind=='model':
                    input_bytes+=len(api['encode'](event.get('request',{})).encode())+(len(media['bytes'])*4//3 if media and model_index==0 else 0);model_index+=1
                    if input_bytes>budget['maxInputBytes']:raise AgentError('budget_exceeded','模型输入超出预算')
                digest=hashlib.sha256(api['encode'](event).encode()).hexdigest()
                with api['transaction'](db):
                    if not api['fence'](db,t):raise AgentError('cancelled','任务已停止')
                    for memory in payload.get('memories',[])+payload.get('historyMemoryIds',[]):
                        if not db.execute('SELECT id FROM memories WHERE id=? AND owner=? AND workspace_id=? AND deleted=0',(memory['id'],t['owner'],t['workspace_id'])).fetchone():raise AgentError('memory_revoked','使用的记忆已删除')
                    for frozen in [payload.get('agricultureContext',{})]+payload.get('historyAgricultureContexts',[]):agriculture.validate_context(db,t['owner'],t['workspace_id'],frozen)
                    old=db.execute('SELECT * FROM agent_receipts WHERE turn_id=? AND call_id=?',(t['id'],call_id)).fetchone()
                    if old:
                        if old['digest']!=digest:raise AgentError('runtime_unavailable','回执摘要不一致')
                        if old['state']!='sealed':raise AgentError('provider_uncertain','模型或工具结果未知，不会重发',True)
                        result=json.loads(old['result']);send({'callId':call_id,'ok':True,'result':model_tool_view(result) if kind=='tool' else result});last_body=result.get('body',last_body) if kind=='model' else last_body;continue
                    if kind=='model':configured(app.config,payload.get('processingKind','chat') if model_index==1 else 'chat')
                    counts[kind]+=1
                    used=db.execute('SELECT count(*) FROM agent_receipts WHERE turn_id=? AND kind=?',(t['id'],kind)).fetchone()[0]
                    if used>=budget['maxModelCalls' if kind=='model' else 'maxToolCalls']:raise AgentError('budget_exceeded','模型或工具调用超出预算')
                    db.execute('INSERT INTO agent_receipts VALUES(?,?,?,?,?,?,NULL)',(t['id'],t['generation'],call_id,kind,digest,'dispatched'))
                    if kind=='model':db.execute('UPDATE turns SET dispatched=1 WHERE id=?',(t['id'],))
                    else:
                        result=agriculture.execute_tool(db,t,event.get('name'),event.get('arguments'),t['id']+':'+call_id)
                        if isinstance(result,dict):result={'_toolName':event['name'],**result}
                        db.execute("UPDATE agent_receipts SET state='sealed',result=? WHERE turn_id=? AND call_id=?",(api['encode'](result),t['id'],call_id))
                if kind=='model':
                    try:result=complete(app.config,event.get('request',{}),media if used==0 else None,timeout=remaining-(time.monotonic()-started),check_progress=check_progress)
                    except AgentError:raise
                    except Exception as error:raise AgentError('provider_uncertain','模型请求结果未知，不会自动重发',True) from error
                    check_progress()
                    with api['transaction'](db):
                        check_progress()
                        if not api['fence'](db,t):raise AgentError('cancelled','任务已停止')
                        db.execute("UPDATE agent_receipts SET state='sealed',result=? WHERE turn_id=? AND call_id=?",(api['encode'](result),t['id'],call_id))
                    provider_output_bytes+=len(api['encode'](result).encode())
                    if provider_output_bytes>budget['maxOutputBytes']:raise AgentError('budget_exceeded','模型输出超出预算')
                    last_body=result.get('body','')
                send({'callId':call_id,'ok':True,'result':model_tool_view(result) if kind=='tool' else result})
    except (OSError,RuntimeError) as error:
        raise AgentError('runtime_unavailable','Agent运行时不可用') from error
    finally:
        stopped.set()
        if process is not None:
            if process.poll() is None:
                with contextlib.suppress(OSError):process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            process.stdin.close();process.stdout.close()
        for thread in (writer,reader,maintenance):
            if thread is not None and thread.is_alive():thread.join(timeout=2)
