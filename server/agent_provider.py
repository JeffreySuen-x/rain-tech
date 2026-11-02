"""Bounded OpenAI-compatible transport. No retries after dispatch."""
import json
import urllib.request
import base64
import secrets
import urllib.parse
import ipaddress

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderFailure('provider_uncertain','模型服务不允许重定向')

def validate_url(config):
    try:
        u=urllib.parse.urlsplit(config['PROVIDER_URL'])
        local=u.hostname=='localhost' or ipaddress.ip_address(u.hostname).is_loopback
    except ValueError:
        local=False
    try:
        if u.username or u.password or u.query or u.fragment or not u.hostname or u.scheme not in ('https','http') or (u.scheme=='http' and not (config.get('PRODUCTION') is False and local)):
            raise ValueError()
        u.port
    except (ValueError,UnboundLocalError):
        raise ProviderFailure('provider_unconfigured','模型服务地址无效')


class ProviderFailure(Exception):
    def __init__(self,code,message): self.code,self.message=code,message

def configured(config,kind='chat'):
    if not all(config.get(k) for k in ('PROVIDER_URL','PROVIDER_MODEL','PROVIDER_KEY')):
        raise ProviderFailure('provider_unconfigured','服务器尚未配置模型服务')
    validate_url(config)
    if config.get('PROVIDER_THINKING','') not in ('','disabled'):raise ProviderFailure('provider_unconfigured','模型思考配置无效')
    capability={'image_analysis':'vision','audio_transcription':'asr'}.get(kind,'text')
    caps=config.get('PROVIDER_CAPABILITIES','text')
    if capability not in (caps.split(',') if isinstance(caps,str) else caps):
        raise ProviderFailure('capability_unconfigured','服务器尚未配置此媒体能力')
    if kind=='audio_transcription' and config.get('PROVIDER_ASR_ADAPTER','transcriptions') not in ('transcriptions','input_audio'):
        raise ProviderFailure('capability_unconfigured','音频adapter未配置')

def _complete_http(config,request,media=None,timeout=60):
    kind=media['kind'] if media else 'chat'; configured(config,kind)
    model=config.get('PROVIDER_VISION_MODEL') if kind=='image_analysis' else config.get('PROVIDER_ASR_MODEL') if kind=='audio_transcription' else None
    data={'model':model or config['PROVIDER_MODEL'],'messages':request.get('messages',[]),'max_tokens':2400}
    if request.get('system'): data['messages']=[{'role':'system','content':request['system']}]+data['messages']
    if request.get('tools'): data['tools']=[{'type':'function','function':t.get('function',t)} for t in request['tools']]
    thinking=config.get('PROVIDER_THINKING','')
    if thinking not in ('','disabled'):raise ProviderFailure('provider_unconfigured','模型思考配置无效')
    if thinking:data['thinking']={'type':thinking}
    path='/chat/completions'; headers={'Authorization':'Bearer '+config['PROVIDER_KEY'],'Content-Type':'application/json'}
    if media:
        content=media['bytes']; mime=media['mime']
        if kind=='image_analysis':
            data['messages'][-1]['content']=[{'type':'text','text':str(data['messages'][-1].get('content',''))},{'type':'image_url','image_url':{'url':'data:'+mime+';base64,'+base64.b64encode(content).decode()}}]
        elif config.get('PROVIDER_ASR_ADAPTER','transcriptions')=='input_audio':
            data['messages'][-1]['content']=[{'type':'input_audio','input_audio':{'data':base64.b64encode(content).decode(),'format':{'audio/wav':'wav','audio/mpeg':'mp3','audio/webm':'webm'}.get(mime,'wav')}}]
        else:
            path='/audio/transcriptions'; boundary='shuyu-'+secrets.token_hex(16)
            extension={'audio/wav':'wav','audio/mpeg':'mp3','audio/webm':'webm','audio/ogg':'ogg','audio/flac':'flac','audio/mp4':'m4a'}.get(mime,'bin')
            raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{data["model"]}\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.{extension}"\r\nContent-Type: {mime}\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
            headers['Content-Type']='multipart/form-data; boundary='+boundary
    raw=raw if media and kind=='audio_transcription' and path.endswith('transcriptions') else json.dumps(data,ensure_ascii=False).encode()
    if len(raw)>24*1024*1024: raise ProviderFailure('too_large','模型输入过大')
    req=urllib.request.Request(config['PROVIDER_URL'].rstrip('/')+path,data=raw,headers=headers)
    with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=max(.1,min(60,timeout))) as response:
        result=response.read(256*1024+1)
    if len(result)>256*1024: raise ProviderFailure('provider_uncertain','模型响应过大')
    value=json.loads(result)
    message={'role':'assistant','content':value['text']} if path.endswith('transcriptions') else value['choices'][0]['message']
    text=message.get('content') or ''; calls=message.get('tool_calls') or []
    if not isinstance(text,str) or len(text)>100000 or not isinstance(calls,list) or len(calls)>16: raise ValueError('invalid provider response')
    blocks=([{'type':'text','text':text}] if text else [])+[{'type':'tool-call','id':c['id'],'name':c['function']['name'],'arguments':c['function']['arguments']} for c in calls]
    chunks=[]
    for i,b in enumerate(blocks):
        chunks.append({'type':'block-start','index':i,'blockType':b['type']})
        chunks.append({'type':'text-delta','index':i,'text':b['text']} if b['type']=='text' else {'type':'tool-call-delta','index':i,'id':b['id'],'name':b['name'],'argumentsDelta':b['arguments']})
        chunks.append({'type':'block-end','index':i,'block':b})
    usage=value.get('usage')
    if isinstance(usage,dict) and all(isinstance(usage.get(k),int) and usage[k]>=0 for k in ('prompt_tokens','completion_tokens','total_tokens')):
        chunks.append({'type':'usage','usage':{'inputTokens':usage['prompt_tokens'],'outputTokens':usage['completion_tokens'],'totalTokens':usage['total_tokens']}})
    chunks.append({'type':'finish','reason':{'kind':'tool-calls' if calls else 'stop'}})
    return {'chunks':chunks,'body':text,'usage':usage if isinstance(usage,dict) else None}


def complete(config, request, media=None, timeout=60, *, check_progress=None):
    """Own the entire transport lifetime, including DNS and pipe transfer."""
    import os
    import pickle
    import subprocess
    import sys
    import threading
    import time
    from pathlib import Path
    deadline = time.monotonic() + max(0, min(60, timeout))
    def progress():
        if check_progress:
            check_progress()
        if time.monotonic() >= deadline:
            if timeout < 60:
                from .agent_runtime import AgentError
                raise AgentError('budget_exceeded', '执行时间超出预算')
            raise ProviderFailure('provider_uncertain', '模型请求超时')
    progress()
    configured(config, media['kind'] if media else 'chat')
    projection = {k: config[k] for k in (
        'PROVIDER_URL', 'PROVIDER_MODEL', 'PROVIDER_KEY', 'PROVIDER_THINKING',
        'PROVIDER_CAPABILITIES', 'PROVIDER_ASR_ADAPTER', 'PROVIDER_ASR_MODEL',
        'PROVIDER_VISION_MODEL', 'PRODUCTION') if k in config}
    process = subprocess.Popen([sys.executable, '-m', 'server.agent_provider_worker'],
        cwd=str(Path(__file__).resolve().parent.parent), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={k: v for k, v in os.environ.items() if k in ('SYSTEMROOT', 'WINDIR', 'LANG', 'LC_ALL', 'PATH')})
    output = []; errors = []
    def writer():
        try:
            pickle.dump((projection, request, media, min(60, timeout)), process.stdin)
            process.stdin.close()
        except (OSError, ValueError):
            errors.append(True)
    def reader():
        try:
            output.append(process.stdout.read(2 * 1024 * 1024 + 1))
        except (OSError, ValueError):
            errors.append(True)
    threads = [threading.Thread(target=writer, name='provider-input'),
               threading.Thread(target=reader, name='provider-output')]
    try:
        for thread in threads: thread.start()
        while process.poll() is None:
            progress()
            time.sleep(.025)
        progress()
        for thread in threads: thread.join(.5)
        if errors or not output or len(output[0]) > 2 * 1024 * 1024:
            raise ValueError()
        value = pickle.loads(output[0])
        progress()
        if not value.get('ok'):
            raise ProviderFailure('provider_uncertain', '模型请求结果未知')
        return value['result']
    except (ValueError, EOFError, pickle.UnpicklingError, OSError):
        raise ProviderFailure('provider_uncertain', '模型请求结果未知') from None
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        else:
            process.wait()
        for thread in threads:
            if thread.ident is not None: thread.join(1)
        process.stdin.close()
        process.stdout.close()
