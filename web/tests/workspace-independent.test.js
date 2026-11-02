import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspace } from '../src/store.js'
import { request } from '../src/api.js'
vi.mock('../src/api.js', () => ({ request: vi.fn() }))
let s
beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks(); s = useWorkspace(); s.user = {id:'independent-owner'}; s.csrf='csrf'; s.workspaceId='w1'; s.threadId='t1' })
it('independent: opt-in history resets for thread, workspace and logout', async () => {
 expect(s.includeHistory).toBe(false)
 request.mockImplementation(path => Promise.resolve(path.endsWith('/memories') ? {memories:[]} : path.endsWith('/threads') ? {threads:[]} : {messages:[],turns:[]}))
 s.includeHistory=true; s.skillId='shuyu.knowledge.v1'; await s.selectThread('t2')
 expect(s.includeHistory).toBe(false); expect(s.skillId).toBe('shuyu.analyze.v1')
 s.includeHistory=true; await s.selectWorkspace('w2'); expect(s.includeHistory).toBe(false)
 s.includeHistory=true; s.clearSession(); expect(s.includeHistory).toBe(false)
})
it('independent: uncertain retry freezes skill, history and explicit references', async () => {
 s.prompt='original'; s.skillId='shuyu.inspection.v1'; s.includeHistory=true; s.agricultureContext={plotId:'p',assetIds:['a'],knowledgeIds:['k']}
 let attempts=0
 request.mockImplementation(path => path.endsWith('/turns') ? ++attempts === 1 ? Promise.reject(Object.assign(new Error('offline'),{status:0})) : Promise.resolve({turn:{id:'turn',status:'queued'}}) : Promise.resolve({messages:[],turns:[]}))
 await s.submit(); const original=JSON.parse(JSON.stringify(request.mock.calls[0][1].body))
 s.skillId='shuyu.report.v1'; s.includeHistory=false; s.prompt='different'; s.agricultureContext={assetIds:[],knowledgeIds:[]}
 await s.submit(true)
 const submissions=request.mock.calls.filter(([path])=>path.endsWith('/turns'))
 expect(submissions).toHaveLength(2); expect(submissions[1][1].body).toEqual(original)
 expect(original).toMatchObject({skillId:'shuyu.inspection.v1',includeHistory:true,agricultureContext:{plotId:'p',assetIds:['a'],knowledgeIds:['k']}})
})
