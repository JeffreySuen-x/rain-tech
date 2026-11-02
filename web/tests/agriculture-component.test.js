import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createRenderer, h, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import * as vue from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import { readFileSync } from 'node:fs'
import * as agricultureApi from '../src/agriculture/api.js'
import { useLocalSpeech } from '../src/agriculture/useLocalSpeech.js'
import { useLiveDemo } from '../src/agriculture/useLiveDemo.js'
import * as presentation from '../src/agriculture/presentation.js'
import * as calendarPresentation from '../src/agriculture/calendarPresentation.js'
import BrandMark from '../src/BrandMark.js'
import * as library from '../src/agriculture/library.js'
import * as mobileLearning from '../src/agriculture/mobile-learning.js'
import * as readerMarkdown from '../src/agriculture/reader-markdown.js'
import ReaderContent from '../src/agriculture/ReaderContent.js'
const readerDescriptor = parse(readFileSync(new URL('../src/agriculture/KnowledgeReader.vue', import.meta.url), 'utf8')).descriptor
let readerCode = compileScript(readerDescriptor,{id:'knowledge-reader-test',inlineTemplate:true}).content.replace(/^import\s+['"][^'"]+['"];?\s*$/gm,'').replace(/^import\s+\{([\s\S]*?)\}\s+from\s+['"]([^'"]+)['"];?/gm, (_m,n,module)=>`const {${n.replace(/\bas\b/g, ':')}} = bindings[${JSON.stringify(module)}];`).replace(/^import\s+(\w+)\s+from\s+['"]([^'"]+)['"];?/gm, (_m,n,module)=>`const ${n} = bindings[${JSON.stringify(module)}].default;`)
const KnowledgeReader = new Function('bindings',readerCode.replace('export default','return'))({vue,'./mobile-learning.js':mobileLearning,'./ReaderContent.js':{default:ReaderContent},'./reader-markdown.js':readerMarkdown})
const libraryDescriptor = parse(readFileSync(new URL('../src/agriculture/KnowledgeLibrary.vue', import.meta.url), 'utf8')).descriptor
let libraryCode = compileScript(libraryDescriptor,{id:'knowledge-library-test',inlineTemplate:true}).content.replace(/^import\s+\{([\s\S]*?)\}\s+from\s+['"]([^'"]+)['"];?/gm, (_m,n,module)=>`const {${n.replace(/\bas\b/g, ':')}} = bindings[${JSON.stringify(module)}];`)
libraryCode=libraryCode.replace(/^import\s+(\w+)\s+from\s+['"]([^'"]+)['"];?/gm, (_m,n,module)=>`const ${n} = bindings[${JSON.stringify(module)}].default;`)
const KnowledgeLibrary = new Function('bindings',libraryCode.replace('export default','return'))({vue,'./library.js':library,'./mobile-learning.js':mobileLearning,'./FriendlyIcon.vue':{default:{render:()=>null}}})
import { useWorkspace } from '../src/store.js'
import { request } from '../src/api.js'
vi.mock('../src/api.js', () => ({ request: vi.fn() }))
// Compile the actual SFC for a client renderer, rather than Vite's Node SSR transform.
const { descriptor } = parse(readFileSync(new URL('../src/agriculture/AgricultureWorkbench.vue', import.meta.url), 'utf8'))
let compiled = compileScript(descriptor, {id:'agriculture-component-test',inlineTemplate:true}).content
compiled = compiled.replace(/^import\s+['"][^'"]+['"];?\s*$/gm,'')
compiled = compiled.replace(/^import\s+\{([\s\S]*?)\}\s+from\s+['"]([^'"]+)['"];?/gm, (_match, names, module) => `const {${names.replace(/\bas\b/g, ':')}} = bindings[${JSON.stringify(module)}];`)
compiled = compiled.replace(/^import\s+(\w+)\s+from\s+['"]([^'"]+)['"];?/gm, (_match,name,module)=>`const ${name} = bindings[${JSON.stringify(module)}].default;`)
const panelDescriptor = parse(readFileSync(new URL('../src/agriculture/LiveFieldPanel.vue', import.meta.url), 'utf8')).descriptor
let panelCode = compileScript(panelDescriptor,{id:'live-panel-test',inlineTemplate:true,templateOptions:{compilerOptions:{hoistStatic:false}}}).content.replace(/^import\s+['"][^'"]+['"];?\s*$/gm,'').replace(/^import\s+\{([\s\S]*?)\}\s+from\s+['"]([^'"]+)['"];?/gm, (_m,n,module)=>`const {${n.replace(/\bas\b/g, ':')}} = bindings[${JSON.stringify(module)}];`)
panelCode=panelCode.replace(/^import\s+(\w+)\s+from\s+['"]([^'"]+)['"];?/gm, (_m,n,module)=>`const ${n} = bindings[${JSON.stringify(module)}].default;`)
const LiveFieldPanel = new Function('bindings',panelCode.replace('export default','return'))({vue,'./api.js':agricultureApi,'./FriendlyIcon.vue':{default:{render:()=>null}}})
const mobileDescriptor = parse(readFileSync(new URL('../src/agriculture/MobileGarden.vue', import.meta.url), 'utf8')).descriptor
let mobileCode = compileScript(mobileDescriptor,{id:'mobile-test',inlineTemplate:true}).content.replace(/^import\s+\{([\s\S]*?)\}\s+from\s+['"]([^'"]+)['"];?/gm, (_m,n,module)=>`const {${n.replace(/\bas\b/g, ':')}} = bindings[${JSON.stringify(module)}];`)
mobileCode=mobileCode.replace(/^import\s+(\w+)\s+from\s+['"]([^'"]+)['"];?/gm,(_,n,m)=>`const ${n}=bindings[${JSON.stringify(m)}].default;`)
const MobileGarden = new Function('bindings',mobileCode.replace('export default','return'))({vue,'./FriendlyIcon.vue':{default:{render:()=>null}},'./api.js':agricultureApi,'./calendarPresentation.js':calendarPresentation})
const reportDescriptor=parse(readFileSync(new URL('../src/agriculture/ReportDocument.vue',import.meta.url),'utf8')).descriptor
let reportCode=compileScript(reportDescriptor,{id:'report-test',inlineTemplate:true}).content.replace(/^import\s+\{([\s\S]*?)\}\s+from\s+['"]([^'"]+)['"];?/gm,(_m,n,module)=>`const {${n.replace(/\bas\b/g,':')}}=bindings[${JSON.stringify(module)}];`)
const ReportDocument=new Function('bindings',reportCode.replace('export default','return'))({vue,'./useLocalSpeech.js':{useLocalSpeech},'./presentation.js':presentation})
const taskDescriptor=parse(readFileSync(new URL('../src/agriculture/MobileTaskFlow.vue',import.meta.url),'utf8')).descriptor
const taskCode=compileScript(taskDescriptor,{id:'real-task',inlineTemplate:true}).content.replace(/^import\s+\{([^}]+)\}\s+from\s+['"]vue['"];?/gm,(_,names)=>`const {${names.replace(/\bas\b/g,':')}}=vue;`)
const MobileTaskFlow=new Function('vue','agricultureApi',taskCode.replace(/^import\s+\{([^}]+)\}\s+from\s+['"]\.\/api.js['"];?/gm,(_,names)=>`const {${names}}=agricultureApi;`).replace('export default','return'))(vue,agricultureApi)
const safeComponentBindings = values => new Proxy(values, {get(target,key){ if(key in target)return target[key]; if(typeof key==='string' && key.endsWith('.vue'))return {default:{render:()=>null}}; throw new Error(`Missing test module binding: ${String(key)}`)}})
const AgricultureWorkbench = new Function('bindings', compiled.replace('export default', 'return'))(safeComponentBindings({vue, './MobileTaskFlow.vue':{default:MobileTaskFlow}, './MobileGarden.vue':{default:MobileGarden}, './FriendlyIcon.vue':{default:{render:()=>null}}, './ReportDocument.vue':{default:ReportDocument}, './VoiceRecorder.vue':{default:{render:()=>null}}, './useLocalSpeech.js':{useLocalSpeech}, './KnowledgeReader.vue':{default:KnowledgeReader}, './KnowledgeLibrary.vue':{default:KnowledgeLibrary}, './library.js':library,'./mobile-learning.js':mobileLearning, './LiveFieldPanel.vue':{default:LiveFieldPanel}, './useLiveDemo.js':{useLiveDemo}, '../BrandMark.js':{default:BrandMark}, '../store.js':{useWorkspace,statusNames:{queued:'等待执行',running:'正在思考'}}, '../api.js':{request}, './api.js':agricultureApi, './presentation.js':presentation, './calendarPresentation.js':calendarPresentation}))

const node = (tag, text = '') => vue.markRaw({tag,tagName:tag.toUpperCase(),text,style:{},props:{},children:[],parent:null,addEventListener(){},removeEventListener(){},querySelector(selector){return all(this).find(n=>n.props.class===selector.slice(1))},contains(other){return this===other||this.children.some(n=>n.contains(other))},closest(){return null},focus(){},getRootNode(){return globalThis.document},get parentElement(){return this.parent},classList:{contains(){return false}},get options(){return this.children.filter(child=>child.tag==='option')},value:'',multiple:false})
const renderer = createRenderer({
  createElement: tag => node(tag), createText: text => node('#text',text), createComment: text => node('#comment',text),
  insert(child,parent,anchor) { if(child.parent) this.remove(child); const index=parent.children.indexOf(anchor); if(index<0) parent.children.push(child); else parent.children.splice(index,0,child); child.parent=parent },
  remove(child) { if(child.parent) child.parent.children.splice(child.parent.children.indexOf(child),1); child.parent=null },
  setText(element,text) {element.text=text}, setElementText(element,text) {element.text=text;element.children=[]},
  parentNode: element=>element.parent, nextSibling: element=>element.parent?.children[element.parent.children.indexOf(element)+1] || null,
  patchProp(element,key,_previous,value){element.props[key]=value;if(key==='value')element._value=value},
})
const all = root => [root,...root.children.flatMap(all)]
const text = root => root.text + root.children.map(text).join('')
let app, s, root, vueErrors=[]
beforeEach(async()=>{
  vueErrors=[];vi.spyOn(console,'error').mockImplementation((...args)=>vueErrors.push(args));
  vi.stubGlobal('Document',class Document {});vi.stubGlobal('ShadowRoot',class ShadowRoot {});vi.stubGlobal('document',{addEventListener:vi.fn(),removeEventListener:vi.fn(),activeElement:null,body:{style:{overflow:''}}})
  const pinia=createPinia();setActivePinia(pinia);s=useWorkspace();s.user={id:'owner'};s.workspaceId='w';s.workspaces=[{id:'w',name:'园区'}]
  request.mockImplementation(path=>Promise.resolve(path.endsWith('/assets')?{assets:[{id:'doc',name:'巡查.md',kind:'document',status:'ready'},{id:'image',name:'叶片.png',kind:'image',status:'stored'},{id:'audio',name:'录音.wav',kind:'audio',status:'stored'}]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}))
  app=renderer.createApp(h(AgricultureWorkbench));app.use(pinia);root=node('root');app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await Promise.resolve();await Promise.resolve();await nextTick()
})
afterEach(()=>{app?.unmount();expect(vueErrors).toEqual([]);vi.restoreAllMocks();vi.unstubAllGlobals()})
it('compiled composer submit treats the DOM event as a fresh send and preserves the first prompt through thread creation',async()=>{
  s.prompt='这张叶片照片需要核实什么？';s.createThread=vi.fn(async()=>{s.threadId='new-thread';s.prompt='';return true});s.submit=vi.fn(async()=>true)
  const composer=all(root).find(element=>element.tag==='form' && element.props.class==='agri-composer')
  const submit={type:'submit',preventDefault:vi.fn()};await composer.props.onSubmit(submit)
  expect(submit.preventDefault).toHaveBeenCalled();expect(s.createThread).toHaveBeenCalledOnce();expect(s.submit).toHaveBeenCalledWith(false);expect(s.prompt).toBe('这张叶片照片需要核实什么？')
  const retry=all(root).find(element=>element.tag==='button' && text(element).includes('确认原请求'))
  expect(retry).toBeUndefined();s.pending={commandId:'original'};await nextTick();const confirm=all(root).find(element=>element.tag==='button' && text(element).includes('确认原请求'));await confirm.props.onClick({type:'click'});expect(s.submit).toHaveBeenLastCalledWith(true)
})
it('compiled knowledge rows offer document reading/reference, image analysis, and audio transcription with Chinese states',async()=>{
  const knowledge=all(root).find(element=>element.tag==='button' && text(element)==='学习知识库');knowledge.props.onClick({type:'click'});await nextTick()
  const rows=all(root).filter(element=>element.props.class==='agri-row')
  const document=rows.find(element=>text(element).includes('巡查.md'));expect(text(document)).toContain('可阅读与引用');expect(text(document)).toContain('阅读原文');expect(text(document)).toContain('加入对话引用');expect(text(document)).not.toContain('分析照片');expect(text(document)).not.toContain('转写音频')
  expect(text(rows.find(element=>text(element).includes('叶片.png')))).toContain('分析照片')
  expect(text(rows.find(element=>text(element).includes('录音.wav')))).toContain('转写音频')
})
it('renders readable source title, position and excerpt without replaying historical transcription into the editable draft',async()=>{
  s.submit=vi.fn();s.turns=[{id:'asr',status:'completed',processingKind:'audio_transcription'}]
  s.artifact={id:'draft',turnId:'asr',body:'先检查叶背，再补拍整株。',sources:[{references:[{title:'园区巡查记录',locator:'lines:3-4',excerpt:'三号地块叶片出现斑点。',version:2}]}]}
  await nextTick();await nextTick()
  expect(s.prompt).toBe('');expect(s.submit).not.toHaveBeenCalled()
  const sourceButton=all(root).find(element=>element.tag==='button' && text(element)==='查看本轮来源 ↗');sourceButton.props.onClick();await nextTick();const source=all(root).find(element=>element.tag==='pre')
  expect(text(source)).toContain('园区巡查记录');expect(text(source)).toContain('位置：lines:3-4');expect(text(source)).toContain('三号地块叶片出现斑点。')
  const composer=all(root).find(element=>element.tag==='textarea' && element.props['aria-label']==='描述现场或询问下一步')
  composer.props['onUpdate:modelValue']('用户核对后的草稿');expect(s.prompt).toBe('用户核对后的草稿')
})

it('renders the current Shuyu product brand and shared mascot entry without legacy visible brand',()=>{
  expect(text(root)).toContain('澍雨');expect(text(root)).toContain('澍雨 Agent');
  const logos=all(root).filter(element=>element.tag==='img' && element.props.class?.includes('shuyu-brand-mark'));expect(logos.length).toBeGreaterThanOrEqual(2);for(const logo of logos)expect(logo.props.src).toBe('/brand/shuyu-raindrop-v1.png')
})
it('history checkbox is explicit and the compiled submit freezes its value across uncertain retry',async()=>{
  s.threadId='thread';s.prompt='只核对已选内容';let attempts=0
  request.mockImplementation(path=>path.endsWith('/turns') ? (++attempts===1 ? Promise.reject(Object.assign(new Error('unknown'),{status:0})) : Promise.resolve({turn:{id:'turn',status:'queued'}})) : Promise.resolve({messages:[],turns:[{id:'turn',status:'queued'}]}))
  all(root).find(element=>element.props['aria-label']==='对话设置').props.onClick();await nextTick();const choice=all(root).find(element=>element.tag==='input' && element.parent?.props.class==='agri-history-choice');expect(s.includeHistory).toBe(false)
  choice.props['onUpdate:modelValue'](true);expect(s.includeHistory).toBe(true);await nextTick()
  const composer=all(root).find(element=>element.tag==='form' && element.props.class==='agri-composer');await composer.props.onSubmit({type:'submit',preventDefault(){}})
  const frozen=s.pending;expect(frozen.includeHistory).toBe(true)
  s.includeHistory=false;await nextTick();const retry=all(root).find(element=>element.tag==='button' && text(element).includes('确认原请求'));await retry.props.onClick({type:'click'})
  const writes=request.mock.calls.filter(([path])=>path.endsWith('/turns'));expect(writes).toHaveLength(2);expect(writes[1][1].body.includeHistory).toBe(true);expect(writes[1][1].body.commandId).toBe(frozen.commandId)
})
it('upload saves a file without authorizing model context until the user clicks Join this turn',async()=>{
  const uploaded={id:'uploaded',name:'新记录.md',kind:'document',status:'ready'}
  request.mockImplementation((path,options)=>Promise.resolve(path.endsWith('/assets') ? (options?.method==='POST'?{asset:uploaded}:{assets:[uploaded]}) : path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}))
  const file=all(root).find(element=>element.tag==='input' && element.props.type==='file')
  await file.props.onChange({target:{files:[new Blob(['new field notes'])],value:'chosen'}});await nextTick()
  const receipt=all(root).find(element=>element.props.class==='agri-upload-receipt');expect(text(root)).toContain('尚未加入本轮，也未发送给模型服务');expect(text(root)).not.toContain('已选 1 份资料')
  const mobileReceipt=all(root).find(element=>element.props.class==='mobile-upload-receipt');expect(text(mobileReceipt)).toContain('已保存，尚未转写')
  const join=all(mobileReceipt).find(element=>element.tag==='button' && text(element)==='加入本轮');join.props.onClick({type:'click'});await nextTick();expect(text(root)).toContain('已选 1 份资料')
  expect(text(receipt)).toContain('取消本轮引用')
  s.workspaceId='other';await settle();expect(all(root).some(element=>element.props.class==='mobile-upload-receipt')).toBe(false)
})
it('media action sends only its file action identity even when chat history and other context are selected',async()=>{
  s.threadId='thread';s.includeHistory=true;s.agricultureContext={assetIds:['unrelated'],knowledgeIds:['unrelated-knowledge']}
  request.mockImplementation(path=>Promise.resolve(path.endsWith('/analyze')?{turn:{id:'photo-turn',status:'queued'}}:path.endsWith('/assets')?{assets:[{id:'image',name:'叶片.png',kind:'image',status:'stored'}]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}))
  all(root).find(element=>element.tag==='button' && text(element)==='对话').props.onClick({type:'click'});await nextTick()
  const analyze=all(root).find(element=>element.tag==='button' && text(element)==='分析照片');await analyze.props.onClick({type:'click'})
  const body=request.mock.calls.find(([path])=>path==='/assets/image/analyze')[1].body;expect(body.threadId).toBe('thread');expect(body.commandId).toBeTruthy();expect(Object.keys(body).sort()).toEqual(['commandId','threadId'])
})

it('overview shows the latest two photos in server order and keeps all three materials',async()=>{
  const photos=[
    {id:'newest-garden',name:'最新园区.png',kind:'image',status:'ready',createdAt:300},
    {id:'recent-leaf',name:'近期叶片.png',kind:'image',status:'ready',createdAt:200},
    {id:'old-photo',name:'旧照片.png',kind:'image',status:'ready',createdAt:100},
  ]
  request.mockImplementation(path=>Promise.resolve(path.endsWith('/assets')?{assets:photos}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}))
  const refresh=all(root).find(element=>element.tag==='button' && text(element)==='刷新')
  await refresh.props.onClick({type:'click'});await nextTick()
  const scene=all(root).find(element=>element.props.class==='agri-photos')
  expect(all(scene).filter(element=>element.tag==='img').map(element=>element.props.alt)).toEqual(['最新园区.png','近期叶片.png'])
  all(root).find(element=>element.tag==='button' && text(element)==='学习知识库').props.onClick({type:'click'});await nextTick()
  const rows=all(root).filter(element=>element.props.class==='agri-row')
  for(const photo of photos)expect(rows.some(element=>text(element).includes(photo.name))).toBe(true)
})

const demoProjection = (version=1) => ({mode:'demo',enabled:true,label:'演示模式 · 设备与画面为模拟',version,paused:false,scenario:'normal',observedAt:Date.now()/1000,staleAfterSeconds:20,status:'online',samples:[{temperature:24.2,humidity:68,soil_moisture:42,observedAt:Date.now()/1000}],cameras:[{id:'cam',name:'葡萄行相机',assetId:'photo',status:'online'}],captures:[],events:[{id:'event',message:'机器人开始巡检',observedAt:Date.now()/1000}],robot:{id:'robot',name:'巡园一号',state:'idle',position:{x:.1,y:.2},route:[{x:.1,y:.2},{x:.8,y:.2}],battery:92,progress:10}})
const settle = async () => {for(let i=0;i<8;i++)await Promise.resolve();await nextTick()}
it('renders real demo panel and sends scenario/camera/robot commands with CSRF while pending prevents duplicate actions',async()=>{
  app.unmount();let resolveAction
  request.mockImplementation((path,options)=> {
    if(path.includes('/live-demo/actions'))return new Promise(resolve=>resolveAction=resolve)
    if(path.includes('/live-demo'))return Promise.resolve({liveDemo:demoProjection()})
    return Promise.resolve(path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]})
  })
  s.csrf='csrf-token';app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await settle()
  expect(text(root)).toContain('演示模式');expect(text(root)).toContain('24.2');expect(text(root)).toContain('机器人开始巡检');expect(text(root)).not.toContain('手工录入会明确标识来源')
  const capture=all(root).find(el=>el.tag==='button'&&text(el).includes('抓拍并保存'));capture.props.onClick();await settle();expect(capture.props.disabled).toBe(true)
  capture.props.onClick();expect(request.mock.calls.filter(([path])=>path.endsWith('/actions'))).toHaveLength(1)
  const write=request.mock.calls.find(([path])=>path.endsWith('/actions'))[1];expect(write.csrf).toBe('csrf-token');expect(write.body).toMatchObject({action:'camera.capture',cameraId:'cam'});expect(write.body.commandId).toBeTruthy()
  resolveAction({liveDemo:{...demoProjection(2),paused:true}});await settle();expect(text(root)).toContain('继续演示')
  const scenario=all(root).find(el=>el.tag==='select'&&el.parent?.tag==='label'&&text(el.parent).includes('演示场景'));scenario.props.onChange({target:{value:'humidity_change'}})
  expect(request.mock.calls.filter(([path])=>path.endsWith('/actions')).at(-1)[1].body).toMatchObject({action:'scenario.set',scenario:'humidity_change'})
  resolveAction({liveDemo:demoProjection(3)});await settle()
  all(root).find(el=>el.tag==='button'&&text(el)==='开始巡检').props.onClick();expect(request.mock.calls.filter(([path])=>path.endsWith('/actions')).at(-1)[1].body.action).toBe('robot.start');resolveAction({liveDemo:demoProjection(4)});await settle()
})
it('rejects late demo responses from previous garden and shows connection errors without replacing real garden UI',async()=>{
  app.unmount();let oldResolve
  request.mockImplementation(path=> {
    if(path==='/workspaces/w/live-demo')return new Promise(resolve=>oldResolve=resolve)
    if(path.includes('/live-demo'))return Promise.reject(new Error('现场连接中断'))
    return Promise.resolve(path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]})
  })
  app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await settle();s.workspaceId='other';await settle();oldResolve({liveDemo:demoProjection(99)});await settle();expect(text(root)).not.toContain('演示模式');expect(text(root)).toContain('等待监测数据')
})
it('demo action uncertainty requires explicit reconcile and explanation only edits the unsent draft',async()=>{
  app.unmount();request.mockImplementation((path,options)=>path.endsWith('/actions')?Promise.reject(Object.assign(new Error('连接中断，请核对'),{status:0})):Promise.resolve(path.includes('/live-demo')?{liveDemo:demoProjection()}:path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}))
  app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await settle();s.submit=vi.fn()
  all(root).find(el=>el.tag==='button'&&text(el).includes('让澍雨解释')).props.onClick();expect(s.prompt).toContain('正常巡检');expect(s.submit).not.toHaveBeenCalled();await nextTick();expect(s.prompt).toContain('正常巡检');all(root).find(el=>el.tag==='button'&&text(el)==='园区监控').props.onClick();await nextTick()
  all(root).find(el=>el.tag==='button'&&text(el)==='暂停演示').props.onClick();await settle();expect(text(root)).toContain('操作结果尚未确认');expect(all(root).find(el=>el.tag==='button'&&text(el)==='暂停演示').props.disabled).toBe(true)
  await all(root).find(el=>el.tag==='button'&&text(el)==='刷新并核对状态').props.onClick();await settle();expect(text(root)).toContain('操作结果尚未确认')
})
it('demo polling pauses for hidden page, resumes on visibility, and stale read versions cannot overwrite an action',async()=>{
  app.unmount();vi.useFakeTimers();let readResolve
  request.mockImplementation((path,options)=> {
    if(path.endsWith('/actions'))return Promise.resolve({liveDemo:{...demoProjection(5),paused:true}})
    if(path.includes('/live-demo'))return readResolve ? new Promise(resolve=>readResolve=resolve) : Promise.resolve({liveDemo:demoProjection(1)})
    return Promise.resolve(path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]})
  })
  app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await settle()
  const visibility=document.addEventListener.mock.calls.filter(([name])=>name==='visibilitychange').at(-1)[1]
  const before=request.mock.calls.filter(([path])=>path.includes('/live-demo')).length
  document.hidden=true;visibility();await vi.advanceTimersByTimeAsync(11000);expect(request.mock.calls.filter(([path])=>path.includes('/live-demo'))).toHaveLength(before)
  document.hidden=false;visibility();await settle();expect(request.mock.calls.filter(([path])=>path.includes('/live-demo')).length).toBe(before+1)
  readResolve=true;await vi.advanceTimersByTimeAsync(5000);await all(root).find(el=>el.tag==='button'&&text(el)==='暂停演示').props.onClick();await settle();expect(text(root)).toContain('继续演示');readResolve({liveDemo:demoProjection(2)});await settle();expect(text(root)).toContain('继续演示');app.unmount();vi.useRealTimers()
})
it('demo null robot and empty metrics render an unbound state, null camera image cannot capture',async()=>{
  app.unmount();const live={...demoProjection(),robot:null,samples:[],cameras:[{id:'cam',name:'未绑定画面',assetId:null}],captures:[{id:'empty',assetId:null}]}
  request.mockImplementation(path=>Promise.resolve(path.includes('/live-demo')?{liveDemo:live}:path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}))
  app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await settle();expect(text(root)).toContain('所选地块未绑定演示巡检机器人');expect(text(root)).toContain('所选地块无监测绑定');expect(all(root).find(el=>el.tag==='button'&&text(el).includes('抓拍并保存')).props.disabled).toBe(true);expect(all(root).filter(el=>el.tag==='img').some(el=>el.props.src?.includes('/null/'))).toBe(false)
})
it('global pause takes priority over stale age and worker stale never displays online devices',async()=>{
  app.unmount();let live={...demoProjection(),paused:true,observedAt:1,status:'paused'}
  request.mockImplementation(path=>Promise.resolve(path.includes('/live-demo')?{liveDemo:live}:path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}))
  app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await settle();expect(text(root)).toContain('演示已暂停');expect(text(root)).not.toContain('数据已过期');expect(text(root)).not.toContain('● 在线')
  all(root).find(el=>el.tag==='button'&&text(el)==='农业设备').props.onClick();await settle();expect(text(root)).not.toContain('● 在线');expect(text(root)).toContain('● 已暂停')
  app.unmount();root=node('root');app=renderer.createApp(h(LiveFieldPanel,{live:{...live,paused:false,status:'stale'},view:'devices',workspaceId:'w'}));app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await settle();expect(text(root)).toContain('数据已过期');expect(text(root)).not.toContain('● 在线')
})

it('one persistent Agent becomes the chat main area and collapse/expand preserves the draft and active turn',async()=>{
  s.prompt='未发送草稿';s.turns=[{id:'active',status:'running'}];await nextTick()
  expect(root.children[0].props.class).toContain('agent-collapsed')
  all(root).find(el=>el.tag==='button'&&text(el)==='问澍雨').props.onClick();await nextTick()
  const toggle=all(root).find(el=>el.tag==='button'&&text(el)==='收起助手');toggle.props.onClick();await nextTick()
  expect(all(root).find(el=>el.tag==='aside'&&el.props.class?.includes('agri-agent'))).toBeDefined()
  expect(s.prompt).toBe('未发送草稿');expect(s.activeTurn.id).toBe('active')
  all(root).find(el=>el.tag==='button'&&text(el)==='问澍雨').props.onClick();await nextTick()
  all(root).find(el=>el.tag==='button'&&text(el)==='对话').props.onClick();await nextTick()
  expect(all(root).filter(el=>el.tag==='form'&&el.props.class==='agri-composer')).toHaveLength(1)
  expect(root.children[0].props.class).toContain('chat-workspace');expect(s.prompt).toBe('未发送草稿');expect(s.activeTurn.id).toBe('active')
  all(root).find(el=>el.tag==='button'&&text(el)==='资料').props.onClick();await nextTick();expect(root.children[0].props.class).toContain('resources-open')
  all(root).find(el=>el.tag==='button'&&text(el)==='关闭资料 ✕').props.onClick();await nextTick();expect(s.prompt).toBe('未发送草稿')
})
it('skills load from the API and uncertain retries retain the original skill and command identity',async()=>{
  app.unmount();request.mockImplementation(path=>Promise.resolve(path==='/skills'?{skills:[{id:'shuyu.analyze.v1',label:'通用分析',kind:'chat',description:'请核对现场'},{id:'field.v1',label:'现场巡查',kind:'chat',description:'请列出巡查重点'},{id:'image.v1',label:'照片分析',kind:'image_analysis'}]}:path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}))
  app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await settle()
  const skill=all(root).find(el=>el.tag==='select'&&el.props['aria-label']==='本轮技能');skill.props['onUpdate:modelValue']('field.v1');await nextTick()
  const originalSubmit=s.submit;s.submit=vi.fn(async()=>true);all(root).find(el=>el.tag==='button'&&text(el)==='建议问题').props.onClick();expect(s.prompt).toBe('请列出巡查重点');expect(s.submit).not.toHaveBeenCalled()
  s.submit=originalSubmit;s.$reset();s.user={id:'owner'};s.workspaceId='w';s.threadId='thread';s.prompt='巡查';s.skillId='field.v1';let count=0
  request.mockImplementation(path=>path.endsWith('/turns')?(++count===1?Promise.reject(Object.assign(new Error('unknown'),{status:0})):Promise.resolve({turn:{id:'turn',status:'queued'}})):Promise.resolve({messages:[],turns:[]}))
  // Exercise the actual store rather than a component-only payload mock.
  await s.submit();const frozen=s.pending;expect(frozen.skillId).toBe('field.v1');s.skillId='shuyu.analyze.v1';await s.submit(true)
  const writes=request.mock.calls.filter(([path])=>path.endsWith('/turns'));expect(writes.at(-1)[1].body.skillId).toBe('field.v1');expect(writes.at(-1)[1].body.commandId).toBe(frozen.commandId)
})
it('scope changes remove selected materials and settings while task filters show only real open/completed states',async()=>{
  request.mockImplementation(path=>Promise.resolve(path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[{id:'open',title:'检查滴头',status:'open',dueAt:1},{id:'done',title:'已完成巡园',status:'completed'}],reports:[]}))
  await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle()
  all(root).find(el=>el.tag==='button'&&text(el)==='待办任务').props.onClick();await nextTick();expect(text(root)).toContain('检查滴头');expect(text(root)).not.toContain('已完成巡园');expect(text(root)).toContain('逾期')
  all(root).find(el=>el.tag==='button'&&text(el)==='已完成').props.onClick();await nextTick();expect(text(root)).toContain('已完成巡园');expect(text(all(root).find(el=>String(el.props.class).includes('desktop-task-flow')))).not.toContain('检查滴头')
  all(root).find(el=>el.props['aria-label']==='对话设置').props.onClick();await nextTick();expect(text(root)).toContain('默认不带历史');s.workspaceId='next';await settle();expect(text(root)).not.toContain('默认不带历史')
})
it('inventory renders server metrics/categories/details and never creates hardware controls',async()=>{
  app.unmount();const live={...demoProjection(),inventory:[{id:'demo-weather',name:'葡萄园微气象站',category:'环境感知',status:'paused',origin:'demo',observedAt:123,summary:'微气象观察',metrics:[{key:'temperature',label:'空气温度',value:24.2,unit:'°C'}],sources:['https://example.org/official']},{id:'demo-irrigation',name:'滴灌主管',category:'水肥灌溉',status:'paused',metrics:[{key:'flow',label:'流量',value:0,unit:'L/min'}]}]}
  app=renderer.createApp(h(LiveFieldPanel,{live,view:'devices',workspaceId:'w'}));root=node('root');app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await settle()
  expect(text(root)).toContain('葡萄园微气象站');expect(text(root)).toContain('24.2');expect(text(root)).toContain('滴灌主管')
  const order=all(root);expect(order.findIndex(el=>el.props.class==='agri-card inventory-section')).toBeLessThan(order.findIndex(el=>el.props.class==='live-scene-grid'))
  const first=all(root).find(el=>el.props.class==='inventory-card');expect(text(first)).toContain('已暂停');expect(text(first)).not.toContain('在线')
  all(first).find(el=>el.tag==='button'&&text(el).startsWith('设备详情')).props.onClick();await nextTick();expect(all(first).find(el=>el.tag==='a').props.href).toBe('https://example.org/official')
  all(root).find(el=>el.tag==='button'&&text(el)==='水肥灌溉').props.onClick();await nextTick();expect(text(root)).not.toContain('葡萄园微气象站');expect(text(root)).toContain('滴灌主管');expect(text(root)).not.toContain('开启灌溉')
})
it('knowledge cards filter actual assets, open excerpts, and require an explicit reference selection',async()=>{
  request.mockImplementation(path=>Promise.resolve(path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[{id:'k',title:'滴灌核查',assetId:'doc',library:{articleId:'MON-001',memberships:[]},excerpts:[{locator:'lines:1-2',text:'核查滴头与末端压力。'}]},{id:'k2',title:'叶片观察',excerpts:[{text:'补拍叶背。'}]}]}:path==='/knowledge/k'?{knowledge:{excerpts:[{locator:'lines:1-2',text:'核查滴头与末端压力。'}]}}:{devices:[],plots:[],workItems:[],reports:[]}))
  await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle();all(root).find(el=>el.tag==='button'&&text(el)==='学习知识库').props.onClick();await nextTick()
  const grid=all(root).find(el=>el.props.class==='knowledge-grid');expect(text(grid)).toContain('滴灌核查');expect(text(grid)).toContain('叶片观察');expect(text(root)).not.toContain('已选 0 份资料')
  all(root).find(el=>el.tag==='input'&&el.props['aria-label']==='搜索全部知识正文').props['onUpdate:modelValue']('滴灌');await nextTick();expect(text(grid)).not.toContain('叶片观察')
  all(grid).find(el=>el.tag==='button'&&text(el)==='加入对话引用').props.onClick();await nextTick();expect(text(root)).toContain('1 条知识')
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,status:200,text:async()=> '# 滴灌核查\n核查滴头与末端压力。\n末尾来源'})))
  await all(grid).find(el=>el.tag==='button'&&text(el)==='阅读原文').props.onClick();await settle();expect(text(root)).not.toContain('L3');expect(text(root)).toContain('末尾来源');all(root).find(el=>el.tag==='button'&&text(el)==='更多 ···').props.onClick();await nextTick();all(root).find(el=>el.tag==='button'&&text(el)==='原文与来源').props.onClick();await nextTick();expect(text(root)).toContain('L3');expect(fetch).toHaveBeenCalledWith('/api/v1/assets/doc/content',{credentials:'same-origin'})
})
it('message emphasis renders as safe text nodes with readable list lines',async()=>{
  s.messages=[{role:'assistant',content:'**先观察**\n- 拍摄叶背\n<script>alert(1)</script>'}];await nextTick()
  expect(all(root).some(el=>el.tag==='strong'&&text(el)==='先观察')).toBe(true);expect(text(root)).toContain('• 拍摄叶背');expect(text(root)).toContain('<script>alert(1)</script>');expect(all(root).some(el=>el.tag==='script')).toBe(false)
})
it('media skills block an empty selection and send only the explicitly selected original photo',async()=>{
  app.unmount();request.mockClear();request.mockImplementation(path=>Promise.resolve(path==='/skills'?{skills:[{id:'shuyu.analyze.v1',label:'通用分析',kind:'chat'},{id:'image.v1',label:'照片分析',kind:'image_analysis'}]}:path.endsWith('/analyze')?{turn:{id:'media',status:'queued'}}:path.endsWith('/assets')?{assets:[{id:'photo',name:'叶片.png',kind:'image',status:'stored'}]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}))
  app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.config.errorHandler=(error)=>vueErrors.push(error);app.mount(root);await settle();s.threadId='thread';s.includeHistory=true
  all(root).find(el=>el.tag==='select'&&el.props['aria-label']==='本轮技能').props['onUpdate:modelValue']('image.v1');await nextTick()
  const composer=all(root).find(el=>el.tag==='form'&&el.props.class==='agri-composer');await composer.props.onSubmit({preventDefault(){}});await nextTick();expect(text(root)).toContain('请在资料侧栏明确选择一份照片');expect(request.mock.calls.some(([path])=>path.endsWith('/analyze'))).toBe(false)
  all(root).find(el=>el.tag==='button'&&text(el)==='对话').props.onClick();await nextTick();all(root).find(el=>el.tag==='input'&&el.props.type==='checkbox').props.onChange();await nextTick()
  await composer.props.onSubmit({preventDefault(){}});const call=request.mock.calls.find(([path])=>path.endsWith('/analyze'));expect(call[0]).toBe('/assets/photo/analyze');expect(Object.keys(call[1].body).sort()).toEqual(['commandId','threadId']);expect(request.mock.calls.some(([path])=>path.endsWith('/turns'))).toBe(false)
})
it('entering chat finds the latest message while new answers preserve a reader scrolled into history',async()=>{
  const list=all(root).find(el=>el.props.class==='agri-messages');list.scrollHeight=1000;list.clientHeight=400;list.scrollTop=0
  s.messages=[{role:'assistant',content:'历史回答'}];all(root).find(el=>el.tag==='button'&&text(el)==='对话').props.onClick();await settle();expect(list.scrollTop).toBe(1000)
  list.scrollTop=100;list.props.onScroll();list.scrollHeight=1200;s.messages.push({role:'assistant',content:'新增回答'});await settle();expect(list.scrollTop).toBe(100)
  list.scrollTop=850;list.props.onScroll();list.scrollHeight=1400;s.messages.push({role:'assistant',content:'继续更新'});await settle();expect(list.scrollTop).toBe(1400)
  list.scrollTop=0;list.props.onScroll();s.threadId='another-thread';await settle();expect(list.scrollTop).toBe(1400)
})
it('resource tabs keep material title and action rows separate and preserve explicit references',async()=>{
  all(root).find(el=>el.tag==='button'&&text(el)==='对话').props.onClick();await nextTick()
  const row=all(root).find(el=>el.props.class==='agri-row resource-asset');const title=all(row).find(el=>el.tag==='span'&&el.props.title==='巡查.md');expect(title).toBeDefined();expect(title.parent.props.class).toBe('resource-asset-label')
  const actions=all(row).find(el=>el.props.class==='resource-asset-actions');expect(text(actions)).toContain('原文');expect(text(actions)).toContain('移除资料');all(row).find(el=>el.tag==='input').props.onChange();await nextTick()
  all(root).find(el=>el.tag==='button'&&text(el)==='会话记录').props.onClick();await nextTick();expect(all(root).some(el=>el.props.class==='agri-row resource-asset')).toBe(false)
  all(root).find(el=>el.tag==='button'&&text(el)==='本轮资料').props.onClick();await nextTick();expect(text(root)).toContain('已选 1 份资料')
})
it('knowledge summaries skip Markdown headings and originals/media are folded by default',async()=>{
  request.mockImplementation(path=>Promise.resolve(path.endsWith('/assets')?{assets:[{id:'image',name:'叶片.png',kind:'image',status:'stored'}]}:path.endsWith('/knowledge')?{knowledge:[{id:'k',title:'巡田拍照',excerpts:[{text:'# 巡田拍照'},{text:'先确认地块与生育阶段，再记录全景、整株和叶片正反面。'},{text:'## 来源与适用范围'}]}]}:{devices:[],plots:[],workItems:[],reports:[]}))
  await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle();all(root).find(el=>el.tag==='button'&&text(el)==='学习知识库').props.onClick();await nextTick()
  const grid=all(root).find(el=>el.props.class==='knowledge-grid');expect(text(grid)).toContain('先确认地块与生育阶段');expect(text(grid)).not.toContain('# 巡田拍照');expect(text(grid)).not.toContain('来源与适用范围')
  const originals=all(root).find(el=>el.tag==='details'&&el.props.class==='knowledge-originals');expect(originals.props.open).toBeUndefined();expect(text(originals)).toContain('原件与媒体（1）');expect(text(originals)).toContain('分析照片');expect(text(originals)).toContain('发送此照片');expect(all(grid).some(el=>el.props.class==='agri-media-disclosure')).toBe(false)
})
it('reader request sequencing drops older articles and closed responses without choosing knowledge',async()=>{
 const docs=[{id:'a',title:'文章甲',assetId:'asset-a',library:{id:'lib',sourceRelativePath:'articles/a.md'},excerpts:[]},{id:'b',title:'文章乙',assetId:'asset-b',library:{id:'lib',sourceRelativePath:'articles/b.md'},excerpts:[]}]
 request.mockImplementation(path=>Promise.resolve(path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:docs}:path==='/knowledge/a'?{knowledge:docs[0]}:path==='/knowledge/b'?{knowledge:docs[1]}:{devices:[],plots:[],workItems:[],reports:[]}))
 const pending=[];vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,status:200,text:()=>new Promise(resolve=>pending.push(resolve))})))
 await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle();all(root).find(el=>el.tag==='button'&&text(el)==='学习知识库').props.onClick();await nextTick()
 let reads=all(root).filter(el=>el.tag==='button'&&text(el)==='阅读原文');const first=reads[0].props.onClick();await settle();const second=reads[1].props.onClick();await settle()
 expect(pending).toHaveLength(2);pending[1]('# 文章乙\n当前乙正文');await second;await settle();pending[0]('# 文章甲\n过期甲正文');await first;await settle()
 expect(text(root)).toContain('当前乙正文');expect(text(root)).not.toContain('过期甲正文');expect(text(root)).not.toContain('已选 0 份资料')
 all(root).find(el=>el.tag==='button'&&text(el)==='← 学习').props.onClick();await nextTick()
 const third=reads[0].props.onClick();await settle();all(root).find(el=>el.tag==='button'&&text(el)==='← 学习').props.onClick();await nextTick();pending[2]('# 关闭后正文');await third;await settle()
 expect(text(root)).not.toContain('关闭后正文');expect(all(root).some(el=>el.props.class==='reader-toolbar')).toBe(false)
})
it('cross-workspace changes close the reader and discard its pending original',async()=>{
 const item={id:'k',title:'跨园区测试',assetId:'asset-k',library:{id:'lib',sourceRelativePath:'articles/k.md'},excerpts:[]}
 request.mockImplementation(path=>Promise.resolve(path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[item]}:path==='/knowledge/k'?{knowledge:item}:{devices:[],plots:[],workItems:[],reports:[]}))
 let finish;vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,status:200,text:()=>new Promise(resolve=>finish=resolve)})))
 await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle();all(root).find(el=>el.tag==='button'&&text(el)==='学习知识库').props.onClick();await nextTick()
 const opening=all(root).find(el=>el.tag==='button'&&text(el)==='阅读原文').props.onClick();await settle();s.workspaceId='another';await settle();finish('# 旧园区私有正文');await opening;await settle()
 expect(text(root)).not.toContain('旧园区私有正文');expect(all(root).some(el=>el.props.class==='reader-toolbar')).toBe(false)
})

it('mobile navigation reuses the persistent composer, references, skill and thread state across all three tabs', async()=>{
  s.prompt='保留现场草稿';s.threadId='existing';s.skillId='shuyu.analyze.v1'
  const nav=all(root).find(element=>element.tag==='nav' && element.props['aria-label']==='手机工作台')
  expect(nav.children.filter(element=>element.tag==='button')).toHaveLength(3)
  for(const button of nav.children.filter(element=>element.tag==='button')){
    button.props.onClick();await nextTick()
    expect(s.prompt).toBe('保留现场草稿');expect(s.threadId).toBe('existing');expect(s.skillId).toBe('shuyu.analyze.v1')
    expect(all(root).filter(element=>element.tag==='form' && element.props.class==='agri-composer')).toHaveLength(1)
  }
})

// Independent responsive acceptance: exercise real compiled SFC events.
it('independent mobile three tabs preserve chosen reference and composer identity without sending', async()=>{
  s.submit=vi.fn();s.prompt='独立验收草稿';s.threadId='kept';s.skillId='shuyu.analyze.v1'
  all(root).find(el=>el.tag==='button'&&text(el)==='对话').props.onClick();await nextTick()
  const row=all(root).find(el=>el.props.class==='agri-row resource-asset')
  all(row).find(el=>el.tag==='input').props.onChange();await nextTick()
  const composer=all(root).find(el=>el.props.class==='agri-composer')
  const nav=all(root).find(el=>el.props['aria-label']==='手机工作台')
  for(const button of nav.children.filter(el=>el.tag==='button')){
    button.props.onClick();await nextTick()
    expect(all(root).find(el=>el.props.class==='agri-composer')).toBe(composer)
    expect(text(root)).toContain('已选 1 份资料');expect(s.prompt).toBe('独立验收草稿');expect(s.threadId).toBe('kept')
  }
  expect(s.submit).not.toHaveBeenCalled()
  s.workspaceId='next-workspace';await settle();expect(text(root)).not.toContain('已选 1 份资料')
})
it('independent mobile menu closes through every bottom navigation action', async()=>{
 const header=all(root).find(el=>el.props.class==='mobile-workspace-header')
 const menu={props:{onClick:()=>all(root).find(el=>el.props['aria-controls']==='garden-menu').props.onClick(),get 'aria-expanded'(){return all(root).find(el=>el.props['aria-controls']==='garden-menu')?.props['aria-expanded'] ?? false}}}
 const nav=all(root).find(el=>el.props['aria-label']==='手机工作台')
 for(const button of nav.children.filter(el=>el.tag==='button')){
  nav.children.filter(el=>el.tag==='button')[0].props.onClick();await nextTick()
  menu.props.onClick();await nextTick();expect(menu.props['aria-expanded']).toBe(true)
  button.props.onClick();await nextTick();expect(menu.props['aria-expanded']).toBe(false)
 }
 nav.children.filter(el=>el.tag==='button')[0].props.onClick();await nextTick()
 menu.props.onClick();await nextTick();expect(menu.props['aria-expanded']).toBe(true)
 s.workspaceId='another';await settle();expect(menu.props['aria-expanded']).toBe(false)
 menu.props.onClick();await nextTick()
 all(root).find(el=>el.tag==='button'&&text(el)==='对话').props.onClick();await nextTick();expect(menu.props['aria-expanded']).toBe(false)
})
it('releases mutation busy on view changes and fences old finalizers across repeated garden switches',async()=>{
  const deferred=[]
  const original=request.getMockImplementation()
  request.mockImplementation((path,options)=>options?.method==='POST'&&path.endsWith('/plots')?new Promise(resolve=>deferred.push({path,resolve})):original(path,options))
  const openPlot=async(name)=>{
    all(root).find(el=>el.tag==='button'&&text(el).includes('添加地块')).props.onClick();await nextTick()
    const modal=all(root).find(el=>String(el.props.class).split(' ').includes('agri-modal'))
    const input=all(modal).find(el=>el.tag==='input');input.props['onUpdate:modelValue'](name);await nextTick()
    const form=all(modal).find(el=>el.tag==='form')
    expect(all(modal).find(el=>el.tag==='button'&&text(el)==='保存记录').props.disabled).toBe(false)
    const pending=form.props.onSubmit({preventDefault(){}});await nextTick();return {pending}
  }
  const saveDisabled=()=>all(root).find(el=>el.tag==='button'&&['保存中…','保存记录'].includes(text(el)))?.props.disabled
  const first=await openPlot('A地块');expect(saveDisabled()).toBe(true)
  s.clearView();s.workspaceId='b';await settle()
  const second=await openPlot('B地块');expect(saveDisabled()).toBe(true)
  deferred[0].resolve({plot:{id:'a'}});await first.pending;await settle();expect(saveDisabled()).toBe(true)
  s.clearView();s.workspaceId='c';await settle()
  const third=await openPlot('C地块');expect(saveDisabled()).toBe(true)
  deferred[1].resolve({plot:{id:'b'}});await second.pending;await settle();expect(saveDisabled()).toBe(true)
  deferred[2].resolve({plot:{id:'c'}});await third.pending;await settle()
  await openPlot('C第二地块');expect(saveDisabled()).toBe(true)
  s.clearView();await settle();expect(saveDisabled()).toBe(false)
  deferred[3].resolve({plot:{id:'d'}});await settle();expect(saveDisabled()).toBe(false)
})

it('renders only currently available image IDs projected in historical messages, retaining the text',async()=>{
  s.messages=[{id:'historical-user',role:'user',content:'请核对这张照片',assetIds:['image','doc','revoked']}];await settle()
  let photos=all(root).filter(el=>el.tag==='img'&&el.props.class==='agri-message-photo')
  expect(photos.map(el=>el.props.src)).toEqual(['/api/v1/assets/image/content'])
  const original=request.getMockImplementation()
  request.mockImplementation((path,options)=>path.endsWith('/assets')?Promise.resolve({assets:[]}):original(path,options))
  await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle()
  photos=all(root).filter(el=>el.tag==='img'&&el.props.class==='agri-message-photo')
  expect(photos).toHaveLength(0);expect(text(root)).toContain('请核对这张照片')
})

it('releases mutation busy after a refresh changes the overview epoch',async()=>{
  let resolveWrite
  const original=request.getMockImplementation()
  request.mockImplementation((path,options)=>options?.method==='POST'&&path.endsWith('/plots')?new Promise(resolve=>resolveWrite=resolve):original(path,options))
  all(root).find(el=>el.tag==='button'&&text(el).includes('添加地块')).props.onClick();await nextTick()
  const modal=all(root).find(el=>String(el.props.class).split(' ').includes('agri-modal'))
  all(modal).find(el=>el.tag==='input').props['onUpdate:modelValue']('Epoch plot');await nextTick()
  const pending=all(modal).find(el=>el.tag==='form').props.onSubmit({preventDefault(){}});await nextTick()
  expect(all(modal).find(el=>el.tag==='button'&&text(el)==='保存中…').props.disabled).toBe(true)
  await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle()
  resolveWrite({plot:{id:'epoch'}});await pending;await settle()
  expect(text(root)).toContain('已保存')
  expect(all(root).find(el=>String(el.props.class).split(' ').includes('agri-modal'))).toBeUndefined()
})

it('retains upload receipt on unrelated refresh',async()=>{
 let resolveUpload;
 request.mockImplementation((path,opts)=>opts?.method==='POST' && path.endsWith('/assets') ? new Promise(resolve=>resolveUpload=resolve) : Promise.resolve(path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}));
 const input=all(root).find(el=>el.tag==='input' && el.props.type==='file');
 const upload=input.props.onChange({file:new Blob(['test']),target:{value:''}});await settle();
 s.turns=[{id:'other',status:'running'}];await settle();s.turns=[{id:'other',status:'completed'}];await settle();
 resolveUpload({asset:{id:'new',name:'new.txt'}});await upload;await settle();
 expect(text(root)).toContain('尚未加入本轮，也未发送给模型服务');

});

it.each([400,500])('retains write error %s after same-garden refresh',async(status)=>{
 let rejectWrite
 const original=request.getMockImplementation()
 request.mockImplementation((path,opts)=>opts?.method==='POST'&&path.endsWith('/plots')?new Promise((resolve,reject)=>rejectWrite=reject):original(path,opts))
 all(root).find(el=>el.tag==='button'&&text(el).includes('添加地块')).props.onClick();await nextTick()
 const modal=all(root).find(el=>String(el.props.class).split(' ').includes('agri-modal'))
 all(modal).find(el=>el.tag==='input').props['onUpdate:modelValue']('error plot');await nextTick()
 const pending=all(modal).find(el=>el.tag==='form').props.onSubmit({preventDefault(){}});await nextTick()
 await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle()
 rejectWrite(Object.assign(new Error('回执失败'),{status}));await pending;await settle()
 expect(text(root)).toContain('回执失败')
 if(status===500) expect(text(root)).toContain('核对')
})
it('mobile garden shortcuts reach all retained child pages and return without replacing composer',async()=>{
 s.prompt='园区草稿';s.submit=vi.fn()
 const composer=all(root).find(el=>el.props.class==='agri-composer')
 for(const name of ['监控','设备','报告']){
  const shortcut=all(root).find(el=>el.tag==='button'&&text(el)===name || el.tag==='button'&&text(el).endsWith(name)&&['监控','设备','报告'].includes(name))
  expect(shortcut).toBeTruthy();shortcut.props.onClick();await nextTick()
  const back=name==='报告'?all(root).find(el=>el.tag==='button'&&text(el)==='返回'):all(root).find(el=>el.props.class==='mobile-back');expect(back).toBeTruthy()
  const nav=all(root).find(el=>el.props['aria-label']==='手机工作台');expect(nav.children.filter(el=>el.tag==='button')[0].props.class).toContain('active')
  back.props.onClick();await nextTick();expect(s.prompt).toBe('园区草稿');expect(all(root).find(el=>el.props.class==='agri-composer')).toBe(composer)
 }
 expect(s.submit).not.toHaveBeenCalled()
})
it('mobile answer task opens a reviewable draft without writing and clears it on workspace switch',async()=>{
 s.messages=[{role:'assistant',content:'先检查叶背，再核对附近植株。'}];await settle()
 const previous=request.mock.calls.length
 all(root).find(el=>el.props.class==='mobile-answer-task').props.onClick();await nextTick()
 const modal=all(root).find(el=>String(el.props.class).split(' ').includes('agri-modal'))
 expect(text(modal)).toContain('新建待办')
 const inputs=all(modal).filter(el=>el.tag==='input')
 expect(inputs[0].value).toContain('现场检查')
 expect(all(modal).find(el=>el.props['aria-label']==='现场说明').value).toBe('先检查叶背，再核对附近植株。')
 expect(request.mock.calls.slice(previous).some(([,options])=>options?.method==='POST')).toBe(false)
 s.workspaceId='different';await settle()
 expect(all(root).some(el=>String(el.props.class).split(' ').includes('agri-modal'))).toBe(false)
 all(root).find(el=>el.tag==='button'&&text(el)==='待办任务').props.onClick();await nextTick();
 all(root).find(el=>el.tag==='button'&&el.props['aria-label']==='新建任务').props.onClick();await nextTick()
 const nextModal=all(root).find(el=>String(el.props.class).split(' ').includes('agri-modal'))
 expect(all(nextModal).filter(el=>el.tag==='input').slice(0,2).every(el=>el.value==='')).toBe(true)
})

it('opens a real new task form from the mobile conversation action without changing the draft or sending', async()=>{
 s.submit=vi.fn();s.prompt='保留我的现场问题';await nextTick();
 all(root).find(el=>el.props['aria-label']==='照片与更多').props.onClick();await nextTick();
 all(root).find(el=>el.tag==='button'&&text(el)==='待办').props.onClick();await nextTick();
 expect(text(root)).toContain('新建待办');
 expect(all(root).some(el=>el.tag==='form'&&all(el).some(child=>child.tag==='button'&&text(child)==='保存记录'))).toBe(true);
 expect(s.prompt).toBe('保留我的现场问题');expect(s.submit).not.toHaveBeenCalled();
})
it('garden task card opens only its concrete task and returns to the list',async()=>{
 const original=request.getMockImplementation();request.mockImplementation((path,options)=>path.endsWith('/agriculture')?Promise.resolve({devices:[],plots:[],reports:[],workItems:[{id:'first',title:'核对叶背',status:'open',description:'第一项事实'},{id:'second',title:'核对土壤',status:'open',description:'第二项事实'}]}):original(path,options));
 await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle();
 all(root).find(el=>el.tag==='button'&&text(el)==='待办任务').props.onClick();await nextTick();all(root).find(el=>el.props['aria-label']==='搜索任务').props['onUpdate:modelValue']('不存在的任务');await nextTick();all(root).find(el=>el.tag==='button'&&text(el)==='园区').props.onClick();await nextTick();const card=all(root).find(el=>el.tag==='button'&&text(el)==='去看看　 →');expect(card).toBeTruthy();card.props.onClick();await nextTick();expect(text(root)).not.toContain('没有匹配的任务');
 const flow=all(root).find(el=>el.props.class==='mobile-task-flow');expect(text(flow)).toContain('第一项事实');expect(text(flow)).not.toContain('第二项事实');const cards=all(root).filter(el=>String(el.props.class).includes('task-card')&&el.tag==='article');expect(cards).toHaveLength(1);expect(text(cards[0])).toContain('核对叶背');expect(all(root).some(el=>el.props.class==='task-stats')).toBe(false);expect(all(root).some(el=>el.props.class==='task-reports')).toBe(false);expect(all(root).some(el=>el.props.class==='mobile-back')).toBe(false);expect(all(root).some(el=>el.props['aria-label']==='搜索任务')).toBe(false);
 all(root).find(el=>el.tag==='button'&&text(el)==='‹ 返回待办').props.onClick();await nextTick();all(root).find(el=>el.props['aria-label']==='搜索任务').props['onUpdate:modelValue']('');await nextTick();expect(all(root).filter(el=>String(el.props.class).includes('task-card')&&el.tag==='article')).toHaveLength(2);
})
it('task completion does not inherit selected conversation files and retains note after failure',async()=>{
 const original=request.getMockImplementation();request.mockImplementation((path,options)=>path.endsWith('/agriculture')?Promise.resolve({devices:[],plots:[],reports:[],workItems:[{id:'first',title:'核对叶背',status:'open'}]}):path.endsWith('/complete')?Promise.reject(Object.assign(new Error('保存失败'),{status:400})):original(path,options));
 await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle();
 all(root).find(el=>el.tag==='button'&&text(el)==='去看看　 →').props.onClick();await nextTick();
 all(root).find(el=>el.tag==='button'&&['标记完成并记录','我已检查，写记录'].includes(text(el))).props.onClick();await nextTick();
 const modal=all(root).find(el=>String(el.props.class).split(' ').includes('agri-modal'));const note=all(modal).find(el=>el.tag==='textarea');note.props['onUpdate:modelValue']('已查看叶背，等待复核');await nextTick();
 const checkbox=all(modal).find(el=>el.tag==='input'&&el.props.type==='checkbox');expect(checkbox.props.checked).toBe(false);checkbox.props.onChange();await nextTick();
 await all(modal).find(el=>el.tag==='form').props.onSubmit({preventDefault(){}});await settle();
 const body=request.mock.calls.find(([path])=>path.endsWith('/complete'))[1].body;expect(body.assetIds).toEqual(['image']);expect(body.note).toBe('已查看叶背，等待复核');expect(all(root).some(el=>el.tag==='textarea'&&el.props['aria-label']==='实际处理与现场结果')).toBe(true);await all(modal).find(el=>el.tag==='form').props.onSubmit({preventDefault(){}});expect(request.mock.calls.filter(([path])=>path.endsWith('/complete')).at(-1)[1].body.note).toBe('已查看叶背，等待复核');
})
it('explicit photo processing displays failure and then a real result can be drafted without sending',async()=>{
 s.threadId='thread';s.submit=vi.fn();await settle();const original=request.getMockImplementation();request.mockImplementation((path,options)=>path.endsWith('/analyze')?Promise.resolve({turn:{id:'photo-turn',status:'queued',processingKind:'image_analysis'}}):original(path,options));
 all(root).find(el=>el.tag==='button'&&text(el)==='对话').props.onClick();await nextTick();await all(root).find(el=>el.tag==='button'&&text(el)==='分析照片').props.onClick();await settle();
 s.turns=[{id:'photo-turn',status:'failed',processingKind:'image_analysis',error:{message:'图片模型未配置'}}];await nextTick();expect(text(root)).toContain('图片模型未配置');expect(s.submit).not.toHaveBeenCalled();
 s.prompt='保留的问题';s.turns=[{id:'photo-turn',status:'completed',processingKind:'image_analysis'}];s.artifact={id:'artifact-photo',turnId:'photo-turn',body:'可见斑点，需现场复核'};await nextTick();
 all(root).find(el=>el.tag==='button'&&text(el)==='结合这张继续问').props.onClick();await nextTick();expect(s.prompt).toContain('保留的问题');expect(s.prompt).toContain('可见斑点，需现场复核');expect(text(root)).toContain('已选 1 份资料');expect(s.submit).not.toHaveBeenCalled();
 s.threadId='another';await nextTick();expect(all(root).some(el=>el.props.class==='mobile-media-result')).toBe(false);
})
it('reader ask closes the original, selects only current knowledge and preserves an existing draft',async()=>{
 const item={id:'current',title:'当前文章',assetId:'asset-current',excerpts:[]};const original=request.getMockImplementation();request.mockImplementation((path,options)=>path.endsWith('/knowledge')?Promise.resolve({knowledge:[item]}):path==='/knowledge/current'?Promise.resolve({knowledge:item}):original(path,options));vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,text:async()=>'当前原文'})));
 await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle();s.prompt='原有待问问题';s.submit=vi.fn();
 all(root).find(el=>el.tag==='button'&&text(el)==='学习知识库').props.onClick();await nextTick();await all(root).find(el=>el.tag==='button'&&text(el)==='阅读原文').props.onClick();await settle();
 all(root).find(el=>el.tag==='button'&&text(el)==='问问这篇').props.onClick();await nextTick();expect(all(root).some(el=>el.props.class==='reader-toolbar')).toBe(false);expect(text(root)).toContain('已选 0 份资料 · 1 条知识');expect(s.prompt).toBe('原有待问问题');expect(s.submit).not.toHaveBeenCalled();
})
it('report Markdown export downloads a blob and suppresses a late download after garden switch',async()=>{
 const original=request.getMockImplementation();request.mockImplementation((path,options)=>path.endsWith('/agriculture')?Promise.resolve({devices:[],plots:[],workItems:[],reports:[{id:'report',title:'事实报告'}]}):path.endsWith('/exports')?Promise.resolve({asset:{id:'markdown'}}):original(path,options));
 const click=vi.fn(),create=vi.fn(()=> 'blob:report'),revoke=vi.fn();document.createElement=vi.fn(()=>({click}));vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:create,revokeObjectURL:revoke}));vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,blob:async()=>new Blob(['# 报告'],{type:'text/markdown'})})));
 await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle();all(root).find(el=>el.tag==='button'&&text(el)==='待办任务').props.onClick();await nextTick();
 await all(root).find(el=>el.tag==='button'&&text(el)==='导出 Markdown').props.onClick();expect(fetch).toHaveBeenCalledWith('/api/v1/assets/markdown/content',{credentials:'same-origin'});expect(document.createElement.mock.results[0].value.download).toBe('事实报告.md');expect(click).toHaveBeenCalledOnce();
 let finish;fetch.mockImplementation(async()=>({ok:true,blob:()=>new Promise(resolve=>finish=resolve)}));const pending=all(root).find(el=>el.tag==='button'&&text(el)==='导出 Markdown').props.onClick();await settle();s.workspaceId='another';await settle();finish(new Blob(['old']));await pending;expect(click).toHaveBeenCalledOnce();
})

it('shows a Markdown export failure inside the still open report',async()=>{
 const item={id:'report',title:'事实报告',body:'已核验事实'};const original=request.getMockImplementation();request.mockImplementation((path,options)=>path.endsWith('/agriculture')?Promise.resolve({devices:[],plots:[],workItems:[],reports:[item]}):path==='/reports/report'?Promise.resolve({report:item}):path.endsWith('/exports')?Promise.reject(Object.assign(new Error('来源已撤销'),{status:409})):original(path,options));
 await all(root).find(el=>el.tag==='button'&&text(el)==='刷新').props.onClick();await settle();all(root).find(el=>el.tag==='button'&&text(el)==='待办任务').props.onClick();await nextTick();await all(root).find(el=>el.tag==='button'&&text(el)==='查看').props.onClick();await settle();
 const layer=all(root).find(el=>el.props.class==='report-document-layer');expect(layer).toBeTruthy();await all(layer).find(el=>el.tag==='button'&&text(el)==='导出 Markdown').props.onClick();await nextTick();await all(layer).find(el=>el.tag==='button'&&text(el)==='保存到设备').props.onClick();await settle();const stillOpen=all(root).find(el=>el.props.class==='report-document-layer');expect(stillOpen).toBeTruthy();expect(all(stillOpen).some(el=>el.props.role==='alert'&&text(el).includes('来源已撤销'))).toBe(true);
})

it('independent report scope rejects empty and stale cross-plot IDs even when handler is invoked directly',async()=>{
 const original=request.getMockImplementation();request.mockImplementation((path,options)=>path.endsWith('/agriculture')?Promise.resolve({plots:[{id:'a',name:'甲'},{id:'b',name:'乙'}],workItems:[{id:'ta',plotId:'a',title:'甲任务',status:'open'},{id:'tb',plotId:'b',title:'乙任务',status:'open'}],devices:[],reports:[]}):original(path,options));
 await all(root).find(n=>n.tag==='button'&&text(n)==='刷新').props.onClick();await settle();all(root).find(n=>n.tag==='button'&&text(n)==='待办任务').props.onClick();await nextTick();all(root).find(n=>n.tag==='button'&&text(n)==='生成园区报告').props.onClick();await nextTick();
 const scope=all(root).find(n=>n.props['aria-label']==='选择报告范围'),checks=all(scope).filter(n=>n.tag==='input');checks[0].props['onUpdate:modelValue']([]);await nextTick();let generate=all(scope).find(n=>n.tag==='button'&&text(n).startsWith('生成简报'));expect(generate.props.disabled).toBe(true);await generate.props.onClick();expect(request.mock.calls.some(([p,o])=>p.endsWith('/reports')&&o?.method==='POST')).toBe(false);
 checks[0].props['onUpdate:modelValue'](['ta']);await nextTick();all(root).find(n=>n.props['aria-label']==='选择地块').props['onUpdate:modelValue']('b');await nextTick();generate=all(scope).find(n=>n.tag==='button'&&text(n).startsWith('生成简报'));expect(generate.props.disabled).toBe(true);checks[0].props['onUpdate:modelValue'](['ta']);await generate.props.onClick();expect(request.mock.calls.some(([p,o])=>p.endsWith('/reports')&&o?.method==='POST')).toBe(false);
})
it('independent mounted mobile task filter shows completed only and restores open only',async()=>{
 const r=node('root'),a=renderer.createApp(MobileTaskFlow,{tasks:[{id:'o',title:'独立待处理',status:'open'},{id:'c',title:'独立已完成',status:'completed'}],plots:[],records:[]});a.mount(r);await nextTick();expect(text(r)).toContain('独立待处理');expect(text(r)).not.toContain('独立已完成');all(r).find(n=>n.tag==='button'&&text(n).startsWith('已完成')).props.onClick();await nextTick();expect(text(r)).not.toContain('独立待处理');expect(text(r)).toContain('独立已完成');all(r).find(n=>n.tag==='button'&&text(n).startsWith('待处理')).props.onClick();await nextTick();expect(text(r)).toContain('独立待处理');expect(text(r)).not.toContain('独立已完成');a.unmount()
})
it('independent late report creation cannot reopen a prior workspace report',async()=>{
 let resolve;const original=request.getMockImplementation();request.mockImplementation((path,options)=>path.endsWith('/agriculture')?Promise.resolve({plots:[],workItems:[{id:'ta',title:'旧任务',status:'open'}],devices:[],reports:[]}):path.endsWith('/reports')&&options?.method==='POST'?new Promise(r=>resolve=r):original(path,options));
 await all(root).find(n=>n.tag==='button'&&text(n)==='刷新').props.onClick();await settle();all(root).find(n=>n.tag==='button'&&text(n)==='待办任务').props.onClick();await nextTick();all(root).find(n=>n.tag==='button'&&text(n)==='生成园区报告').props.onClick();await nextTick();const pending=all(root).find(n=>n.tag==='button'&&text(n).startsWith('生成简报 ·')).props.onClick();await settle();s.workspaceId='new-workspace';await settle();resolve({report:{id:'old-report',title:'旧园区秘密报告'}});await pending;await settle();expect(text(root)).not.toContain('旧园区秘密报告');expect(request.mock.calls.some(([p])=>p==='/reports/old-report')).toBe(false);expect(all(root).some(n=>n.props['aria-label']==='选择报告范围')).toBe(false)
})
it('independent onboarding save failure and cancellation never show ready success',async()=>{
 s.createWorkspace=vi.fn(async()=>false);all(root).find(n=>n.tag==='button'&&text(n)==='＋ 新建园区').props.onClick();await nextTick();let modal=all(root).find(n=>String(n.props.class).split(' ').includes('agri-modal'));all(modal).find(n=>n.tag==='input').props['onUpdate:modelValue']('合成园区');await nextTick();await all(modal).find(n=>n.tag==='form').props.onSubmit({preventDefault(){}});await settle();expect(s.createWorkspace).toHaveBeenCalledWith('合成园区');expect(text(root)).not.toContain('园区准备好了');all(modal).find(n=>n.props.class==='agri-close').props.onClick();await nextTick();expect(text(root)).not.toContain('园区准备好了');expect(all(root).some(n=>String(n.props.class).split(' ').includes('agri-modal'))).toBe(false)
})
it('independent reader excerpt reaches parent draft without send and learning closes reader for real form',async()=>{
 const item={id:'excerpt-current',title:'选段文章',assetId:'excerpt-asset'},original=request.getMockImplementation();request.mockImplementation((path,options)=>path.endsWith('/knowledge')?Promise.resolve({knowledge:[item]}):path==='/knowledge/excerpt-current'?Promise.resolve({knowledge:item}):original(path,options));vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,text:async()=>'当前选段原文'})));
 await all(root).find(n=>n.tag==='button'&&text(n)==='刷新').props.onClick();await settle();s.prompt='保留我的草稿';s.submit=vi.fn();all(root).find(n=>n.tag==='button'&&text(n)==='学习知识库').props.onClick();await nextTick();const open=()=>all(root).find(n=>n.tag==='button'&&text(n)==='阅读原文').props.onClick();await open();await settle();const article=all(root).find(n=>n.props.class==='reader-article'),inside=article.children.at(-1),layer=all(root).find(n=>n.props['aria-label']==='知识阅读器');vi.stubGlobal('window',{addEventListener(){},removeEventListener(){},getSelection:()=>({rangeCount:1,anchorNode:inside,focusNode:inside,toString:()=>'当前选段原文'})});layer.props.onMouseup({target:inside});await nextTick();const before=request.mock.calls.length;all(root).find(n=>n.tag==='button'&&text(n)==='问问这段').props.onClick();await nextTick();expect(s.prompt).toContain('保留我的草稿');expect(s.prompt).toContain('当前选段原文');expect(text(root)).toContain('已选 0 份资料 · 1 条知识');expect(s.submit).not.toHaveBeenCalled();expect(request.mock.calls.slice(before).some(([,o])=>o?.method==='POST')).toBe(false);
 all(root).find(n=>n.tag==='button'&&text(n)==='学习知识库').props.onClick();await nextTick();await open();await settle();all(root).find(n=>n.tag==='button'&&text(n)==='更多 ···').props.onClick();await nextTick();all(root).find(n=>n.tag==='button'&&text(n)==='写下这次学到的').props.onClick();await nextTick();expect(all(root).some(n=>n.props['aria-label']==='知识阅读器')).toBe(false);expect(all(root).some(n=>n.tag==='form'&&all(n).some(x=>x.tag==='button'&&text(x)==='保存学习记录'))).toBe(true);const learningForm=all(root).find(n=>n.tag==='form'&&all(n).some(x=>x.tag==='button'&&text(x)==='保存学习记录'));const fields=all(learningForm).filter(n=>n.tag==='textarea');fields[0].props['onUpdate:modelValue']('独立理解');fields[1].props['onUpdate:modelValue']('独立疑问');await nextTick();const calls=request.mock.calls.length;all(learningForm).find(n=>n.props.class==='learning-continue').props.onClick();await nextTick();expect(s.prompt).toContain('保留我的草稿');expect(s.prompt).toContain('独立理解');expect(s.prompt).toContain('独立疑问');expect(s.submit).not.toHaveBeenCalled();expect(request.mock.calls.slice(calls).some(([,o])=>o?.method==='POST')).toBe(false);expect(all(root).some(n=>n.tag==='form'&&all(n).some(x=>x.props.class==='learning-continue'))).toBe(false)
})
it('independent report success followed by pending refresh cannot open a report after workspace switch',async()=>{
 let releaseRefresh,created=false;const original=request.getMockImplementation();request.mockImplementation((path,options)=>{
  if(path.endsWith('/reports')&&options?.method==='POST'){created=true;return Promise.resolve({report:{id:'prior-report',title:'旧园区报告'}})}
  if(path==='/workspaces/w/agriculture'&&created)return new Promise(resolve=>releaseRefresh=resolve)
  if(path.endsWith('/agriculture'))return Promise.resolve({plots:[],workItems:[{id:'t',title:'合成任务',status:'open'}],devices:[],reports:path.includes('new-workspace')?[{id:'new-report',title:'新园区报告'}]:[]})
  return original(path,options)
 });
 await all(root).find(n=>n.tag==='button'&&text(n)==='刷新').props.onClick();await settle();all(root).find(n=>n.tag==='button'&&text(n)==='待办任务').props.onClick();await nextTick();all(root).find(n=>n.tag==='button'&&text(n)==='生成园区报告').props.onClick();await nextTick();const pending=all(root).find(n=>n.tag==='button'&&text(n).startsWith('生成简报 ·')).props.onClick();await settle();expect(releaseRefresh).toBeTypeOf('function');s.workspaceId='new-workspace';await settle();const boundary=request.mock.calls.length;releaseRefresh({plots:[],workItems:[],devices:[],reports:[{id:'prior-report'}]});await pending;await settle();expect(request.mock.calls.slice(boundary).some(([p])=>p==='/reports/prior-report'||p==='/reports/new-report')).toBe(false);expect(all(root).some(n=>n.props.class==='report-document-layer')).toBe(false)
})
it('independent capture addition drops its late receipt after thread switch',async()=>{
 app.unmount();let pending=false,release;const live={...demoProjection(),captures:[{id:'capture',assetId:'captured',observedAt:1}]};request.mockImplementation(path=>{
 if(path.includes('/live-demo'))return Promise.resolve({liveDemo:live});if(path.endsWith('/agriculture')&&pending)return new Promise(r=>release=r);return Promise.resolve(path.endsWith('/assets')?{assets:[{id:'captured',kind:'image',name:'合成抓拍',status:'stored'}]}:path.endsWith('/knowledge')?{knowledge:[]}:{plots:[],devices:[],workItems:[],reports:[]})
 });s.threadId='capture-thread';app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.config.errorHandler=e=>vueErrors.push(e);app.mount(root);await settle();pending=true;const action=all(root).find(n=>n.tag==='button'&&text(n)==='加入本轮对话').props.onClick();await settle();expect(release).toBeTypeOf('function');s.threadId='different-thread';await nextTick();release({plots:[],devices:[],workItems:[],reports:[]});await action;await settle();expect(text(root)).not.toContain('抓拍已加入本轮，可先分析照片或补充描述');expect(all(root).some(n=>n.props.class==='mobile-upload-receipt')).toBe(false)
})
it('independent report next-step context is temporary across cancel, thread and workspace changes',async()=>{
 const item={id:'context-report',title:'独立来源报告',document:{schemaVersion:'agriculture.report.v1',generatedAt:1,period:{from:1,to:2},summary:{taskCount:1,completedTaskCount:0,recordCount:0},photos:[],observations:[],tasks:[{id:'t',title:'独立后续任务',description:'独立现场说明',status:'open'}],limitations:[]}},original=request.getMockImplementation();request.mockImplementation((p,o)=>p.endsWith('/agriculture')?Promise.resolve({plots:[],devices:[],workItems:[],reports:[item]}):p==='/reports/context-report'?Promise.resolve({report:item}):original(p,o));await all(root).find(n=>n.tag==='button'&&text(n)==='刷新').props.onClick();await settle();all(root).find(n=>n.tag==='button'&&text(n)==='待办任务').props.onClick();await nextTick();
 const enter=async()=>{await all(root).find(n=>n.tag==='button'&&text(n)==='查看').props.onClick();await settle();all(root).find(n=>n.tag==='button'&&text(n)==='核对并安排下一步').props.onClick();await nextTick();expect(text(root)).toContain('独立来源报告');expect(all(root).some(n=>n.tag==='button'&&text(n)==='确认并创建待办')).toBe(true)};
 await enter();all(root).find(n=>n.props.class==='agri-close').props.onClick();await nextTick();expect(all(root).some(n=>n.tag==='button'&&text(n)==='确认并创建待办')).toBe(false);await enter();s.threadId='context-other-thread';await nextTick();expect(all(root).some(n=>n.tag==='button'&&text(n)==='确认并创建待办')).toBe(false);all(root).find(n=>n.props.class==='agri-close').props.onClick();await nextTick();await enter();s.workspaceId='context-other-workspace';await settle();expect(all(root).some(n=>n.tag==='button'&&text(n)==='确认并创建待办')).toBe(false)
})
