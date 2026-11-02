import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspace } from '../src/store.js'
import { request } from '../src/api.js'
import { agricultureRead, agricultureWrite, agricultureAssetContentUrl } from '../src/agriculture/api.js'
vi.mock('../src/api.js', () => ({ request: vi.fn() }))
beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks() })
describe('independent agriculture lifecycle', () => {
  it('freezes agriculture selection with the original uncertain chat command', async () => {
    const s = useWorkspace(); s.user={id:'owner'};s.csrf='csrf';s.workspaceId='w';s.threadId='thread';s.prompt='叶片情况';s.agricultureContext={plotId:'p1',assetIds:['a1'],knowledgeIds:['k1']}
    let calls=0
    request.mockImplementation(path => path.endsWith('/turns') ? (++calls === 1 ? Promise.reject(Object.assign(new Error('unknown'),{status:0})) : Promise.resolve({turn:{id:'turn',status:'queued'}})) : Promise.resolve({messages:[],turns:[{id:'turn',status:'queued'}]}))
    await s.submit(); const original=JSON.parse(JSON.stringify(s.pending));
    s.agricultureContext.assetIds.push('late');s.agricultureContext.plotId='other';await s.submit(true)
    expect(request.mock.calls.filter(([path]) => path.endsWith('/turns'))[1][1].body).toMatchObject({commandId:original.commandId,agricultureContext:{plotId:'p1',assetIds:['a1'],knowledgeIds:['k1']}})
  })
  it('uses independent API entities and explicit command identity for JSON and multipart', async () => {
    request.mockResolvedValue({plot:{id:'p'}})
    await agricultureWrite('workspaces/w/plots',{commandId:'original',name:'西地块'},'csrf')
    expect(request).toHaveBeenLastCalledWith('/workspaces/w/plots',expect.objectContaining({csrf:'csrf',body:{commandId:'original',name:'西地块'}}))
    const file=new FormData();file.set('kind','image');await agricultureWrite('workspaces/w/assets',file,'csrf');const key=file.get('commandId');expect(key).toBeTruthy();await agricultureWrite('workspaces/w/assets',file,'csrf');expect(file.get('commandId')).toBe(key)
    expect(agricultureAssetContentUrl('w','a/safe')).toBe('/api/v1/assets/a%2Fsafe/content')
    await agricultureRead('devices/d/readings');expect(request).toHaveBeenLastCalledWith('/devices/d/readings',{signal:undefined})
  })
  it('does not retry a rejected domain mutation', async () => {
    request.mockRejectedValue(Object.assign(new Error('尚未配置视觉能力'),{code:'capability_unconfigured',status:503}))
    await expect(agricultureWrite('assets/a/analyze',{threadId:'t'},'csrf')).rejects.toMatchObject({code:'capability_unconfigured'})
    expect(request).toHaveBeenCalledTimes(1)
  })
})
it('retains the same creation command for an uncertain workspace or conversation', async () => {
  const s=useWorkspace();s.user={id:'owner'};s.csrf='csrf';s.workspaceId='w';s.threadId='thread';
  request.mockRejectedValue(Object.assign(new Error('unknown'),{status:0}))
  await s.createWorkspace('园区');const workspaceCommand=s.pendingWorkspace.commandId;await s.createWorkspace('园区');expect(s.pendingWorkspace.commandId).toBe(workspaceCommand)
  await s.createThread('叶片观察');const threadCommand=s.pendingThread.commandId;await s.createThread('叶片观察');expect(s.pendingThread.commandId).toBe(threadCommand)
  const writes=request.mock.calls.filter(([,options])=>options?.method==='POST');expect(writes[0][1].body.commandId).toBe(writes[1][1].body.commandId);expect(writes[2][1].body.commandId).toBe(writes[3][1].body.commandId)
})
it('history authorization clears on conversation, garden and session changes',async()=>{
  const s=useWorkspace();s.user={id:'owner'};s.workspaceId='w';s.threadId='thread';request.mockImplementation(path=>Promise.resolve(path.endsWith('/memories')?{memories:[]}:path.endsWith('/threads')?{threads:[]}:{messages:[],turns:[]}))
  expect(s.includeHistory).toBe(false);s.includeHistory=true;await s.selectThread('other');expect(s.includeHistory).toBe(false)
  s.includeHistory=true;await s.selectWorkspace('other-garden');expect(s.includeHistory).toBe(false)
  s.includeHistory=true;s.clearSession();expect(s.includeHistory).toBe(false)
})
