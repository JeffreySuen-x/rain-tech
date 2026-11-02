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

const node = (tag, text = '') => vue.markRaw({tag,tagName:tag.toUpperCase(),text,style:{},props:{},children:[],parent:null,addEventListener(){},removeEventListener(){},querySelector(selector){return all(this).find(n=>n.props.class===selector.slice(1))},contains(other){return this===other||this.children.some(n=>n.contains(other))},closest(){return null},focus(){},getRootNode(){return globalThis.document},get parentElement(){return this.parent},classList:{contains(){return false}},querySelector(){return null},get options(){return this.children.filter(child=>child.tag==='option')},value:'',multiple:false})
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

it('independent reader renders one native H1 and direct controls, disables failed document actions',async()=>{
 app.unmount();const item={id:'qa',title:'Fallback title'};app=renderer.createApp(h(KnowledgeReader,{item,text:'# Native heading\n\nTAIL_UNIQUE'}));root=node('root');app.mount(root);await nextTick();
 expect(all(root).filter(n=>n.tag==='h1')).toHaveLength(1);expect(text(root).split('TAIL_UNIQUE')).toHaveLength(2);expect(all(root).some(n=>n.tag==='button'&&text(n)==='目录')).toBe(true);expect(all(root).some(n=>n.props['aria-label']==='阅读字号与行距')).toBe(true);expect(text(root)).not.toContain('完整原文');
 app.unmount();app=renderer.createApp(h(KnowledgeReader,{item,text:'plain body',error:'denied'}));root=node('root');app.mount(root);await nextTick();expect(text(root)).toContain('denied');expect(all(root).find(n=>n.tag==='button'&&text(n)==='问问这篇').props.disabled).toBe(true)
})
it('independent drawer late history failure cannot contaminate a different workspace',async()=>{
 s.threads=[{id:'history',title:'QA history',workspaceId:'w'}];let reject;s.selectThread=vi.fn(()=>new Promise((_,r)=>reject=r));await nextTick();
 const trigger=all(root).find(n=>n.props['aria-controls']==='garden-menu');expect(trigger).toBeTruthy();trigger.props.onClick();await nextTick();await nextTick();const history=all(root).find(n=>n.tag==='button'&&text(n)==='QA history');expect(history).toBeTruthy();const pending=history.props.onClick();s.workspaceId='other';await nextTick();reject(new Error('OLD_ERROR_SENTINEL'));await pending;await nextTick();expect(text(root)).not.toContain('OLD_ERROR_SENTINEL');expect(s.selectThread).toHaveBeenCalledWith('history')
})
it('independent drawer open and local search produce zero API or store selection requests',async()=>{
 for(let i=0;i<12;i++)await Promise.resolve();await nextTick();s.threads=[{id:'qa-leaf',title:'叶片检查',workspaceId:'w'},{id:'qa-water',title:'浇水记录',workspaceId:'w'}];s.selectThread=vi.fn();await nextTick();const boundary=request.mock.calls.length;
 all(root).find(n=>n.props['aria-controls']==='garden-menu').props.onClick();await nextTick();await nextTick();const search=all(root).find(n=>n.props['aria-label']==='搜索历史对话');search.props['onUpdate:modelValue']('叶片');await nextTick();const list=all(root).find(n=>n.props.class==='drawer-history');expect(text(list)).toContain('叶片检查');expect(text(list)).not.toContain('浇水记录');search.props['onUpdate:modelValue']('不存在');await nextTick();expect(text(list)).toContain('没有找到相关对话');expect(request.mock.calls.length).toBe(boundary);expect(s.selectThread).not.toHaveBeenCalled()
})
