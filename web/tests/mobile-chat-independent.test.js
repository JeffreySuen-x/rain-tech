import { expect, it, vi } from 'vitest'
import { ref, computed } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspace } from '../src/store.js'
import { request } from '../src/api.js'
vi.mock('../src/api.js',()=>({request:vi.fn()}))
import { readFileSync } from 'node:fs'
// Execute the production handler, with isolated synthetic state and no network.
function fixture() {
 const source=readFileSync(new URL('../src/agriculture/AgricultureWorkbench.vue',import.meta.url),'utf8')
 const start=source.indexOf('async function startNewChat()')
 const end=source.indexOf('function createAnswerTask',start)
 const s={sessionEpoch:1,workspaceId:'w',threadId:'old',messages:[{role:'user'}],turns:[],prompt:'草稿',includeHistory:true,skillId:'skill',error:'',pendingThread:null}
 const refs=Object.fromEntries(['toolsOpen','creatingThread','loading','generating','busy','pendingMutation','resourcesOpen'].map(k=>[k,ref(false)]))
 Object.assign(refs,{gardenId:ref('w'),notice:ref(''),tab:ref('garden'),assetIds:ref(['a']),knowledgeIds:ref(['k'])})
 refs.newChatBlocked=computed(()=>refs.creatingThread.value||refs.loading.value||s.loading||refs.generating.value||!!s.pending||refs.busy.value||!!refs.pendingMutation.value)
 const closeDrawer=vi.fn(); const names=['s','closeDrawer',...Object.keys(refs)]
 const run=new Function(...names,source.slice(start,end)+';return startNewChat')(s,closeDrawer,...Object.values(refs))
 return {s,run,...refs}
}
it('independent: creates immediately with default title, preserves unsent choices without submission',async()=>{
 const f=fixture(); f.s.createThread=vi.fn(async()=>{f.s.prompt='';f.s.includeHistory=false;f.s.skillId='default';f.s.threadId='new';return true})
 await f.run();expect(f.s.createThread).toHaveBeenCalledExactlyOnceWith('新对话');expect(f.s.prompt).toBe('草稿');expect(f.s.includeHistory).toBe(true);expect(f.s.skillId).toBe('skill');expect(f.assetIds.value).toEqual(['a']);expect(f.tab.value).toBe('chat');expect(f.creatingThread.value).toBe(false)
})
it('independent: dedicated creation lock rejects duplicate while awaiting result',async()=>{
 const f=fixture();let finish;f.s.createThread=vi.fn(()=>new Promise(resolve=>finish=resolve));const pending=f.run();await f.run();expect(f.s.createThread).toHaveBeenCalledTimes(1);finish(false);await pending;expect(f.s.prompt).toBe('草稿');expect(f.creatingThread.value).toBe(false)
})
it('independent: an empty conversation is reused, but unresolved creation remains retryable',async()=>{
 const f=fixture();f.s.messages=[];f.s.createThread=vi.fn(async()=>false);await f.run();expect(f.s.createThread).not.toHaveBeenCalled();expect(f.tab.value).toBe('chat');f.s.pendingThread={commandId:'unchanged'};await f.run();expect(f.s.createThread).toHaveBeenCalledTimes(1);expect(f.s.pendingThread.commandId).toBe('unchanged')
})
it('independent: late success cannot restore an old workspace draft',async()=>{
 const f=fixture();let finish;f.s.createThread=()=>new Promise(resolve=>finish=resolve);const pending=f.run();f.s.workspaceId='other';f.s.prompt='新园区';f.assetIds.value=[];finish(true);await pending;expect(f.s.prompt).toBe('新园区');expect(f.assetIds.value).toEqual([])
})
it.each(['loading','generating','busy','pendingMutation'])('independent: %s blocks creation',async key=>{
 const f=fixture();f[key].value=true;f.s.createThread=vi.fn();await f.run();expect(f.s.createThread).not.toHaveBeenCalled()
})
it('independent: a detail-load failure after creation still preserves the unsent draft',async()=>{
 const f=fixture();f.s.createThread=vi.fn(async()=>{f.s.threadId='created';f.s.prompt='';f.s.error='读取失败';return true});await f.run();expect(f.s.prompt).toBe('草稿');expect(f.s.error).toBe('读取失败');expect(f.notice.value).not.toContain('未发送内容已保留')
})
it('independent: empty conversation reuse closes the resource panel',async()=>{
 const f=fixture();f.s.messages=[];f.resourcesOpen.value=true;await f.run();expect(f.resourcesOpen.value).toBe(false)
})

it('independent: real store rejects late thread creation after same-workspace history navigation',async()=>{
 setActivePinia(createPinia());const s=useWorkspace();s.user={id:'synthetic'};s.workspaceId='w';s.threadId='old';s.prompt='old draft';let finish;
 request.mockImplementation(path=>path.endsWith('/threads')?new Promise(resolve=>finish=resolve):Promise.resolve({messages:[],turns:[]}));
 const creating=s.createThread('新对话');await s.selectThread('history');s.prompt='history draft';finish({thread:{id:'created',title:'新对话'}});expect(await creating).toBe(false);expect(s.threadId).toBe('history');expect(s.prompt).toBe('history draft')
})
it('independent: six production tool actions route locally and close the panel',()=>{
 const source=readFileSync(new URL('../src/agriculture/AgricultureWorkbench.vue',import.meta.url),'utf8');const expression=source.match(/v-for="tool in (\[.*?\])"/)[1];const chooseUpload=vi.fn(),open=vi.fn();let voiceOpen=false;
 const result=new Function('chooseUpload','open',`let voiceOpen=false; return {tools:${expression}, recording:()=>voiceOpen}`)(chooseUpload,open); const tools=result.tools;
 const toolsOpen=ref(true);const actionSource=source.match(/function toolAction\(action\) \{[^}]+\}/)[0];const toolAction=new Function('toolsOpen',actionSource+';return toolAction')(toolsOpen);
 expect(tools.map(t=>t.label)).toEqual(['拍照 / 相册','录制语音','录音文件','上传资料','待办','设置']);
 for(const tool of tools){toolsOpen.value=true;toolAction(tool.action);expect(toolsOpen.value).toBe(false)}
 expect(result.recording()).toBe(true);expect(chooseUpload.mock.calls).toEqual([['image'],['audio'],['document']]);expect(open.mock.calls).toEqual([['task'],['settings']]);
})
it('independent: current context is a native labelled button, locked during creation',()=>{
 const source=readFileSync(new URL('../src/agriculture/AgricultureWorkbench.vue',import.meta.url),'utf8');const button=source.match(/<button[^>]*class="mobile-context-pill"[^>]*>/)?.[0];expect(button).toContain('aria-label="查看当前园区与对话资料"');expect(button).toContain(':disabled="creatingThread"');expect(button).toContain('@click="resourcesOpen = true"')
})
