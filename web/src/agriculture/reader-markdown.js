// Clean-room static Markdown subset. No HTML strings, network or filesystem access.
const MAX_NODES = 12000, MAX_DEPTH = 8, MAX_TEXT = 200000
const heading = text => /^( {0,3})(#{1,6})\s+(.+?)\s*#*\s*$/.exec(text)
const rule = text => /^ {0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/.test(text)
const fence = text => /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(text)
const list = text => /^(\s*)([-+*]|\d+[.)])\s+(.*)$/.exec(text)
const slug = text => text.toLocaleLowerCase().replace(/[*_`]/g,'').replace(/[^\p{L}\p{N}\s-]/gu,'').trim().replace(/\s+/g,'-')
function cells(text) {
  let value=text.trim(); if(value.startsWith('|')) value=value.slice(1); if(value.endsWith('|') && !value.endsWith('\\|'))value=value.slice(0,-1)
  const result=[];let cell='',ticks=0
  for(let i=0;i<value.length;i++) { const ch=value[i]; if(ch==='\\' && value[i+1]==='|') {cell+='|';i++;continue} if(ch==='`'){let n=1;while(value[i+n]==='`')n++; if(!ticks)ticks=n;else if(ticks===n)ticks=0;cell+='`'.repeat(n);i+=n-1;continue} if(ch==='|'&&!ticks){result.push(cell.trim());cell=''}else cell+=ch }
  result.push(cell.trim());return result
}
const separator = text => {const values=cells(text);return values.length>0 && values.every(x=>/^:?-{3,}:?$/.test(x)) ? values.map(x=>x.startsWith(':')&&x.endsWith(':')?'center':x.endsWith(':')?'right':'left') : null}
export function parseDocument(rawText) {
  const raw=String(rawText || ''), refs={}, toc=[]; let count=0
  const fallback=()=>({blocks:[{type:'plain',text:raw,startLine:1,endLine:raw.split('\n').length}],toc:[],refs:{},fallback:true})
  if(raw.length>MAX_TEXT)return fallback()
  const rows=raw.split(/\r?\n/).map((text,i)=>({text,line:i+1}))
  let start=0
  if(rows[0]?.text.replace(/^\uFEFF/,'').trim()==='---'){const end=rows.findIndex((r,i)=>i>0&&r.text.trim()==='---');if(end>0)start=end+1}
  // Definitions remain visible as source notes; reference use is resolved without navigation.
  for(const row of rows.slice(start)){const m=/^ {0,3}\[([^\]]+)\]:\s*(\S+)(?:\s+.*)?$/.exec(row.text);if(m)refs[m[1].toLocaleLowerCase()]=m[2].replace(/^<|>$/g,'')}
  const usedSlugs=new Map()
  function parse(input,depth) {
    if(depth>MAX_DEPTH)throw Error('depth')
    const out=[]; let i=0
    function add(type,a,b,data={}){
      const tokensCount = tokens => tokens.reduce((sum,token) => sum+1+(token.children?tokensCount(token.children):0),0)
      count++
      if(type==='paragraph'||type==='heading') count+=tokensCount(parseInline(data.text,refs))
      if(type==='table') for(const row of data.rows) { count++; for(const cell of row) count+=1+tokensCount(parseInline(cell,refs)); }
      if(count>MAX_NODES)throw Error('nodes')
      out.push({type,startLine:input[a].line,endLine:input[b].line,...data})
    }
    function special(index){const t=input[index]?.text||'';return !t.trim()||heading(t)||rule(t)||fence(t)||list(t)||/^\s*>/.test(t)||(index+1<input.length&&t.includes('|')&&separator(input[index+1].text))}
    while(i<input.length){const t=input[i].text;if(!t.trim()){i++;continue}const a=i;let m
      if((m=fence(t))){i++;const body=[];const marker=m[1][0],minimum=m[1].length;while(i<input.length&&!new RegExp('^ {0,3}'+(marker==='`'?'`':'~')+'{'+minimum+',}\\s*$').test(input[i].text)){body.push(input[i++].text)}const end=i<input.length?i++:i-1;add('code',a,end,{text:body.join('\n'),language:m[2].trim()});continue}
      if((m=heading(t))){const text=m[3],base=slug(text),n=usedSlugs.get(base)||0;usedSlugs.set(base,n+1);const entry={level:m[2].length,text,id:`section-L${input[i].line}`,slug:base+(n?`-${n}`:'')};toc.push(entry);add('heading',i,i,{...entry});i++;continue}
      if(rule(t)){add('rule',i,i);i++;continue}
      if(/^\s*>/.test(t)){const inner=[];while(i<input.length&&/^\s*>/.test(input[i].text)){inner.push({...input[i],text:input[i].text.replace(/^\s*> ?/,'')});i++}add('quote',a,i-1,{blocks:parse(inner,depth+1)});continue}
      if((m=list(t))){const indent=m[1].length,ordered=/\d/.test(m[2][0]),items=[];const first=Number.parseInt(m[2],10)||1
        while(i<input.length){const match=list(input[i].text);if(!match||match[1].length!==indent||/\d/.test(match[2][0])!==ordered)break
          const child=[{...input[i],text:match[3]}];i++
          while(i<input.length){const next=list(input[i].text);if(next&&next[1].length<=indent)break
            if(!input[i].text.trim()){if(i+1<input.length&&/^\s+/.test(input[i+1].text)){child.push(input[i++]);continue}break}
            if((/^\s*/.exec(input[i].text)[0].length)<=indent)break
            child.push({...input[i],text:input[i].text.slice(Math.min(indent+2,/^\s*/.exec(input[i].text)[0].length))});i++
          }
          items.push({blocks:parse(child,depth+1)})
          if(!input[i]?.text.trim()){let j=i;while(j<input.length&&!input[j].text.trim())j++;const following=list(input[j]?.text||'');if(following&&following[1].length===indent){i=j;continue}break}
        }
        add('list',a,Math.max(a,i-1),{ordered,start:first,items});continue
      }
      const align=i+1<input.length&&t.includes('|')?separator(input[i+1].text):null
      if(align){const tableRows=[cells(t)];i+=2;while(i<input.length&&input[i].text.includes('|')&&input[i].text.trim()){tableRows.push(cells(input[i++].text))}add('table',a,i-1,{rows:tableRows,align});continue}
      const body=[t];i++;while(i<input.length&&!special(i)){body.push(input[i++].text)}add('paragraph',a,i-1,{text:body.join(' ')})
    }
    return out
  }
  try{return {blocks:parse(rows.slice(start),0),toc,refs,fallback:false}}catch{return fallback()}
}
export function parseInline(text,refs={},depth=0) {
  text=String(text);if(depth>MAX_DEPTH||text.length>MAX_TEXT)return [{type:'text',text}]
  const tokens=[];let plain='',i=0,work=0
  const flush=()=>{if(plain){tokens.push({type:'text',text:plain});plain=''}}
  while(i<text.length){if(tokens.length>MAX_NODES)return [{type:'text',text}]
    if(text[i]==='\\'&&i+1<text.length&&/[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/.test(text[i+1])){plain+=text[i+1];i+=2;continue}
    if(text[i]==='`'){let n=1;while(text[i+n]==='`'){n++;if(++work>MAX_TEXT*8)return [{type:'text',text}]}const marker='`'.repeat(n),end=text.indexOf(marker,i+n);work+=(end<0?text.length:end)-(i+n);if(work>MAX_TEXT*8)return [{type:'text',text}];if(end>=0){flush();tokens.push({type:'code',text:text.slice(i+n,end)});i=end+n;continue}}
    const image=text.startsWith('![',i), link=text[i]==='['
    if(image||link){const begin=i+(image?2:1),end=text.indexOf(']',begin);work+=(end<0?text.length:end)-begin;if(work>MAX_TEXT*8)return [{type:'text',text}];if(end>=0){const label=text.slice(begin,end);let destination='',last=end+1
        if(text[end+1]==='('){let cursor=end+2,balance=1;for(;cursor<text.length;cursor++){if(++work>MAX_TEXT*8)return [{type:'text',text}];if(text[cursor]==='\\'){cursor++;if(++work>MAX_TEXT*8)return [{type:'text',text}];continue}if(text[cursor]==='(')balance++;if(text[cursor]===')'&&!--balance)break}if(balance===0){destination=text.slice(end+2,cursor).trim().replace(/^<([^>]+)>$/,'$1');last=cursor+1}}
        else if(text[end+1]==='['){const close=text.indexOf(']',end+2);work+=(close<0?text.length:close)-(end+2);if(work>MAX_TEXT*8)return [{type:'text',text}];if(close>=0){destination=refs[(text.slice(end+2,close)||label).toLocaleLowerCase()]||'';if(destination)last=close+1}}
        else {destination=refs[label.toLocaleLowerCase()]||''}
        if(destination){flush();tokens.push(image?{type:'image',text:label}:{type:'link',destination,children:parseInline(label,refs,depth+1)});i=last;continue}
      }}
    let consumed=false
    const flanks=(position,length)=>{
      const before=text[position-1]||'',after=text[position+length]||''
      const space=ch=>!ch||/\s/u.test(ch), punctuation=ch=>Boolean(ch)&&/[\p{P}\p{S}]/u.test(ch)
      return {left:!space(after)&&(!punctuation(after)||space(before)||punctuation(before)),right:!space(before)&&(!punctuation(before)||space(after)||punctuation(after)),beforePunctuation:punctuation(before),afterPunctuation:punctuation(after)}
    }
    for(const marker of ['**','__','*','_'])if(text.startsWith(marker,i)&&text[i+marker.length]!==marker[0]&&text[i-1]!==marker[0]){
      // Underscores inside words/identifiers are literal. Stars retain Markdown's
      // permitted intraword emphasis, but neither delimiter consumes whitespace.
      const opening=flanks(i,marker.length),underscore=marker[0]==='_'
      if(!opening.left||(underscore&&opening.right&&!opening.beforePunctuation))continue
      let end=text.indexOf(marker,i+marker.length)
      while(end>=0){
        work+=end-i;if(work>MAX_TEXT*8)return [{type:'text',text}]
        const closing=flanks(end,marker.length)
        let escapes=0;for(let cursor=end-1;cursor>=0&&text[cursor]==='\\';cursor--)escapes++
        if(end>i+marker.length&&text[end-1]!==marker[0]&&text[end+marker.length]!==marker[0]&&escapes%2===0&&closing.right&&(!underscore||!closing.left||closing.afterPunctuation))break
        end=text.indexOf(marker,end+marker.length)
      }
      if(end>i+marker.length){flush();tokens.push({type:marker.length===2?'strong':'em',children:parseInline(text.slice(i+marker.length,end),refs,depth+1)});i=end+marker.length;consumed=true;break}
    }
    if(consumed)continue;
    if(text[i]==='_'||text[i]==='*'){const marker=text[i];do{plain+=text[i++]}while(text[i]===marker)}else plain+=text[i++]
  }
  flush();return tokens
}
export function resolveReaderLink(destination,currentItem,authorizedItems=[]) {
  const value=String(destination||'').trim(),blocked={kind:'blocked',message:'当前知识库未收录或链接不可用'}
  if(!value||/[\u0000-\u0020\u007f\\]/.test(value)||value.startsWith('//'))return blocked
  if(/^https?:/i.test(value)){try{const url=new URL(value);if(!['http:','https:'].includes(url.protocol)||url.username||url.password||!/^https?:\/\//i.test(value))return blocked;return {kind:'external',href:url.href}}catch{return blocked}}
  if(value.startsWith('#')){try{return {kind:'anchor',fragment:decodeURIComponent(value.slice(1))}}catch{return blocked}}
  if(value.startsWith('/')||/^[a-z][a-z\d+.-]*:/i.test(value)||!currentItem?.library?.id)return blocked
  const hash=value.indexOf('#'), path=hash<0?value:value.slice(0,hash);let decoded,fragment
  try{decoded=decodeURIComponent(path);fragment=hash<0?'':decodeURIComponent(value.slice(hash+1))}catch{return blocked}
  if(!decoded||/[\u0000-\u0020\u007f\\?#]/.test(decoded)||decoded.startsWith('/')||!decoded.toLowerCase().endsWith('.md'))return blocked
  const parts=(currentItem.library.sourceRelativePath||'').split('/');parts.pop()
  for(const part of decoded.split('/')){if(!part||part==='.')continue;if(part==='..'){if(!parts.length)return blocked;parts.pop()}else parts.push(part)}
  const normalized=parts.join('/'), matches=authorizedItems.filter(x=>x.library?.id===currentItem.library.id&&x.library?.sourceRelativePath===normalized)
  return matches.length===1?{kind:'article',id:matches[0].id,fragment}:blocked
}
export function findReaderAnchor(toc,fragment) {return toc.find(x=>x.id===fragment||x.slug===fragment||x.text===fragment)?.id||null}
