import { defineStore } from 'pinia'
import { request } from './api.js'
export const activeStatuses = ['queued', 'running']
const terminalStatuses = ['completed', 'failed', 'cancelled', 'needs_review']
function mergeTurn(previous, incoming) {
  // Server transitions are terminal. An earlier GET may arrive after cancel
  // or completion; it must never replace a terminal receipt in this view.
  if (previous && terminalStatuses.includes(previous.status) && incoming.status !== previous.status) return previous
  return { ...previous, ...incoming }
}
function mergeTurns(previous, incoming) {
  const byId = new Map(previous.map(turn => [turn.id, turn]))
  const received = new Set(incoming.map(turn => turn.id))
  return [...incoming.map(turn => mergeTurn(byId.get(turn.id), turn)), ...previous.filter(turn => !received.has(turn.id))]
}
export const statusNames = { queued: '等待执行', running: '正在思考', completed: '已完成', failed: '未完成', cancelled: '已取消', needs_review: '需要核对' }
const id = () => globalThis.crypto.randomUUID()
const navigation = () => typeof window === 'undefined' ? new URLSearchParams() : new URLSearchParams(window.location.search)
function rememberNavigation(workspaceId = '', threadId = '') {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  for (const [key, value] of [['workspace', workspaceId], ['thread', threadId]]) { if (value) url.searchParams.set(key, value); else url.searchParams.delete(key) }
  window.history.replaceState(null, '', url)
}
export const useWorkspace = defineStore('workspace', {
  state: () => ({
    user: null, csrf: '', booting: true, busy: false, error: '', notice: '', sessionEpoch: 0, viewEpoch: 0,
    workspaces: [], workspaceId: '', threads: [], threadId: '', messages: [], turns: [], memories: [], selectedMemories: [],
    pendingWorkspace: null, pendingThread: null, pendingThreads: {}, prompt: '', background: '', agricultureContext: null, includeHistory: false, skillId: 'shuyu.analyze.v1', pending: null, submitting: false, loading: false, polling: false, pollError: '', artifact: null, reportTurnId: '',
  }),
  getters: {
    workspace: s => s.workspaces.find(w => w.id === s.workspaceId),
    thread: s => s.threads.find(t => t.id === s.threadId),
    latestTurn: s => s.turns.at(-1),
    activeTurn: s => [...s.turns].reverse().find(t => activeStatuses.includes(t.status)),
  },
  actions: {
    stamp() { return `${this.sessionEpoch}:${this.viewEpoch}` },
    current(stamp) { return this.stamp() === stamp && !!this.user },
    clearView() {
      this.viewEpoch++; this.threadId = ''; this.messages = []; this.turns = []; this.memories = []; this.selectedMemories = []
      this.prompt = ''; this.background = ''; this.agricultureContext = null; this.includeHistory = false; this.skillId = 'shuyu.analyze.v1'; this.pending = null; this.artifact = null; this.reportTurnId = ''
      this.error = ''; this.notice = ''; this.pollError = ''; this.loading = false; this.submitting = false; this.polling = false
    },
    clearSession() {
      this.sessionEpoch++; this.clearView(); rememberNavigation(); this.pendingWorkspace = null; this.pendingThread = null; this.pendingThreads = {}; this.user = null; this.csrf = ''; this.workspaces = []; this.workspaceId = ''; this.threads = []
    },
    handleError(error, stamp) {
      if (stamp && !this.current(stamp)) return
      if (error.status === 401) { this.clearSession(); this.error = '登录已失效，请重新登录。' }
      else this.error = error.message || '操作未完成。'
    },
    async initialize() {
      try {
        const data = await request('/auth/me'); this.user = data.user; this.csrf = data.csrfToken
        await this.loadWorkspaces()
      } catch (e) {
        if (e.status !== 401) this.error = e.message
        try { this.csrf = (await request('/auth/csrf')).csrfToken } catch (csrfError) { this.error = csrfError.message }
      } finally { this.booting = false }
    },
    async login(username, password) {
      this.busy = true; this.error = ''
      try {
        if (!this.csrf) this.csrf = (await request('/auth/csrf')).csrfToken
        const data = await request('/auth/login', { method: 'POST', csrf: this.csrf, body: { username, password } })
        this.clearSession(); this.user = data.user; this.csrf = data.csrfToken; await this.loadWorkspaces()
      } catch (e) { this.error = e.message; try { this.csrf = (await request('/auth/csrf')).csrfToken } catch { /* retain visible original error */ } }
      finally { this.busy = false }
    },
    async logout() {
      this.busy = true
      try { await request('/auth/logout', { method: 'POST', csrf: this.csrf, body: {} }); this.clearSession() }
      catch (e) { this.handleError(e) } finally { this.busy = false }
    },
    async loadWorkspaces() {
      const session = this.sessionEpoch
      const data = await request('/workspaces')
      if (session !== this.sessionEpoch || !this.user) return
      this.workspaces = data.workspaces
      if (this.workspaces.length) {
        const saved = navigation(); const wid = this.workspaces.some(w => w.id === saved.get('workspace')) ? saved.get('workspace') : this.workspaces[0].id
        await this.selectWorkspace(wid, saved.get('thread'))
      }
    },
    async createWorkspace(name) {
      const stamp = this.stamp(); this.error = ''
      try {
        if (this.pendingWorkspace && this.pendingWorkspace.name !== name) { this.error = '上一园区创建结果未确认，请用原名称核对。'; return false }
        this.pendingWorkspace ||= { name, commandId: id() }
        const data = await request('/workspaces', { method: 'POST', csrf: this.csrf, body: this.pendingWorkspace })
        if (!this.current(stamp)) return false
        this.pendingWorkspace = null; if (!this.workspaces.some(w => w.id === data.workspace.id)) this.workspaces.push(data.workspace); await this.selectWorkspace(data.workspace.id); return true
      } catch (e) { if (this.current(stamp) && e.status > 0 && e.status < 500) this.pendingWorkspace = null; this.handleError(e, stamp); return false }
    },
    async selectWorkspace(workspaceId, preferredThreadId = '') {
      if (this.pendingThread) this.pendingThreads[this.pendingThread.workspaceId] = this.pendingThread
      this.pendingThread = this.pendingThreads[workspaceId] || null
      this.clearView(); this.workspaceId = workspaceId; rememberNavigation(workspaceId); this.threads = []; this.loading = true
      const stamp = this.stamp()
      try {
        const [threads, memories] = await Promise.all([request(`/workspaces/${encodeURIComponent(workspaceId)}/threads`), request(`/workspaces/${encodeURIComponent(workspaceId)}/memories`)])
        if (!this.current(stamp)) return
        this.threads = threads.threads; this.memories = memories.memories
        if (this.threads.length) await this.selectThread(this.threads.some(t => t.id === preferredThreadId) ? preferredThreadId : this.threads[0].id)
      } catch (e) { this.handleError(e, stamp) } finally { if (this.current(stamp)) this.loading = false }
    },
    async createThread(title) {
      const stamp = this.stamp(); const wid = this.workspaceId; this.error = ''
      try {
        if (this.pendingThread && (this.pendingThread.title !== title || this.pendingThread.workspaceId !== wid)) { this.error = '上一对话创建结果未确认，请先核对原请求。'; return false }
        this.pendingThread ||= { title, workspaceId: wid, commandId: id() }
        this.pendingThreads[wid] = this.pendingThread
        const { workspaceId: _wid, ...threadBody } = this.pendingThread
        const data = await request(`/workspaces/${encodeURIComponent(wid)}/threads`, { method: 'POST', csrf: this.csrf, body: threadBody })
        if (!this.current(stamp)) return false
        this.pendingThread = null; delete this.pendingThreads[wid]; if (!this.threads.some(t => t.id === data.thread.id)) this.threads.unshift(data.thread); await this.selectThread(data.thread.id); return this.workspaceId === wid && this.threadId === data.thread.id
      } catch (e) { if (this.current(stamp) && e.status > 0 && e.status < 500) { this.pendingThread = null; delete this.pendingThreads[wid] } this.handleError(e, stamp); return false }
    },
    async selectThread(threadId) {
      const memories = this.memories
      this.clearView(); this.memories = memories; this.threadId = threadId; rememberNavigation(this.workspaceId, threadId); this.loading = true
      const stamp = this.stamp()
      try {
        const data = await request(`/threads/${encodeURIComponent(threadId)}`)
        if (!this.current(stamp)) return
        this.messages = data.messages; this.turns = data.turns
        if (this.latestTurn?.artifactId) await this.openReport(this.latestTurn)
      } catch (e) { this.handleError(e, stamp) } finally { if (this.current(stamp)) this.loading = false }
    },
    async submit(retry = false) {
      if (this.submitting || this.activeTurn || !this.threadId) return false
      if (!retry) {
        if (!this.prompt.trim() || this.pending) return false
        this.pending = { threadId: this.threadId, commandId: id(), includeHistory: this.includeHistory === true, skillId: this.skillId, prompt: this.prompt.trim(), background: this.background.trim(), memoryIds: [...this.selectedMemories], ...(this.agricultureContext ? { agricultureContext: { ...(this.agricultureContext.plotId ? { plotId: this.agricultureContext.plotId } : {}), assetIds: [...(this.agricultureContext.assetIds || [])], knowledgeIds: [...(this.agricultureContext.knowledgeIds || [])] } } : {}) }
      }
      const payload = this.pending
      if (!payload || payload.threadId !== this.threadId) return false
      const stamp = this.stamp(); this.submitting = true; this.error = ''; this.artifact = null; this.reportTurnId = ''
      try {
        const { threadId, ...body } = payload
        const data = await request(`/threads/${encodeURIComponent(threadId)}/turns`, { method: 'POST', csrf: this.csrf, body })
        if (!this.current(stamp)) return false
        if (!this.turns.some(t => t.id === data.turn.id)) this.turns.push(data.turn)
        this.prompt = ''; this.background = ''; this.selectedMemories = []; this.pending = null
        await this.refreshMessages(stamp, threadId)
        return true
      } catch (e) {
        if (this.current(stamp)) {
          // A transport failure may follow a committed request. Retain exactly the
          // same command and frozen inputs; only an explicit retry resends it.
          if (e.status > 0 && e.status < 500) this.pending = null
          this.handleError(e, stamp)
        }
        return false
      } finally { if (this.current(stamp)) this.submitting = false }
    },
    async refreshMessages(stamp, threadId) {
      try {
        const data = await request(`/threads/${encodeURIComponent(threadId)}`)
        if (this.current(stamp) && this.threadId === threadId) { this.messages = data.messages; this.turns = mergeTurns(this.turns, data.turns) }
      } catch (e) { if (this.current(stamp)) { if (e.status === 401) this.handleError(e, stamp); else this.pollError = e.message } }
    },
    async poll() {
      if (!this.activeTurn || this.polling || !this.user) return
      const stamp = this.stamp(); const turnId = this.activeTurn.id; const threadId = this.threadId
      this.polling = true
      try {
        const data = await request(`/turns/${encodeURIComponent(turnId)}`)
        if (!this.current(stamp)) return
        this.pollError = ''
        this.turns = this.turns.map(t => t.id === turnId ? mergeTurn(t, data.turn) : t)
        if (!activeStatuses.includes(data.turn.status)) {
          await this.refreshMessages(stamp, threadId)
          if (this.current(stamp) && data.turn.artifactId) await this.openReport(data.turn)
        }
      } catch (e) {
        if (this.current(stamp)) { if (e.status === 401) this.handleError(e, stamp); else this.pollError = e.message }
      } finally { if (this.current(stamp)) this.polling = false }
    },
    async cancel(turn) {
      const stamp = this.stamp(); this.error = ''
      try {
        const data = await request(`/turns/${encodeURIComponent(turn.id)}/cancel`, { method: 'POST', csrf: this.csrf, body: { commandId: id() } })
        if (this.current(stamp)) this.turns = this.turns.map(t => t.id === turn.id ? mergeTurn(t, data.turn) : t)
      } catch (e) { this.handleError(e, stamp) }
    },
    async openReport(turn) {
      const stamp = this.stamp(); this.reportTurnId = turn.id; this.artifact = null
      try {
        const data = await request(`/artifacts/${encodeURIComponent(turn.artifactId)}`)
        if (this.current(stamp) && this.reportTurnId === turn.id && data.artifact.turnId === turn.id && data.artifact.threadId === this.threadId) this.artifact = data.artifact
      } catch (e) { this.handleError(e, stamp) }
    },
    async saveMemory(content, sourceTurnId) {
      const stamp = this.stamp(); this.error = ''
      try {
        const data = await request(`/workspaces/${encodeURIComponent(this.workspaceId)}/memories`, { method: 'POST', csrf: this.csrf, body: { commandId: id(), content, ...(sourceTurnId ? { sourceTurnId } : {}) } })
        if (!this.current(stamp)) return false
        if (!this.memories.some(m => m.id === data.memory.id)) this.memories.unshift(data.memory)
        this.notice = '已保存到当前工作区记忆。下次提问时可显式选用。'; return true
      } catch (e) { this.handleError(e, stamp); return false }
    },
    async deleteMemory(memoryId) {
      const stamp = this.stamp(); this.error = ''
      try {
        await request(`/memories/${encodeURIComponent(memoryId)}`, { method: 'DELETE', csrf: this.csrf })
        if (this.current(stamp)) { this.memories = this.memories.filter(m => m.id !== memoryId); this.selectedMemories = this.selectedMemories.filter(i => i !== memoryId); this.notice = '记忆已删除。' }
      } catch (e) { this.handleError(e, stamp) }
    },
  },
})
