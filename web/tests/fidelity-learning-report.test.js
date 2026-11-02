import { expect, it, vi } from 'vitest'
import * as vue from 'vue'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import * as markdown from '../src/agriculture/reader-markdown.js'
import * as mobileLearning from '../src/agriculture/mobile-learning.js'
import * as presentation from '../src/agriculture/presentation.js'
const node=(tag,text='')=>vue.markRaw({tag,text,children:[],props:{},parent:null,contains(other){return this===other||this.children.some(n=>n.contains(other))},querySelector(selector){return all(this).find(n=>n.props.class===selector.slice(1))},closest(){return null}})
const all=n=>[n,...n.children.flatMap(all)],text=n=>n.text+n.children.map(text).join('')
const renderer=vue.createRenderer({createElement:tag=>node(tag),createText:t=>node('#text',t),createComment:t=>node('#comment',t),insert(c,p,a){if(c.parent)this.remove(c);const i=p.children.indexOf(a);i<0?p.children.push(c):p.children.splice(i,0,c);c.parent=p},remove(c){if(c.parent)c.parent.children.splice(c.parent.children.indexOf(c),1)},setText(n,t){n.text=t},setElementText(n,t){n.text=t;n.children=[]},parentNode:n=>n.parent,nextSibling:n=>n.parent?.children[n.parent.children.indexOf(n)+1],patchProp(n,k,o,v){n.props[k]=v}})
function component(name,bindings){let code=compileScript(parse(readFileSync(new URL(`../src/agriculture/${name}.vue`,import.meta.url),'utf8')).descriptor,{id:name,inlineTemplate:true}).content.replace(/^import\s+['"][^'"]+['"];?\s*$/gm,'').replace(/^import\s+\{([^}]+)\}\s+from\s+['"]([^'"]+)['"];?/gm,(_,n,m)=>`const {${n.replace(/\bas\b/g,':')}}=bindings[${JSON.stringify(m)}];`).replace(/^import\s+(\w+)\s+from\s+['"]([^'"]+)['"];?/gm,(_,n,m)=>`const ${n}=bindings[${JSON.stringify(m)}].default;`);return new Function('bindings',code.replace('export default','return'))({vue:{...vue,withDirectives:v=>v},...bindings})}
const button=(root,label)=>all(root).find(n=>n.tag==='button'&&text(n)===label)
it('mounted reader selects only its real article subtree and never auto sends; revoke clears excerpt',async()=>{
 const Reader=component('KnowledgeReader',{'./mobile-learning.js':mobileLearning,'./reader-markdown.js':markdown,'./ReaderContent.js':{default:{render:()=>vue.h('p','原文段落')}}}),events=[],item={id:'one',title:'资料'}
 const root=node('root'),app=renderer.createApp(Reader,{item,text:'原文段落',items:[],selected:[],onAsk:(...args)=>events.push(args)});app.mount(root);await vue.nextTick()
 const article=all(root).find(n=>n.props.class==='reader-article'),layer=all(root).find(n=>n.props['aria-label']==='知识阅读器'),inside=article.children.at(-1)
 let selection={rangeCount:1,anchorNode:inside,focusNode:inside,toString:()=> '原文段落'};vi.stubGlobal('window',{getSelection:()=>selection})
 layer.props.onMouseup({target:inside});await vue.nextTick();expect(events).toEqual([]);button(root,'问问这段').props.onClick();expect(events).toEqual([[item,'原文段落']])
 selection={...selection,focusNode:root};layer.props.onMouseup({target:inside});await vue.nextTick();expect(button(root,'问问这段')).toBeUndefined()
 selection={...selection,focusNode:inside,toString:()=> 'a'.repeat(1201)};layer.props.onMouseup({target:inside});await vue.nextTick();expect(button(root,'问问这段')).toBeUndefined()
 button(root,'问问这篇').props.onClick();expect(events.at(-1)).toEqual([item]);expect(button(root,'写下这次学到的')).toBeUndefined();button(root,'更多 ···').props.onClick();await vue.nextTick();expect(button(root,'写下这次学到的')).toBeTruthy();app.unmount();vi.unstubAllGlobals()
})
it('mounted report opens sheet without export, emits md only on save and retains failure',async()=>{
 const Report=component('ReportDocument',{'./presentation.js':presentation,'./useLocalSpeech.js':{useLocalSpeech:()=>({speaking:vue.ref(false),speechMessage:vue.ref(''),stop(){},speak(){}})}})
 const events=[],root=node('root'),props=vue.reactive({report:{id:'r',title:'历史报告',body:'真实历史正文',sources:[]},error:'',busy:false})
 const app=renderer.createApp({render:()=>vue.h(Report,{...props,onExport:x=>events.push(x)})});app.mount(root)
 expect(text(root)).toContain('真实历史正文');button(root,'导出 Markdown').props.onClick();await vue.nextTick();expect(events).toEqual([]);button(root,'保存到设备').props.onClick();expect(events).toEqual(['md']);props.error='下载失败';await vue.nextTick();expect(button(root,'保存到设备')).toBeTruthy();expect(text(root)).toContain('下载失败');app.unmount()
})
