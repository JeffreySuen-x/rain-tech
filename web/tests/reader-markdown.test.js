import { expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import ReaderContent from '../src/agriculture/ReaderContent.js'
import { parseDocument, parseInline, resolveReaderLink, findReaderAnchor } from '../src/agriculture/reader-markdown.js'
it('parses blocks with original line ranges, unique headings, frontmatter and middle rules',()=>{
 const doc=parseDocument('---\ntitle: demo\n---\n# 同名\n\n跨行\n正文\n\n---\n\n## 同名\n\n> 引用\n> - 项目\n\n3. 顺序\n   - 嵌套\n     续行\n\n~~~js\n<script>**原样**</script>\n~~~')
 expect(doc.fallback).toBe(false)
 expect(doc.blocks.map(x=>x.type)).toEqual(['heading','paragraph','rule','heading','quote','list','code'])
 expect(doc.blocks[1]).toMatchObject({startLine:6,endLine:7,text:'跨行 正文'})
 expect(doc.toc.map(x=>x.slug)).toEqual(['同名','同名-1'])
 expect(findReaderAnchor(doc.toc,'同名-1')).toBe('section-L11')
 expect(doc.blocks[5].start).toBe(3)
 expect(doc.blocks[5].items[0].blocks[1].type).toBe('list')
 expect(doc.blocks.at(-1).text).toBe('<script>**原样**</script>')
})
it('supports escaped and inline-code pipes without discarding extra table cells',()=>{
 const table=parseDocument('| 列1 | 列2 |\n| :--- | ---: |\n| `x|y` | a\\|b | 多出 |').blocks[0]
 expect(table.type).toBe('table');expect(table.align).toEqual(['left','right'])
 expect(table.rows[1]).toEqual(['`x|y`','a|b','多出'])
})
it('handles Chinese inline emphasis, code, escapes, reference links and raw unknown math',()=>{
 const tokens=parseInline('**中文** *强调* `**不是粗体**` \\*标记 [文献][a] \\alpha',{a:'https://example.com'})
 expect(tokens.filter(x=>['strong','em','code','link'].includes(x.type)).map(x=>x.type)).toEqual(['strong','em','code','link'])
 expect(tokens.at(-1).text).toContain('\\alpha')
 const doc=parseDocument('[文献][a]\n\n[a]: https://example.com')
 expect(parseInline(doc.blocks[0].text,doc.refs)[0].destination).toBe('https://example.com')
 expect(parseDocument('```\n最后一行').blocks[0].text).toBe('最后一行')
})
it('falls back to the complete source for excessive nesting or input and bounds malformed inline work',()=>{
 const raw='>'.repeat(20)+' 超深全文'
 expect(parseDocument(raw)).toMatchObject({fallback:true,blocks:[{type:'plain',text:raw}]})
 const long='字'.repeat(200001);expect(parseDocument(long).blocks[0].text).toBe(long)
 const wide='|a|b|\n|---|---|\n|'+ 'x|'.repeat(13000);expect(parseDocument(wide)).toMatchObject({fallback:true,blocks:[{text:wide}]})
 const malformed='['.repeat(10000)+']';expect(parseInline(malformed)).toEqual([{type:'text',text:malformed}])
})
const current={id:'a',library:{id:'lib',sourceRelativePath:'articles/a.md'}},target={id:'b',library:{id:'lib',sourceRelativePath:'articles/b.md'}}
it('resolves only exact authorized same-library paths and safe HTTP anchors',()=>{
 expect(resolveReaderLink('./b.md#章节',current,[target])).toEqual({kind:'article',id:'b',fragment:'章节'})
 expect(resolveReaderLink('../articles/b.md',current,[target]).kind).toBe('article')
 for(const value of ['../../b.md','b.md','/articles/b.md','file:///b.md','//x/b.md']) expect(resolveReaderLink(value,current,[]).kind).toBe('blocked')
 expect(resolveReaderLink('b.md',current,[target,target]).kind).toBe('blocked')
 expect(resolveReaderLink('b.md',current,[{...target,library:{...target.library,id:'other'}}]).kind).toBe('blocked')
 expect(resolveReaderLink('#章节',current,[])).toEqual({kind:'anchor',fragment:'章节'})
 expect(resolveReaderLink('https://example.com/path?a=1&b=2',current,[]).kind).toBe('external')
 for(const value of ['JaVaScRiPt:alert(1)','java\nscript:alert(1)','javascript&#58;alert(1)','data:text/html,x','blob:https://x/1','https://user:pass@example.com','https:\\example.com','//example.com','file:/x','vbscript:x'])expect(resolveReaderLink(value,current,[target]).kind).toBe('blocked')
})
it('actual Vue rendering escapes HTML, has semantic tables/lists and never creates media nodes or unsafe links',async()=>{
 const text='# 标题\n\n<script>alert(1)</script> <svg onload="run()"> <iframe src="https://x"></iframe>\n\n![观察图](https://remote.test/image.png) [危险](javascript:alert(1)) **粗体**\n\n| 名称 | 值 |\n| --- | --- |\n| a | b |\n\n- 列表\n\n[来源](https://example.com)'
 const html=await renderToString(createSSRApp({render:()=>h(ReaderContent,{document:parseDocument(text),item:current,authorizedItems:[target]})}))
 expect(html).toContain('&lt;script&gt;');expect(html).toContain('<strong>粗体</strong>');expect(html).toContain('<thead>');expect(html).toContain('<tbody>');expect(html).toContain('<ul')
 expect(html).not.toMatch(/<(?:script|svg|iframe|img|source|video|object|embed|style)\b/)
 expect(html).not.toContain('href="javascript:');expect(html).toContain('图片：观察图（未自动加载）');expect(html).toContain('rel="noopener noreferrer"')
})
it('preserves intraword underscores and enforces emphasis delimiter whitespace boundaries',async()=>{
 const literal='FINAL_TAIL_SENTINEL snake_case_name value__double__name x_ word_ a* b* ** spaced **'
 expect(parseInline(literal)).toEqual([{type:'text',text:literal}])
 const doc=parseDocument(literal+'\n\n_斜体_ __粗体__ 中文**强调**边界 a*b*c')
 const html=await renderToString(createSSRApp({render:()=>h(ReaderContent,{document:doc,item:current,authorizedItems:[]})}))
 expect(html).toContain('FINAL_TAIL_SENTINEL');expect(html).toContain('snake_case_name');expect(html).toContain('value__double__name')
 expect(html).toContain('<em>斜体</em>');expect(html).toContain('<strong>粗体</strong>');expect(html).toContain('中文<strong>强调</strong>边界');expect(html).toContain('a<em>b</em>c')
 expect(parseInline('中文_内部_变量')).toEqual([{type:'text',text:'中文_内部_变量'}])
})
it('bounds repeated unclosed link destinations and backtick searches with complete literal fallback',()=>{
 // The prefix would normally create strong tokens: one literal token therefore
 // proves the exhausted budget returns the entire input, including prior text.
 const links='**保留完整原文** '+ '[x]('.repeat(10000)
 expect(parseInline(links)).toEqual([{type:'text',text:links}])
 const ticks='**保留完整原文** '+ '`'.repeat(4000)+'未闭合代码尾部'
 expect(parseInline(ticks)).toEqual([{type:'text',text:ticks}])
 const escaped='**保留完整原文** '+ '[x]('.repeat(2000)+'\\x'.repeat(10000)
 expect(parseInline(escaped)).toEqual([{type:'text',text:escaped}])
})
