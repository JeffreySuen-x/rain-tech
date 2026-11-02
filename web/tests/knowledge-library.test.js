import { expect, it } from 'vitest'
import { libraryPage, libraryTracks, readingLines, knowledgePreview } from '../src/agriculture/library.js'
const items=Array.from({length:130},(_,i)=>({id:`k${i}`,title:`教程 ${i}`,library:{articleId:`MON-${i}`,memberships:[{trackId:i%2?'edu':'mon',trackTitle:i%2?'农业技能':'作物监测',groupId:`g${i%6}`,groupTitle:`组${i%6}`,order:i}]},excerpts:[{text:i===129?'最后一段独特全文':'普通正文'}]}))
it('searches the entire authorized corpus before pagination, including final text, ID and metadata',()=>{
 expect(libraryPage(items,{query:'独特全文'}).items.map(x=>x.id)).toEqual(['k129'])
 expect(libraryPage(items,{query:'MON-129'}).total).toBe(1)
 expect(libraryPage(items,{track:'edu',page:2}).items).toHaveLength(12)
 expect(libraryPage(items,{track:'edu'}).total).toBe(65)
 expect(libraryPage(items,{query:'独特全文',page:10}).page).toBe(1)
 expect(libraryPage(items,{query:'农业技能'}).total).toBe(65)
})
it('deduplicates navigation memberships while preserving old personal materials',()=>{
 const old={id:'old',title:'旧园区资料',excerpts:[{text:'旧资料可读'}]}
 expect(libraryPage([...items,old],{track:'mine'}).items).toEqual([old])
 expect(libraryPage([...items,old],{query:'旧资料可读'}).items).toEqual([old])
 expect(libraryTracks(items)).toHaveLength(2)
 expect(libraryTracks(items)[0].count).toBe(65)
})
it('hides only paired opening frontmatter and preserves original line numbers, final sources and untrusted text',()=>{
 const text='---\ntitle: x\n---\n# 标题\n正文\n---\n来源 https://example.com\n<script>alert(1)</script>'
 const rows=readingLines(text)
 expect(rows[0]).toMatchObject({line:4,heading:true,title:'标题'})
 expect(rows.at(-1).text).toBe('<script>alert(1)</script>')
 expect(rows.map(x=>x.text)).toContain('---')
 expect(rows.map(x=>x.text).join('\n')).toContain('来源 https://example.com')
 expect(readingLines('---\n正文')[0].text).toBe('---')
})
it('sorts reversed API navigation by minimum membership order with shared first',()=>{
 const articles=[{library:{memberships:[{trackId:'mon',groupId:'a2',order:20}]}},{library:{memberships:[{trackId:'edu',groupId:'b1',order:40}]}},{library:{memberships:[{trackId:'mon',groupId:'a1',order:0},{trackId:'mon',groupId:'a2',order:25}]}},{library:{memberships:[{trackId:'shared',groupId:'shared',order:100}]}}]
 const tracks=libraryTracks(articles)
 expect(tracks.map(x=>x.id)).toEqual(['shared','mon','edu'])
 expect(tracks[1].groups.map(x=>x.id)).toEqual(['a1','a2'])
})

it('tutorial previews use the first real paragraph after YAML, titles and early catalog lines',()=>{
 const body='---\ntitle: 测试\n---\n# 标题\n\n- 固定ID：MON-002\n- 版本：v0.1\n- 更新日期：2026-10-24\n标签：监测\n前置知识：观察\n关联篇：MON-001\n导航：目录\n- 修订摘要：初版\n\n## 问题\n\n短答：'+ '正文'.repeat(100)+'\n\n第二段'
 const item={library:{},summary:'ID：错误旧摘要',excerpts:[{text:body}]}
 expect(knowledgePreview(item)).toBe(('短答：'+'正文'.repeat(100)).slice(0,160)+'…')
 expect(knowledgePreview({library:{},excerpts:[{text:'# 标题\n版本：v1\n\n真实正文\n\n版本：正文后应保留在原件'}]})).toBe('真实正文')
 expect(knowledgePreview({summary:'用户摘要',excerpts:[{text:'其他正文'}]})).toBe('用户摘要')
 expect(readingLines(body).some(x=>x.text==='- 固定ID：MON-002')).toBe(true)
})
