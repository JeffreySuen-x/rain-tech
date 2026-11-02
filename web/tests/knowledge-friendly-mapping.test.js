import {it,expect} from 'vitest'
import {readFileSync} from 'node:fs'
import {computed} from 'vue'
const source=readFileSync(new URL('../src/agriculture/KnowledgeLibrary.vue',import.meta.url),'utf8')
const expression=name=>source.match(new RegExp(`const ${name}=([^\\n]+)`))[1]
it('projects actual track identities and strictly selects the four approved article IDs',()=>{
  const tracks={value:[{id:'monitoring',count:77},{id:'agricultural_skill_learning',count:52},{id:'shared',count:1}]}
  const main=new Function('computed','tracks',`return ${expression('mainTracks')}`)(computed,tracks)
  expect(main.value.map(item=>item.id)).toEqual(['monitoring','agricultural_skill_learning'])
  const items=['MON-032','EDU-004','EDU-001','EDU-023','MON-099'].map(id=>({id,title:'真实原题 '+id,library:{articleId:id}}))
  const get=items=>new Function('computed','props',`return ${expression('starters')}`)(computed,{items}).value
  expect(get(items).map(entry=>entry.item)).toEqual(items.slice(0,4))
  expect(get(items).map(entry=>entry.cover)).toEqual(['dew','soil','book','camera'])
  expect(get(items.slice(2)).map(entry=>entry.item.id)).toEqual(['EDU-001','EDU-023'])
  expect(get([{id:'fake',title:'夜间叶面结露需要哪些证据',library:{articleId:'OTHER'}}])).toEqual([])
  expect(items[0].title).toBe('真实原题 MON-032')
})
