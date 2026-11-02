import { ref, watch, onBeforeUnmount } from 'vue'
import { request } from '../api.js'
export function useLiveDemo(scope, csrf) {
  const live = ref(null), error = ref(''), pending = ref(false), uncertain = ref(false), pendingRequest = ref(null)
  let epoch = 0, controller, timer, disposed = false
  const path = () => `/workspaces/${encodeURIComponent(scope().workspaceId)}/live-demo`
  const accept = data => { if (!data || !live.value || data.version >= live.value.version) live.value = data }
  async function refresh() {
    const token = epoch
    if (!scope().workspaceId || document.hidden || disposed) return
    controller?.abort(); controller = new AbortController()
    try {
      const plot = scope().plotId
      const data = await request(`${path()}${plot ? `?plotId=${encodeURIComponent(plot)}` : ''}`, {signal:controller.signal})
      if (token === epoch) { accept(data.liveDemo); error.value = '' }
    } catch (e) { if (token === epoch && e.name !== 'AbortError') error.value = e.message }
  }
  async function perform(receipt) {
    const token = epoch
    pending.value = true; error.value = ''
    try {
      const data = await request(`${receipt.url}/actions`, {method:'POST',body:receipt.body,csrf:csrf()})
      if (token === epoch) { accept(data.liveDemo); uncertain.value = false; pendingRequest.value = null }
    } catch (e) {
      if (token === epoch) {
        error.value = e.message; uncertain.value = !e.status || e.status >= 500
        if (!uncertain.value) pendingRequest.value = null
      }
    } finally { if (token === epoch) pending.value = false }
  }
  async function action(action, extra = {}) {
    if (!live.value?.enabled || pending.value || uncertain.value) return
    const receipt = {url:path(),body:{commandId:crypto.randomUUID(),action,...(scope().plotId ? {plotId:scope().plotId} : {}),...extra}}
    pendingRequest.value = receipt
    await perform(receipt)
  }
  async function retry() { if (uncertain.value && pendingRequest.value && !pending.value) await perform(pendingRequest.value) }
  function schedule() { clearInterval(timer); if (!document.hidden && !disposed) { void refresh(); timer = setInterval(refresh, 5000) } }
  watch(() => JSON.stringify(scope()), () => { epoch++; controller?.abort(); live.value = null; pending.value = false; uncertain.value = false; pendingRequest.value = null; error.value = ''; schedule() }, {immediate:true})
  function visibility() { if (document.hidden) { clearInterval(timer); controller?.abort() } else schedule() }
  document.addEventListener('visibilitychange', visibility)
  onBeforeUnmount(() => {disposed=true;epoch++;controller?.abort();clearInterval(timer);document.removeEventListener('visibilitychange',visibility)})
  return {live,error,pending,uncertain,pendingRequest,refresh,action,retry,reconcile:refresh}
}
