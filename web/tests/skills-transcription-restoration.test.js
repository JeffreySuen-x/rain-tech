import {readFileSync} from 'node:fs'
import {it,expect,vi} from 'vitest'
const source=readFileSync(new URL('../src/agriculture/AgricultureWorkbench.vue',import.meta.url),'utf8')
it('skills survive thread view navigation but reject late account results and permit retry',async()=>{
 const code=source.slice(source.indexOf('let skillsRequest = 0'),source.indexOf('\nconst selectedSkill')).replace(/watch\([^\n]+\n/,'')
 const s={sessionEpoch:1,user:{id:'a'},viewEpoch:1};const skills={value:[]},skillsError={value:''};let finish;const request=vi.fn(()=>new Promise(resolve=>finish=resolve));const load=new Function('s','skills','skillsError','request',code+';return loadSkills')(s,skills,skillsError,request)
 let pending=load();s.viewEpoch++;finish({skills:[{id:'all-seven'}]});await pending;expect(skills.value[0].id).toBe('all-seven')
 pending=load();s.sessionEpoch++;s.user={id:'b'};finish({skills:[{id:'stale'}]});await pending;expect(skills.value[0].id).toBe('all-seven')
 request.mockRejectedValueOnce(new Error('synthetic'));await load();expect(skillsError.value).toContain('重试');request.mockResolvedValueOnce({skills:[{id:'retry'}]});await load();expect(skillsError.value).toBe('');expect(skills.value[0].id).toBe('retry')
})
it('only explicitly pending transcription appends once; historical artifact never replays',()=>{
 const code=source.match(/watch\(\[\(\) => s.artifact\?\.id, transcribingTurnId\], \(\) => \{([\s\S]*?)\n\}\);/)[1]
 const s={artifact:{id:'old',turnId:'old',body:'historical'}};const pending={value:''},draft={value:'mine'},notice={value:''};const run=new Function('s','transcribingTurnId','draft','notice',code).bind(null,s,pending,draft,notice)
 run();expect(draft.value).toBe('mine');pending.value='fresh';s.artifact={id:'new',turnId:'fresh',body:'fresh text'};run();run();expect(draft.value).toBe('mine\n\nfresh text');expect(pending.value).toBe('')
})
it('processAsset fences late navigation and direct drafts do not arm replay',async()=>{
 const code=source.slice(source.indexOf('async function processAsset('),source.indexOf('\nfunction complete(',source.indexOf('async function processAsset(')))
 async function fixture(navigate,direct){
  const s={threadId:'thread',sessionEpoch:1,turns:[]};const draft={value:'mine'},pending={value:''};const gardenId={value:'w'},notice={value:''};let finish
  const write=()=>new Promise(resolve=>finish=resolve)
  const run=new Function('s','draft','gardenId','write','mediaTurnId','mediaAssetId','tab','transcribingTurnId','notice','refresh',code+';return processAsset')(s,draft,gardenId,write,{value:''},{value:''},{value:'chat'},pending,notice,async()=>{})
  const task=run({id:'audio',kind:'audio'},'transcribe');if(navigate)s.threadId='elsewhere';finish({turn:{id:'fresh'},...(direct?{draft:'new text'}:{})});await task;return {draft,pending,notice,s}
 }
 const direct=await fixture(false,true);expect(direct.draft.value).toBe('mine\n\nnew text');expect(direct.pending.value).toBe('')
 const queued=await fixture(false,false);expect(queued.pending.value).toBe('fresh');expect(queued.draft.value).toBe('mine')
 const late=await fixture(true,true);expect(late.draft.value).toBe('mine');expect(late.pending.value).toBe('');expect(late.s.turns).toEqual([])
})
