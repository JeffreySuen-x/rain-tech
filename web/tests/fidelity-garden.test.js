import {expect,it} from 'vitest'
import {readFileSync} from 'node:fs'
import {parse,compileScript} from '@vue/compiler-sfc'
import * as vue from 'vue'
const source=readFileSync(new URL('../src/agriculture/MobileGarden.vue',import.meta.url),'utf8')
const descriptor=parse(source).descriptor
let code=compileScript(descriptor,{id:'garden',inlineTemplate:true}).content
code=code.replace(/^import\s+\{([\s\S]*?)\}\s+from\s+['"]([^'"]+)['"];?/gm,(_,n,m)=>`const {${n.replace(/\bas\b/g,':')}}=bindings[${JSON.stringify(m)}];`)
code=code.replace(/^import FriendlyIcon from .*$/m, 'const FriendlyIcon={render:()=>null}')
const component=new Function('bindings',code.replace('export default','return'))({vue,'./calendarPresentation.js':{displayDate:()=> '日期',displayLunar:()=>''},'./api.js':{agricultureAssetContentUrl:()=>''}})
function nodes(v){return [v,...(Array.isArray(v?.children)?v.children.flatMap(nodes):[])]}
it('opens a specific task and returns from readings to the garden',()=>{
 const events=[]
 const render=component.setup({tasks:[{id:'specific-task',title:'核查叶片'}],metrics:[],live:{enabled:false},overview:{},observations:[]},{expose(){},emit:(...v)=>events.push(v)})
 let all=nodes(render({$emit:(...v)=>events.push(v)},[]))
 all.find(v=>v.type==='button'&&v.props.class==='primary').props.onClick()
 expect(events).toEqual([['task','specific-task']])
 all.find(v=>v.props?.class==='readings-button').props.onClick()
 all=nodes(render({},[]));expect(all.some(v=>v.props?.class==='large-readings')).toBe(true)
 all.find(v=>v.props?.class==='back').props.onClick()
 expect(nodes(render({},[])).some(v=>v.props?.class==='priority')).toBe(true)
})
it('guards stale and unknown live mutations and emits real actions',()=>{
 const s=readFileSync(new URL('../src/agriculture/LiveFieldPanel.vue',import.meta.url),'utf8')
 expect(s).toContain('props.pending || props.uncertain || stale.value')
 expect(s).toContain("props.live.status !== 'online'")
 expect(s).toContain("action('camera.capture',{cameraId:camera.id})")
 expect(s).toContain("emit('register-device')")
 expect(s).toContain("emit('create-task',")
})
