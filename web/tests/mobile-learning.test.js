import { expect, it } from 'vitest'
import * as vue from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import { readFileSync } from 'node:fs'
import * as topics from '../src/agriculture/mobile-learning.js'
import * as library from '../src/agriculture/library.js'
const descriptor=parse(readFileSync(new URL('../src/agriculture/KnowledgeLibrary.vue',import.meta.url),'utf8')).descriptor
let code=compileScript(descriptor,{id:'learning',inlineTemplate:true}).content
code=code.replace(/^import\s+\{([\s\S]*?)\}\s+from\s+['"]([^'"]+)['"];?/gm,(_,n,m)=>`const {${n.replace(/\bas\b/g,':')}}=bindings[${JSON.stringify(m)}];`).replace(/^import\s+(\w+)\s+from\s+['"]([^'"]+)['"];?/gm,(_,n,m)=>`const ${n}=bindings[${JSON.stringify(m)}].default;`)
const component=new Function('bindings',code.replace('export default','return'))({vue:{...vue,renderSlot:()=>null,withDirectives:v=>v},'./mobile-learning.js':topics,'./library.js':library,'./FriendlyIcon.vue':{default:{render:()=>null}}})
function nodes(v){return [v,...(Array.isArray(v?.children)?v.children.flatMap(nodes):[])]}
it('opens and asks about a real recommendation without selecting references or sending',()=>{
 const item={id:'leaf',title:'叶片观察原文',excerpts:[{text:'观察叶背'}]},events=[]
 const render=component.setup({items:[item],selected:[]},{expose(){},emit:(...args)=>events.push(args)})
 const tree=render({},[]),all=nodes(tree)
 const feature=all.find(v=>v?.props?.class==='mobile-learning-feature')
 nodes(feature).find(v=>v.type==='button').props.onClick()
 all.find(v=>v?.props?.class==='mobile-learning-ask').props.onClick()
 expect(events).toEqual([['read',item],['ask',item]])
})
it('empty library has no invented recommendation or ask target',()=>{
 const render=component.setup({items:[],selected:[]},{expose(){},emit(){}})
 expect(nodes(render({},[])).some(v=>v?.props?.class==='mobile-learning-feature')).toBe(false)
 expect(nodes(render({},[])).some(v=>v?.props?.class==='mobile-learning-ask')).toBe(false)
})
it('opens complete management without discarding the current library',()=>{
 const item={id:'one',title:'水分核查',excerpts:[]}
 const render=component.setup({items:[item],selected:[]},{expose(){},emit(){}})
 let all=nodes(render({},[]));const toggle=all.find(v=>v?.props?.class==='learning-management-toggle')
 expect(toggle.props['aria-expanded']).toBe(false);toggle.props.onClick()
 all=nodes(render({},[]));expect(all.find(v=>v?.props?.class==='learning-management-toggle').props['aria-expanded']).toBe(true)
 expect(all.some(v=>v?.props?.class==='knowledge-grid')).toBe(true)
})

it('filters real topics, leaves unrelated uploads out of recommendations, and returns empty matches',()=>{
 const items=[{id:'soil',title:'土壤水分核查'},{id:'grape',title:'葡萄修剪'},{id:'leaf',title:'叶片观察'},{id:'misc',title:'随手笔记'}]
 expect(topics.topicItems(items,'water').map(x=>x.id)).toEqual(['soil'])
 expect(topics.topicItems(items,'grapes').map(x=>x.id)).toEqual(['grape'])
 expect(topics.topicItems(items,'field').map(x=>x.id)).toEqual(['leaf'])
 expect(topics.topicItems([items[3]],'water')).toEqual([])
 expect(topics.agriculturalItems(items).map(x=>x.id)).toEqual(['soil','grape','leaf'])
})
it('shows every topic match and never asks about a hidden recommendation',()=>{
 const items=[{id:'leaf',title:'叶片观察'},...Array.from({length:4},(_,i)=>({id:`water-${i}`,title:`土壤水分第${i+1}篇`}))]
 const render=component.setup({items,selected:[]},{expose(){},emit(){}})
 let all=nodes(render({},[]));let rows=all.filter(v=>v?.props?.class==='mobile-learning-row')
 expect(rows).toHaveLength(5)
 expect(rows.some(v=>JSON.stringify(v.children).includes('叶片观察'))).toBe(true)
 const chips=all.find(v=>v?.props?.class==='mobile-learning-chips')
 nodes(chips).find(v=>v?.type==='button'&&v.children==='土壤与水分').props.onClick()
 all=nodes(render({},[]));rows=all.filter(v=>v?.props?.class==='mobile-learning-row')
 expect(rows).toHaveLength(4)
 expect(all.some(v=>v?.props?.class==='mobile-learning-feature')).toBe(false)
 expect(all.some(v=>v?.props?.class==='mobile-learning-ask')).toBe(false)
})
