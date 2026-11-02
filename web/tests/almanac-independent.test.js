import { expect, it } from 'vitest'
import * as vue from 'vue'
import { createRenderer, h, nextTick } from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import { readFileSync } from 'node:fs'
import * as calendarPresentation from '../src/agriculture/calendarPresentation.js'
import * as api from '../src/agriculture/api.js'
const descriptor=parse(readFileSync(new URL('../src/agriculture/MobileGarden.vue',import.meta.url),'utf8')).descriptor
let code=compileScript(descriptor,{id:'independent-almanac',inlineTemplate:true}).content
code=code.replace(/^import\s+\{([\s\S]*?)\}\s+from\s+['"]([^'"]+)['"];?/gm,(_,n,m)=>`const {${n.replace(/\bas\b/g,':')}}=bindings[${JSON.stringify(m)}];`).replace(/^import\s+(\w+)\s+from\s+['"]([^'"]+)['"];?/gm,(_,n,m)=>`const ${n}=bindings[${JSON.stringify(m)}].default;`)
const MobileGarden=new Function('bindings',code.replace('export default','return'))({vue,'./FriendlyIcon.vue':{default:{render:()=>null}},'./calendarPresentation.js':calendarPresentation,'./api.js':api})
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

it('independent compiled mobile almanac opens, expands advice and future nodes, and renders unavailable state',async()=>{
 const calendar=vue.reactive({status:'available',date:'2026-10-31',lunarDate:'九月廿二',yi:['宜一','宜二','宜三','宜四'],ji:['忌一','忌二','忌三','忌四'],nodes:Array.from({length:7},(_,i)=>({id:`n${i}`,name:`独立节点${i}`,type:i===0?'lunarFestival':'solarTerm',date:`2026-11-${String(i+1).padStart(2,'0')}`,lunarDate:'九月',daysUntil:i+1}))})
 const root=node('root'),app=renderer.createApp(h(MobileGarden,{overview:{presentation:{calendar,weather:{forecast:[]}}},metrics:[],tasks:[],observations:[]}))
 app.mount(root)
 try {
 const click=async label=>{const button=all(root).find(n=>n.tag==='button'&&text(n).includes(label));expect(button,`button ${label}`).toBeTruthy();button.props.onClick();await nextTick()}
 await click('黄历')
 const details=all(root).filter(n=>n.tag==='details')
 expect(details).toHaveLength(2)
 expect(details.every(n=>!n.props.open)).toBe(true)
 const outside=all(root).filter(n=>n.props.class==='calendar-node' && n.parent.tag!=='details')
 expect(outside).toHaveLength(4)
 expect(text(details[0])).toContain('宜四');expect(text(details[0])).toContain('忌四')
 expect(text(details[1])).toContain('查看未来一年');expect(text(details[1])).toContain('独立节点6')
 expect(text(root)).toContain('下个农历节日：独立节点0')
 calendar.status='unavailable';calendar.nodes=[];await nextTick()
 expect(text(root)).toMatch(/暂不可用|暂未|不可用/)
 expect(text(root)).not.toContain('独立节点6')
 } finally {app.unmount()}
})
