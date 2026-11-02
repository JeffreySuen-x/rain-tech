import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useWorkspace } from '../src/store.js'
import { request } from '../src/api.js'
vi.mock('../src/api.js', () => ({ request: vi.fn() }))
let s
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const baseThread = { messages: [], turns: [] }
beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks(); s = useWorkspace(); s.user = { id: 'u1', username: 'owner' }; s.csrf = 'csrf'; s.workspaceId = 'w1'; s.threadId = 't1' })
afterEach(() => vi.restoreAllMocks())
describe('request ownership and durable lifecycle', () => {
  it('ignores thread responses after another thread is selected', async () => {
    const old = deferred(); request.mockImplementation(path => path === '/threads/t1' ? old.promise : Promise.resolve({ messages: [{ id: 'new', content: 'new thread' }], turns: [] }))
    const first = s.selectThread('t1'); await s.selectThread('t2')
    old.resolve({ messages: [{ id: 'old', content: 'old thread' }], turns: [] }); await first
    expect(s.threadId).toBe('t2'); expect(s.messages[0].id).toBe('new')
  })
  it('ignores response even after an A to B to A workspace switch', async () => {
    const old = deferred(); let count = 0
    request.mockImplementation(path => path.endsWith('/threads') && count++ === 0 ? old.promise : Promise.resolve(path.endsWith('/memories') ? { memories: [] } : { threads: [] }))
    const first = s.selectWorkspace('a'); await s.selectWorkspace('b'); await s.selectWorkspace('a')
    old.resolve({ threads: [{ id: 'stale', title: 'wrong epoch' }] }); await first
    expect(s.workspaceId).toBe('a'); expect(s.threads).toEqual([])
  })
  it('freezes command ID, thread, prompt and memories for uncertain submission retry', async () => {
    s.prompt = 'first question'; s.background = 'original'; s.selectedMemories = ['m1']
    let firstBody
    request.mockImplementation((path, options) => {
      if (path.endsWith('/turns')) { firstBody ||= JSON.parse(JSON.stringify(options.body)); if (request.mock.calls.filter(c => c[0].endsWith('/turns')).length === 1) return Promise.reject(Object.assign(new Error('offline'), { status: 0 })); return Promise.resolve({ turn: { id: 'turn1', status: 'queued' } }) }
      return Promise.resolve({ messages: [], turns: [{ id: 'turn1', status: 'queued' }] })
    })
    await s.submit(); expect(s.pending.commandId).toBe(firstBody.commandId)
    s.prompt = 'edited'; s.background = 'edited'; s.selectedMemories = []
    await s.submit(true)
    const submissions = request.mock.calls.filter(c => c[0].endsWith('/turns'))
    expect(submissions[1][0]).toBe('/threads/t1/turns'); expect(submissions[1][1].body).toEqual(firstBody)
    expect(s.pending).toBeNull(); expect(s.activeTurn.id).toBe('turn1')
  })
  it('does not write a submission response into a newly selected thread', async () => {
    const submitting = deferred(); request.mockImplementation(path => path.endsWith('/turns') ? submitting.promise : Promise.resolve(baseThread))
    s.prompt = 'question'; const first = s.submit(); await s.selectThread('t2')
    submitting.resolve({ turn: { id: 'oldTurn', status: 'queued' } }); await first
    expect(s.threadId).toBe('t2'); expect(s.turns).toEqual([]); expect(s.pending).toBeNull()
  })
  it('restores queued task from the server after a fresh store loads a thread', async () => {
    request.mockResolvedValue({ messages: [], turns: [{ id: 'persisted', status: 'running' }] })
    await s.selectThread('t1'); expect(s.activeTurn.id).toBe('persisted')
  })
  it('does not relabel a historical report as the newest result on new submission', async () => {
    s.artifact = { id: 'old' }; s.reportTurnId = 'oldTurn'; s.prompt = 'new question'
    request.mockImplementation(path => path.endsWith('/turns') ? Promise.resolve({ turn: { id: 'newTurn', status: 'queued' } }) : Promise.resolve({ messages: [], turns: [{ id: 'newTurn', status: 'queued' }] }))
    await s.submit(); expect(s.artifact).toBeNull(); expect(s.reportTurnId).toBe('')
  })
  it('does not keep polling completed tasks or automatically retry needs_review', async () => {
    s.turns = [{ id: 't', status: 'running' }]
    request.mockImplementation(path => path.startsWith('/turns/') ? Promise.resolve({ turn: { id: 't', status: 'needs_review' } }) : Promise.resolve({ messages: [], turns: [{ id: 't', status: 'needs_review' }] }))
    await s.poll(); expect(s.latestTurn.status).toBe('needs_review'); expect(s.activeTurn).toBeUndefined()
    const calls = request.mock.calls.length; await s.poll(); expect(request).toHaveBeenCalledTimes(calls)
  })
  it('does not allow unbound or cross-thread artifact responses', async () => {
    request.mockResolvedValue({ artifact: { id: 'a', turnId: 'other', threadId: 't1', body: 'unsafe scope' } })
    await s.openReport({ id: 'turn', artifactId: 'a' }); expect(s.artifact).toBeNull()
  })
  it('rejects stale polling responses after logout', async () => {
    s.turns = [{ id: 'turn', status: 'running' }]; const old = deferred(); request.mockReturnValue(old.promise)
    const poll = s.poll(); s.clearSession(); old.resolve({ turn: { id: 'turn', status: 'completed', artifactId: 'a' } }); await poll
    expect(s.user).toBeNull(); expect(s.turns).toEqual([]); expect(s.artifact).toBeNull()
  })
  it('keeps a model configuration failure visible as a failed task', async () => {
    s.turns = [{ id: 'turn', status: 'running' }]
    const turn = { id: 'turn', status: 'failed', error: { code: 'model_not_configured', message: '请配置模型' } }
    request.mockImplementation(path => Promise.resolve(path.startsWith('/turns/') ? { turn } : { messages: [], turns: [turn] }))
    await s.poll(); expect(s.latestTurn.error.message).toBe('请配置模型'); expect(s.latestTurn.status).toBe('failed')
  })
  it('sends cancel with CSRF and an explicit command ID', async () => {
    s.turns = [{ id: 'turn', status: 'running' }]; request.mockResolvedValue({ turn: { id: 'turn', status: 'cancelled' } })
    await s.cancel(s.turns[0]); expect(request.mock.calls[0][1]).toMatchObject({ method: 'POST', csrf: 'csrf', body: { commandId: expect.any(String) } }); expect(s.activeTurn).toBeUndefined()
  })
  it('deleting a memory removes it from explicitly selected inputs', async () => {
    s.memories = [{ id: 'm1' }]; s.selectedMemories = ['m1']; request.mockResolvedValue(null)
    await s.deleteMemory('m1'); expect(s.memories).toEqual([]); expect(s.selectedMemories).toEqual([])
  })
})

describe('terminal receipts are monotone within one view', () => {
  it('does not regress cancelled to running when an earlier poll arrives late', async () => {
    const oldPoll = deferred(); s.turns = [{ id: 'turn', status: 'running' }]
    request.mockImplementation(path => path.endsWith('/cancel') ? Promise.resolve({ turn: { id: 'turn', status: 'cancelled' } }) : oldPoll.promise)
    const poll = s.poll(); await s.cancel(s.turns[0]); expect(s.latestTurn.status).toBe('cancelled')
    oldPoll.resolve({ turn: { id: 'turn', status: 'running' } }); await poll
    expect(s.latestTurn.status).toBe('cancelled'); expect(s.activeTurn).toBeUndefined()
  })
  it('does not regress a terminal receipt through an older thread refresh snapshot', async () => {
    const oldThread = deferred(); s.turns = [{ id: 'turn', status: 'running' }]
    request.mockImplementation(path => path.endsWith('/cancel') ? Promise.resolve({ turn: { id: 'turn', status: 'cancelled' } }) : oldThread.promise)
    const refresh = s.refreshMessages(s.stamp(), 't1'); await s.cancel(s.turns[0])
    oldThread.resolve({ messages: [], turns: [{ id: 'turn', status: 'running' }] }); await refresh
    expect(s.latestTurn.status).toBe('cancelled')
  })
  it('does not lose a locally acknowledged turn omitted by an older snapshot', async () => {
    s.turns = [{ id: 'turn', status: 'queued' }]; request.mockResolvedValue({ messages: [], turns: [] })
    await s.refreshMessages(s.stamp(), 't1'); expect(s.latestTurn.id).toBe('turn')
  })
})

describe('workspace-scoped uncertain conversation creation', () => {
  it('allows B creation and resumes the original A command successfully', async () => {
    request.mockRejectedValueOnce(Object.assign(new Error('offline'), {status: 0}))
    await s.createThread('新对话'); const command = s.pendingThread.commandId
    request.mockImplementation((path, options) => {
      if (options?.method === 'POST') return Promise.resolve({thread: {id: path.includes('/w2/') ? 'b' : 'a', title: '新对话'}})
      if (path.startsWith('/threads/')) return Promise.resolve({messages: [], turns: []})
      return Promise.resolve(path.endsWith('/memories') ? {memories: []} : {threads: []})
    })
    await s.selectWorkspace('w2'); expect(s.pendingThread).toBeNull()
    expect(await s.createThread('新对话')).toBe(true); expect(s.threadId).toBe('b')
    expect(s.pendingThreads.w2).toBeUndefined()
    await s.selectWorkspace('w1'); expect(s.pendingThread.commandId).toBe(command)
    expect(await s.createThread('新对话')).toBe(true); expect(s.threadId).toBe('a')
    const calls = request.mock.calls.filter(([, options]) => options?.method === 'POST')
    expect(calls.at(-1)[1].body.commandId).toBe(command)
    expect(s.pendingThread).toBeNull(); expect(s.pendingThreads).toEqual({})
  })
  it('discards old account receipts and ignores a late creation response', async () => {
    const late = deferred(); request.mockReturnValueOnce(late.promise)
    const creating = s.createThread('新对话')
    expect(s.pendingThreads.w1).toBeTruthy()
    s.clearSession(); s.user = {id: 'new-owner'}; s.workspaceId = 'new-workspace'; s.threadId = 'new-thread'; s.prompt = 'new draft'
    late.resolve({thread: {id: 'old-created', title: '新对话'}})
    expect(await creating).toBe(false)
    expect(s.threadId).toBe('new-thread'); expect(s.prompt).toBe('new draft')
    expect(s.threads).toEqual([]); expect(s.pendingThreads).toEqual({}); expect(s.pendingThread).toBeNull()
  })
})
