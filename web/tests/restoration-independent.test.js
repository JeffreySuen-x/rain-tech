import {readFileSync} from 'node:fs'
import {expect,it} from 'vitest'
const source=readFileSync(new URL('../src/agriculture/AgricultureWorkbench.vue',import.meta.url),'utf8')
const body=source.match(/const canSend = computed\(\(\) => \{([\s\S]*?)\n\}\);/)[1]
const eligible=(kind,assets,ids,text='')=>new Function('selectedSkill','draft','assets','assetIds',body)({value:{kind}},{value:text},{value:assets},{value:ids})
it('independent: stale selected IDs from another workspace cannot authorize media sending',()=>{
 for(const kind of ['image_analysis','audio_transcription'])expect(eligible(kind,[{id:'current',kind:kind==='image_analysis'?'image':'audio'}],['old-workspace-asset'],'描述')).toBe(false)
})
it('independent: mixed references allow the one matching file, removing it disables media send',()=>{
 const rows=[{id:'photo',kind:'image'},{id:'audio',kind:'audio'},{id:'document',kind:'document'}]
 expect(eligible('image_analysis',rows,['photo','audio','document'])).toBe(true)
 expect(eligible('audio_transcription',rows,['photo','audio','document'])).toBe(true)
 expect(eligible('image_analysis',rows,['audio','document'])).toBe(false)
})
it('independent: whitespace never enables chat even with selected media',()=>expect(eligible('chat',[{id:'photo',kind:'image'}],['photo'],' \n ')).toBe(false))
