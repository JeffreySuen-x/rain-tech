import {expect,it} from 'vitest'
import {parseDocument,parseInline,resolveReaderLink,findReaderAnchor} from '../src/agriculture/reader-markdown.js'
const current={id:'A',library:{id:'private-library',sourceRelativePath:'articles/A.md'}}
const sibling={id:'B',library:{id:'private-library',sourceRelativePath:'articles/B.md'}}
it('independent: semantic blocks preserve tail, source lines, code pipes and unsupported content',()=>{
 const raw='---\ntitle: SECRET_METADATA\n---\n# 重复\n\n中文**重要**和*强调* `**代码**`\n\n# 重复\n\n3. first\n   - nested\n     continuation\n\n> quoted\n> - list\n\n| 名称 | 结果 |\n| :--- | ---: |\n| a\\|b | `c|d` | extra |\n\n~~~html\n<script>CODE_ONLY</script>\n~~~\n\n---\n\n[参考][ref]\n\n[ref]: https://example.org/p\n\n$$ unknown_math $$\nFINAL_TAIL'
 const doc=parseDocument(raw);expect(doc.fallback).toBe(false);expect(doc.blocks[0]).toMatchObject({type:'heading',startLine:4,id:'section-L4'})
 expect(new Set(doc.toc.map(x=>x.id)).size).toBe(2);expect(new Set(doc.toc.map(x=>x.slug)).size).toBe(2)
 expect(doc.blocks.find(x=>x.type==='list')).toMatchObject({ordered:true,start:3})
 expect(doc.blocks.find(x=>x.type==='table').rows[1]).toEqual(['a|b','`c|d`','extra'])
 expect(doc.blocks.find(x=>x.type==='code').text).toBe('<script>CODE_ONLY</script>')
 expect(doc.blocks.some(x=>x.type==='rule')).toBe(true);expect(JSON.stringify(doc.blocks)).toContain('FINAL_TAIL');expect(JSON.stringify(doc.blocks)).toContain('unknown_math')
 const inline=parseInline('中文**重要**和*强调* `**代码**` [参考][ref]',doc.refs)
 expect(inline.map(x=>x.type)).toEqual(expect.arrayContaining(['strong','em','code','link']));expect(inline.find(x=>x.type==='code').text).toBe('**代码**')
 expect(findReaderAnchor(doc.toc,doc.toc[1].slug)).toBe(doc.toc[1].id)
})
it('independent: overdepth and oversized documents fall back without truncation',()=>{
 for(const raw of ['>'.repeat(14)+' deepest\nTAIL','FULL\n'+'字'.repeat(200001)+'END']){
  const doc=parseDocument(raw);expect(doc.fallback).toBe(true);expect(doc.blocks[0].text).toBe(raw)
 }
 const unclosed=parseDocument('```js\n<script>tail</script>\nEND');expect(unclosed.blocks[0].text).toContain('END')
})
it('independent: link classifier rejects protocol confusion and only resolves unique authorized same-library paths',()=>{
 for(const value of ['javascript:alert(1)','JaVaScRiPt:alert(1)','java\nscript:alert(1)','jav&#x61;script:alert(1)','data:text/html,x','blob:https://example.org/id','file:///private/secret','//example.org/a','https:\\example.org/a','https://user:password@example.org/a','/Library/private.md','../../B.md','../B.md','B.md%00','%2e%2e/%2e%2e/B.md'])expect(resolveReaderLink(value,current,[sibling]).kind,value).toBe('blocked')
 expect(resolveReaderLink('./B.md#section-L9',current,[sibling])).toEqual({kind:'article',id:'B',fragment:'section-L9'})
 expect(resolveReaderLink('../articles/B.md',current,[sibling]).kind).toBe('article')
 expect(resolveReaderLink('B.md',current,[]).kind).toBe('blocked')
 expect(resolveReaderLink('B.md',current,[sibling,{...sibling,id:'duplicate'}]).kind).toBe('blocked')
 expect(resolveReaderLink('B.md',current,[{...sibling,library:{...sibling.library,id:'foreign-library'}}]).kind).toBe('blocked')
 expect(resolveReaderLink('https://example.org/p?a=1&b=2',current,[])).toMatchObject({kind:'external',href:'https://example.org/p?a=1&b=2'})
})
it('independent: reader tail and identifiers preserve literal intraword underscores',()=>{
 for(const raw of ['FINAL_TAIL_SENTINEL','snake_case_name','value__double__name','中文_内部_变量'])expect(parseInline(raw)).toEqual([{type:'text',text:raw}])
 expect(parseInline('__中文粗体__').some(x=>x.type==='strong')).toBe(true)
 expect(parseInline('中文**重要**').some(x=>x.type==='strong')).toBe(true)
 expect(parseInline('a*b*c').some(x=>x.type==='em')).toBe(true)
})
it('independent: malformed repeated destinations and unmatched code fences preserve full text under parser work budget',()=>{
 const malformed='[a]('.repeat(6000)+'FINAL_TAIL_SENTINEL'
 const unmatched='`'.repeat(10000)+'FINAL_TAIL_SENTINEL'
 for(const raw of [malformed,unmatched]){
  const started=performance.now();const tokens=parseInline(raw)
  expect(tokens).toEqual([{type:'text',text:raw}]);expect(performance.now()-started).toBeLessThan(1500)
 }
})
