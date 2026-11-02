import {readFileSync} from 'node:fs'
import {describe,it,expect} from 'vitest'
const source=readFileSync(new URL('../src/agriculture/AgricultureWorkbench.vue',import.meta.url),'utf8')
const body=source.match(/const canSend = computed\(\(\) => \{([\s\S]*?)\n\}\);/)[1]
function eligible(kind,prompt,rows,ids){return new Function('selectedSkill','draft','assets','assetIds',body)({value:kind?{kind}:null},{value:prompt},{value:rows},{value:ids})}
describe('restored mobile composer eligibility',()=>{
 it('requires text for chat',()=>{expect(eligible('chat','',[],[])).toBe(false);expect(eligible('chat',' hi ',[],[])).toBe(true)})
 it('requires exactly one selected matching media for image and audio',()=>{for(const [kind,media] of [['image_analysis','image'],['audio_transcription','audio']]){const rows=[{id:'a',kind:media},{id:'b',kind:media},{id:'c',kind:'document'}];expect(eligible(kind,'',rows,['a'])).toBe(true);expect(eligible(kind,'',rows,[])).toBe(false);expect(eligible(kind,'text',rows,['a','b'])).toBe(false);expect(eligible(kind,'',rows,['c'])).toBe(false)}})
 it('uses eligibility for visibility and disabled state',()=>{expect(source).toContain("'mobile-send-empty':!canSend");expect(source).toContain('generating || !canSend');expect(source).toContain('aria-label="本轮上下文"')})
})

it('round chips route into the existing settings and resources state',()=>{
 const row=source.match(/<div v-if="tab === 'chat'" class="mobile-round-context"[\s\S]*?<\/div>/)[0]
 const actions=[...row.matchAll(/@click="([^"]+)"/g)].map(match=>match[1])
 const state=new Function(`let dialog='',resourcesTab='threads',resourcesOpen=false;${actions.join(';')};return {dialog,resourcesTab,resourcesOpen}`)()
 expect(state).toEqual({dialog:'settings',resourcesTab:'assets',resourcesOpen:true})
})
it('production send dispatches a selected photo or recording without text',async()=>{
 const branch=source.slice(source.indexOf('  if (retry !== true && selectedSkill.value?.kind'),source.indexOf('  // Vue passes'))
 for(const [kind,media,action] of [['image_analysis','image','analyze'],['audio_transcription','audio','transcribe']]){
  const calls=[];const error={value:''};const asset={id:'synthetic',kind:media}
  const run=new Function('selectedSkill','assets','assetIds','processAsset','error',`return async function(retry=false){${branch}}`)({value:{kind}},{value:[asset]},{value:['synthetic']},async(...args)=>calls.push(args),error)
  await run();expect(calls).toEqual([[asset,action]]);expect(error.value).toBe('')
 }
})
