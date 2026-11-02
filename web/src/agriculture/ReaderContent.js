import { defineComponent, h } from 'vue'
import { parseInline, resolveReaderLink } from './reader-markdown.js'
// Every tag and attribute here is authored locally; source text is always a child.
export default defineComponent({
  props:{document:Object,item:Object,authorizedItems:Array}, emits:['navigate'],
  setup(props,{emit}) {
    function inline(text){return tokens(parseInline(text,props.document.refs))}
    function tokens(parts){return parts.map(part=>{
      if(part.type==='text')return part.text
      if(part.type==='code')return h('code',part.text)
      if(part.type==='strong')return h('strong',tokens(part.children))
      if(part.type==='em')return h('em',tokens(part.children))
      if(part.type==='image')return h('span',{class:'reader-image-placeholder'},`图片：${part.text || '未命名'}（未自动加载）`)
      if(part.type==='link'){const target=resolveReaderLink(part.destination,props.item,props.authorizedItems)
        if(target.kind==='external')return h('a',{href:target.href,target:'_blank',rel:'noopener noreferrer'},tokens(part.children))
        return h('button',{type:'button',class:'reader-text-link',title:target.kind==='blocked'?target.message:'阅读相关位置',onClick:()=>emit('navigate',target)},tokens(part.children))
      }
      return part.text||''
    })}
    function blocks(values){return values.map(block=>{
      const attrs={'data-source-start':block.startLine,'data-source-end':block.endLine}
      if(block.type==='heading'){const content=inline(block.text),tag=block.level===1?'h1':block.level===2?'h2':block.level===3?'h3':block.level===4?'h4':block.level===5?'h5':'h6';return h(tag,{...attrs,id:block.id,tabindex:-1},content)}
      if(block.type==='paragraph')return h('p',attrs,inline(block.text))
      if(block.type==='plain')return h('pre',{...attrs,class:'reader-plain'},block.text)
      if(block.type==='rule')return h('hr',attrs)
      if(block.type==='code')return h('figure',{...attrs,class:'reader-code'},[block.language?h('figcaption',block.language):null,h('pre',[h('code',block.text)])])
      if(block.type==='quote')return h('blockquote',attrs,blocks(block.blocks))
      if(block.type==='list')return h(block.ordered?'ol':'ul',{...attrs,...(block.ordered?{start:block.start}:{})},block.items.map(item=>h('li',blocks(item.blocks))))
      if(block.type==='table')return h('div',{...attrs,class:'reader-table',tabindex:0},[h('table',[h('thead',[h('tr',block.rows[0].map((cell,i)=>h('th',{class:`align-${block.align[i]||'left'}`},inline(cell))))]),h('tbody',block.rows.slice(1).map(row=>h('tr',row.map((cell,i)=>h('td',{class:`align-${block.align[i]||'left'}`},inline(cell))))))])])
      return h('p',attrs,block.text||'')
    })}
    return ()=>h('div',{class:'reader-prose'},blocks(props.document.blocks))
  }
})
