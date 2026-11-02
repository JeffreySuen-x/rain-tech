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
const safeComponentBindings = values => new Proxy(values, {get(target,key){ if(key in target)return target[key]; if(typeof key==='string' && key.endsWith('.vue'))return {default:{render:()=>null}}; throw new Error(`Missing test module binding: ${String(key)}`)}})
const AgricultureWorkbench = new Function('bindings', compiled.replace('export default', 'return'))(safeComponentBindings({vue, './MobileGarden.vue':{default:MobileGarden}, './FriendlyIcon.vue':{default:{render:()=>null}}, './ReportDocument.vue':{default:{render:()=>null}}, './VoiceRecorder.vue':{default:{render:()=>null}}, './useLocalSpeech.js':{useLocalSpeech}, './KnowledgeReader.vue':{default:KnowledgeReader}, './KnowledgeLibrary.vue':{default:KnowledgeLibrary}, './library.js':library,'./mobile-learning.js':mobileLearning, './LiveFieldPanel.vue':{default:LiveFieldPanel}, './useLiveDemo.js':{useLiveDemo}, '../BrandMark.js':{default:BrandMark}, '../store.js':{useWorkspace,statusNames:{queued:'等待执行',running:'正在思考'}}, '../api.js':{request}, './api.js':agricultureApi, './presentation.js':presentation, './calendarPresentation.js':calendarPresentation}))

const node = (tag, text = '') => ({tag,tagName:tag.toUpperCase(),text,style:{},props:{},children:[],parent:null,addEventListener(){},removeEventListener(){},querySelector(){return null},focus(){},getRootNode(){return globalThis.document},get options(){return this.children.filter(child=>child.tag==='option')},value:'',multiple:false})
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
let app, s, root
beforeEach(async()=>{
  vi.stubGlobal('Document',class Document {});vi.stubGlobal('ShadowRoot',class ShadowRoot {});vi.stubGlobal('document',{addEventListener:vi.fn(),removeEventListener:vi.fn(),activeElement:null})
  const pinia=createPinia();setActivePinia(pinia);s=useWorkspace();s.user={id:'owner'};s.workspaceId='w';s.workspaces=[{id:'w',name:'园区'}]
  request.mockImplementation(path=>Promise.resolve(path.endsWith('/assets')?{assets:[{id:'doc',name:'巡查.md',kind:'document',status:'ready'},{id:'image',name:'叶片.png',kind:'image',status:'stored'},{id:'audio',name:'录音.wav',kind:'audio',status:'stored'}]}:path.endsWith('/knowledge')?{knowledge:[]}:{devices:[],plots:[],workItems:[],reports:[]}))
  app=renderer.createApp(h(AgricultureWorkbench));app.use(pinia);root=node('root');app.mount(root);await Promise.resolve();await Promise.resolve();await nextTick()
})
afterEach(()=>{app?.unmount();vi.restoreAllMocks();vi.unstubAllGlobals()})
const settle=async()=>{for(let i=0;i<8;i++)await Promise.resolve();await nextTick()}
for(const stale of [false,true])it(`independent explicit starter listening ${stale?'discards cross-scope late bytes':'reads authorized bytes only'} without reference or model send`,async()=>{
 app.unmount();let resolve;const speak=vi.fn();vi.stubGlobal('speechSynthesis',{cancel:vi.fn(),getVoices:()=>[{lang:'zh-CN',localService:true}],speak});vi.stubGlobal('SpeechSynthesisUtterance',function(t){this.text=t})
 const item={id:'leaf',title:'叶片异常观察',assetId:'original',library:{articleId:'MON-032',memberships:[]}};
 request.mockImplementation(path=>Promise.resolve(path==='/knowledge/leaf'?{knowledge:item}:path.endsWith('/assets')?{assets:[]}:path.endsWith('/knowledge')?{knowledge:[item]}:{devices:[],plots:[],workItems:[],reports:[]}));vi.stubGlobal('fetch',vi.fn(()=>new Promise(r=>resolve=r)))
 app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.mount(root);await settle();all(root).find(n=>n.tag==='button'&&text(n)==='学习知识库').props.onClick();await settle();expect(speak).not.toHaveBeenCalled();const listen=all(root).find(n=>n.tag==='button'&&text(n).includes('听讲'));expect(listen).toBeTruthy();listen.props.onClick();await settle();expect(speak).not.toHaveBeenCalled();if(stale){s.workspaceId='other';await settle()}resolve({ok:true,text:async()=> '已授权原文。'});await settle();expect(speak).toHaveBeenCalledTimes(stale?0:1);if(!stale)expect(speak.mock.calls[0][0].text).toBe('已授权原文。');expect(request.mock.calls.some(([,o])=>o?.method==='POST')).toBe(false);expect(text(root)).not.toContain('已选 1 条引用')
})
it('independent starter cards absent when no existing title or id matches',async()=>{app.unmount();request.mockImplementation(path=>Promise.resolve(path.endsWith('/knowledge')?{knowledge:[{id:'unrelated',title:'灌溉基础',library:{articleId:'MON-090',memberships:[]}}]}:path.endsWith('/assets')?{assets:[]}:{devices:[],plots:[],workItems:[],reports:[]}));app=renderer.createApp(h(AgricultureWorkbench));app.use(s._p);root=node('root');app.mount(root);await settle();all(root).find(n=>n.tag==='button'&&text(n)==='学习知识库').props.onClick();await settle();expect(all(root).some(n=>n.tag==='button'&&text(n).includes('听讲'))).toBe(false);expect(text(root)).toContain('灌溉基础')})
it('independent report display formats units and limits without mutating snapshot',async()=>{app.unmount();let c=compileScript(parse(readFileSync(new URL('../src/agriculture/ReportDocument.vue',import.meta.url),'utf8')).descriptor,{id:'independent-report',inlineTemplate:true}).content.replace(/^import\s+\{([^}]+)\}\s+from\s+['"]([^'"]+)['"];?/gm,(_,names,module)=>`const {${names.replace(/\bas\b/g,':')}}=bindings[${JSON.stringify(module)}];`);const Report=new Function('bindings',c.replace('export default','return'))({vue,'./useLocalSpeech.js':{useLocalSpeech},'./presentation.js':presentation, './calendarPresentation.js':calendarPresentation});const report={id:'frozen',title:'独立报告',body:'原文',document:{schemaVersion:'agriculture.report.v1',generatedAt:1792972800,timezone:'Asia/Shanghai',period:{from:1792368000,to:1792972800},summary:{taskCount:0,completedTaskCount:0,recordCount:0},tasks:[],photos:[],sources:[],observations:[{id:'o',deviceId:'DEVICE-RAW',metric:'humidity',unit:'percent',value:61,source:'test',observedAt:1792972800}],limitations:['实际覆盖时间：1792368000 至 1792972800 Unix秒。','其余原始限制不改']}};const before=JSON.stringify(report);const freeze=o=>{Object.values(o).forEach(v=>{if(v&&typeof v==='object')freeze(v)});Object.freeze(o)};freeze(report);app=renderer.createApp(h(Report,{report}));root=node('root');app.mount(root);await nextTick();expect(text(root)).toContain('空气湿度 · %');expect(text(root)).toContain('DEVICE-RAW');expect(text(root)).toContain('61 percent');expect(text(root)).toContain('其余原始限制不改');expect(text(root)).not.toContain('实际覆盖时间：1792368000');expect(JSON.stringify(report)).toBe(before)})
it('independent real SFC uses actual track ids and exact starter identities; same-title wrong IDs never qualify',async()=>{app.unmount();const ids=['MON-032','EDU-004','EDU-001','EDU-023'];const items=ids.map((id,i)=>({id:'real-'+id,title:'原始完整标题'+id,library:{articleId:id,memberships:[{trackId:i?'agricultural_skill_learning':'monitoring',trackTitle:'完整轨道题',groupId:'g',groupTitle:'组',order:i}]}}));items.push({id:'fake',title:'夜间结露怎么看？',library:{articleId:'MON-999',memberships:[]}});const events=[];app=renderer.createApp(h(KnowledgeLibrary,{items,onRead:x=>events.push(x)}));root=node('root');app.mount(root);await nextTick();expect(text(root)).toContain('看懂作物');expect(text(root)).toContain('学会农活');const starters=all(root).find(n=>n.props.class==='library-starters');const reads=all(starters).filter(n=>n.tag==='button'&&n.props['aria-label']==='阅读原文');expect(reads).toHaveLength(4);for(const b of reads)b.props.onClick();expect(events.map(x=>x.library.articleId)).toEqual(ids);expect(events.map(x=>x.title)).toEqual(items.slice(0,4).map(x=>x.title));expect(text(starters)).not.toContain('MON-999');const main=all(root).find(n=>n.props.class==='library-tracks library-main-tracks');const monitor=all(main).find(n=>n.tag==='button'&&text(n).includes('看懂作物'));monitor.props.onClick();await nextTick();expect(text(root)).toContain('MON-032');expect(text(all(root).find(n=>n.props.class==='knowledge-grid'))).not.toContain('EDU-023')})
