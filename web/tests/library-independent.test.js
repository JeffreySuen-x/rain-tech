import {expect,it,vi} from 'vitest'
import {createPinia,setActivePinia} from 'pinia'
import {libraryPage,libraryTracks,readingLines} from '../src/agriculture/library.js'
import {useWorkspace} from '../src/store.js'
import {request} from '../src/api.js'
vi.mock('../src/api.js',()=>({request:vi.fn()}))
const member=(group,order)=>({trackId:'MON',trackTitle:'方向',groupId:group,groupTitle:group,sectionLabel:'节',order})
const items=Array.from({length:130},(_,i)=>({id:'k'+i,title:'教程'+i,library:{articleId:'MON-'+i,memberships:[member('g'+(i%6),i),member('shared-group',i)]},excerpts:[{text:'start\n末尾特征'+i}]}))
it('independent: all 130 and legacy coexist; filter complete text before pagination; duplicate memberships do not inflate',()=>{
 const all=[...items,{id:'old',title:'旧资料',excerpts:[{text:'旧原文'}]}]
 expect(libraryPage(all).total).toBe(131)
 expect(libraryPage(all,{query:'末尾特征129',page:11}).items.map(x=>x.id)).toEqual(['k129'])
 expect(libraryPage(all,{track:'mine'}).items.map(x=>x.id)).toEqual(['old'])
 expect(libraryPage(all,{track:'MON',group:'shared-group'}).total).toBe(130)
 expect(libraryTracks(all)[0].count).toBe(130)
 const seen=[];for(let p=1;p<=11;p++)seen.push(...libraryPage(all,{track:'MON',page:p}).items.map(x=>x.id))
 expect(new Set(seen).size).toBe(130);expect(seen).toHaveLength(130);expect(request).not.toHaveBeenCalled()
})
it('independent: YAML hiding preserves original line numbers, middle separators, and hostile text',()=>{
 const raw='---\ntitle: "<img src=x onerror=alert(1)>"\n---\n# 正文\n---\n<script>alert(1)</script>\n末尾'
 const lines=readingLines(raw)
 expect(lines[0]).toMatchObject({line:4,text:'# 正文'})
 expect(lines.map(x=>x.text)).toContain('---');expect(lines.at(-1)).toMatchObject({line:7,text:'末尾'})
 expect(lines[2].text).toBe('<script>alert(1)</script>')
})
it('independent: initial privacy is opt-out and workspace change clears explicit selection',async()=>{
 setActivePinia(createPinia());const s=useWorkspace();expect(s.includeHistory).toBe(false)
 s.user={id:'a'};s.workspaceId='w';s.agricultureContext={knowledgeIds:['k129'],assetIds:[]};s.includeHistory=true
 request.mockResolvedValue({threads:[],memories:[],messages:[],turns:[]})
 await s.selectWorkspace('w2');expect(s.includeHistory).toBe(false);expect(s.agricultureContext?.knowledgeIds||[]).toEqual([])
})
