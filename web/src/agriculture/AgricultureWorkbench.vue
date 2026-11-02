<script setup>
import MobileGarden from './MobileGarden.vue'
import MobileTaskFlow from './MobileTaskFlow.vue'
import FriendlyIcon from './FriendlyIcon.vue'
import ReportDocument from './ReportDocument.vue'
import VoiceRecorder from './VoiceRecorder.vue'
import { useLocalSpeech } from './useLocalSpeech.js'
import './friendly.css'
import BrandMark from '../BrandMark.js'
import LiveFieldPanel from './LiveFieldPanel.vue'
import KnowledgeLibrary from './KnowledgeLibrary.vue'
import KnowledgeReader from './KnowledgeReader.vue'
import { useLiveDemo } from './useLiveDemo.js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { request } from '../api.js'
import { useWorkspace, statusNames } from '../store.js'
import { agricultureWrite, agricultureRead, agricultureAssetContentUrl, readGarden } from './api.js'
import './workbench.css'
import './icons.css'
import { savedTurnError, assetStatusLabel, reportKindLabel, metricLabel, statusLabel, deviceKindLabel, observationSourceLabel, sourceRows, sourceText as readableSources } from './presentation.js'
import { displayDate, displayDay, displayMonth, displayLunar } from './calendarPresentation.js'
import './responsive.css'
import './mobile-workbench.css'
const mobileViewportHeight = ref(null)
function updateMobileViewport() { mobileViewportHeight.value = typeof window !== 'undefined' && window.innerWidth < 768 && window.visualViewport ? `${window.visualViewport.height}px` : null }
onMounted(() => { updateMobileViewport(); globalThis.window?.visualViewport?.addEventListener('resize', updateMobileViewport); globalThis.window?.addEventListener('resize', updateMobileViewport) })
onBeforeUnmount(() => { globalThis.window?.visualViewport?.removeEventListener('resize', updateMobileViewport); globalThis.window?.removeEventListener('resize', updateMobileViewport) })
const mobileTabs = [{id:'overview',label:'园区',icon:'house-door'},{id:'chat',label:'对话',icon:'chat'},{id:'knowledge',label:'学习',icon:'book'}]
const mobileMenuOpen = ref(false)
const drawerElement = ref(null), historyQuery = ref(''), drawerError = ref('')
const filteredHistory = computed(() => gardenThreads.value.filter(thread => String(thread.title || thread.name || '现场对话').toLocaleLowerCase().includes(historyQuery.value.trim().toLocaleLowerCase())))
let drawerTrigger, drawerRestore = true, drawerCleanup = () => {}
function closeDrawer(restore = true) { drawerRestore = restore; mobileMenuOpen.value = false }
function drawerAction(action) { previousFocus = drawerTrigger; closeDrawer(false); action() }
async function chooseHistory(thread) {
  if (creatingThread.value) return
  drawerError.value = ''
  const owner = s.sessionEpoch, workspace = s.workspaceId
  try { await s.selectThread(thread.id); if (owner !== s.sessionEpoch || workspace !== s.workspaceId || s.threadId !== thread.id) return; if (s.error) { drawerError.value = s.error; return }; tab.value = 'chat'; closeDrawer() }
  catch (failure) { if (owner !== s.sessionEpoch || workspace !== s.workspaceId) return; drawerError.value = failure.message || '对话读取失败，请重试' }
}
watch(mobileMenuOpen, async value => {
  if (!value) { drawerCleanup(); if (drawerRestore) drawerTrigger?.focus?.(); drawerRestore = true; return }
  drawerTrigger = document.activeElement
  await nextTick()
  if (!mobileMenuOpen.value) return
  const drawer = drawerElement.value
  const siblings = [...drawer.parentElement.children].filter(el => el !== drawer && !el.classList.contains('mobile-menu-shade'))
  const states = siblings.map(el => [el, el.inert]); siblings.forEach(el => { el.inert = true })
  const overflow = document.body.style.overflow; document.body.style.overflow = 'hidden'
  drawerCleanup = () => { states.forEach(([el, inert]) => { el.inert = inert }); document.body.style.overflow = overflow; drawerCleanup = () => {} }
  drawer.querySelector('button')?.focus()
})
function drawerKey(event) {
  if (!mobileMenuOpen.value) return
  if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); closeDrawer(); return }
  if (event.key !== 'Tab') return
  const elements = [...drawerElement.value.querySelectorAll('button:not(:disabled),input,select,[tabindex="0"]')]
  const first = elements[0], last = elements.at(-1)
  if (event.shiftKey && (document.activeElement === first || !drawerElement.value.contains(document.activeElement))) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && (document.activeElement === last || !drawerElement.value.contains(document.activeElement))) { event.preventDefault(); first?.focus() }
}
function drawerResize() { if (window.innerWidth >= 768) closeDrawer(false) }
onMounted(() => { document.addEventListener('keydown', drawerKey, true); globalThis.window?.addEventListener('resize', drawerResize) })
onBeforeUnmount(() => { drawerCleanup(); document.removeEventListener('keydown', drawerKey, true); globalThis.window?.removeEventListener('resize', drawerResize) })
const reportItem = ref(null), voiceOpen = ref(false), calendarOpen = ref(false)
const { speaking, speechMessage, speak, stop: stopSpeaking } = useLocalSpeech()
const s = useWorkspace()
watch(() => s.workspaceId, () => { historyQuery.value = ''; drawerError.value = '' })

const auth = { get userId() { return s.user ? `${s.sessionEpoch}:${s.user.id || s.user.username}` : null } }
const agricultureScopeMatches = (expected, current) => Boolean(expected.owner) && expected.owner === current.owner && expected.gardenId === current.gardenId
const fetchAssetContent = async url => { const response = await fetch(url, {credentials: 'same-origin'}); if (response.status === 401) throw Object.assign(new Error('登录已失效，请重新登录'), {status:401}); return response }
const tabs = [{ id: "overview", label: "\u56ED\u533A\u603B\u89C8", icon: "house-door" }, { id: "chat", label: "\u5BF9\u8BDD", icon: "chat" }, { id: "monitor", label: "\u56ED\u533A\u76D1\u63A7", icon: "bar-chart" }, { id: "tasks", label: "\u5F85\u529E\u4EFB\u52A1", icon: "clipboard-check" }, { id: "knowledge", label: "\u5B66\u4E60\u77E5\u8BC6\u5E93", icon: "book" }, { id: "devices", label: "\u519C\u4E1A\u8BBE\u5907", icon: "gear" }];
const tab = ref("overview"), gardens = computed(() => s.workspaces), gardenId = computed({get: () => s.workspaceId, set: value => s.selectWorkspace(value)}), overview = ref(null), plotId = ref("");
const { live: liveDemo, error: liveError, pending: livePending, uncertain: liveUncertain, action: liveAction, reconcile: liveReconcile, retry: liveRetry } = useLiveDemo(() => ({workspaceId:s.workspaceId, plotId:plotId.value, sessionEpoch:s.sessionEpoch}), () => s.csrf);
function liveExplain(text) { if (creatingThread.value) return; draft.value = text; notice.value = '问题已加入草稿，核对后发送'; agentOpen.value = true; tab.value = 'chat'; }
function liveCaptureSource(capture) { liveSourceCapture.value = capture; sourceText.value = `模拟抓拍来源：演示摄像头\n抓拍时间：${formatTime(capture.observedAt)}\n此画面为模拟素材，非实景视频。`; }
async function liveCaptureAdd(capture) {
  const stamp = s.stamp(), workspace = gardenId.value, thread = s.threadId;
  tab.value = 'chat';
  if (!assetIds.value.includes(capture.assetId)) assetIds.value.push(capture.assetId);
  await refresh();
  if (!s.current(stamp) || gardenId.value !== workspace || s.threadId !== thread) return;
  uploadedAsset.value = assets.value.find(item => item.id === capture.assetId) || null;
  notice.value = '抓拍已加入本轮，可先分析照片或补充描述';
}
const liveSourceCapture = ref(null);
const error = ref(""), notice = ref(""), busy = ref(false), loading = ref(false), sourceText = ref("");
const readingItem = ref(null), sourceLoading = ref(false), sourceError = ref(''), sourceFragment = ref('');
let sourceRequest = 0;
function closeReader() { stopSpeaking(); reportItem.value = null; ++sourceRequest; readingItem.value = null; sourceText.value = ''; sourceLoading.value = false; sourceError.value = ''; sourceFragment.value = ''; }
function askKnowledge(item, excerpt = '') { if (creatingThread.value) return;
  if (!(overview.value?.knowledge || []).some(row => row.id === item.id)) return;
  closeReader();
  assetIds.value = [];
  knowledgeIds.value = [item.id];
  if (!draft.value.trim()) draft.value = `请帮我理解《${label(item)}》，结合当前园区说明。`;
  if (typeof excerpt === 'string' && excerpt.trim()) draft.value += `\n\n《${label(item)}》引用：\n${excerpt.trim().slice(0, 2000)}`;
  tab.value = 'chat';
}
function openRelated(target) { const item = (overview.value?.knowledge || []).find(x => x.id === target.id); if (item) void viewSource(item, 'knowledge', target.fragment); }
const dialog = ref(""), formName = ref(""), formDetail = ref(""), formDue = ref(""), selectedDevice = ref("");
const thresholdMetric = ref("temperature"), thresholdMin = ref(""), thresholdMax = ref("");
const onboarding = ref(''), onboardingGarden = ref('');
const sourceReport = ref(null);
const reportScopeOpen = ref(false), reportSelection = ref([]);
const completionReceipt = ref(null);
const completionAssetIds = ref([]), selectedTaskId = ref('');
const assetIds = ref([]), knowledgeIds = ref([]), draft = computed({get: () => s.prompt, set: value => s.prompt = value}), messages = computed(() => s.messages), generating = computed(() => Boolean(s.activeTurn || s.submitting)), phase = computed(() => statusNames[s.activeTurn?.status] || ""), taskId = computed(() => s.activeTurn?.id || "");
const agentOpen = ref(false), resourcesOpen = ref(false), resourcesTab = ref('assets'), taskFilter = ref('open'), taskQuery = ref('');
const skills = ref([]), skillsError = ref('');
let skillsRequest = 0
watch(() => `${s.sessionEpoch}:${s.user?.id || ''}`, () => { ++skillsRequest; skills.value = []; skillsError.value = '' }, {flush: 'sync'})
async function loadSkills() {
  const generation = ++skillsRequest, session = s.sessionEpoch, user = s.user?.id
  const current = () => generation === skillsRequest && session === s.sessionEpoch && user === s.user?.id
  try { const data = await request('/skills'); if (current()) { skills.value = data.skills || []; skillsError.value = '' } }
  catch(e) { if (current()) skillsError.value = '技能加载失败，请重试' }
}
const selectedSkill = computed(() => skills.value.find(item => item.id === s.skillId));
const canSend = computed(() => {
  const kind = selectedSkill.value?.kind
  if (!kind || kind === 'chat') return !!draft.value.trim()
  const mediaKind = kind === 'image_analysis' ? 'image' : 'audio'
  return assets.value.filter(asset => assetIds.value.includes(asset.id) && asset.kind === mediaKind).length === 1
});
function suggestSkill() { if (creatingThread.value) return; draft.value = selectedSkill.value?.description || ''; notice.value = '建议已加入草稿，编辑后发送'; }
function showAnswerSources() { closeReader(); sourceText.value = readableSources(s.artifact?.sources); }
const taskStats = computed(() => ({open: tasks.value.filter(x => x.status === 'open').length, completed: tasks.value.filter(x => x.status === 'completed').length, overdue: tasks.value.filter(isOverdue).length}));
function isOverdue(item) { return item.status === 'open' && item.dueAt && item.dueAt * 1000 < Date.now() }
const filteredTasks = computed(() => tasks.value.filter(item => (!taskFilter.value || item.status === taskFilter.value) && `${item.title} ${item.description || ''}`.toLowerCase().includes(taskQuery.value.toLowerCase())));
const uploadedAsset = ref(null), mediaTurnId = ref(''), mediaAssetId = ref('');
const mediaTurn = computed(() => s.turns.find(turn => turn.id === mediaTurnId.value));
function continueWithPhoto() { const asset = assets.value.find(row => row.id === mediaAssetId.value); if (!asset) return; if (!assetIds.value.includes(asset.id)) assetIds.value.push(asset.id); const observation = s.artifact?.turnId === mediaTurnId.value ? s.artifact.body : ''; draft.value = [draft.value.trim(), observation ? `此前照片分析结果（待现场核对）：\n${observation}` : '', '请结合这张照片继续分析，需要补充哪些现场信息？'].filter(Boolean).join('\n\n'); tab.value = 'chat'; notice.value = '照片已加入引用，核对草稿后发送；移除引用不会删除原件'; }
const observations = ref([]), pendingMutation = ref(null), followRuns = ref(1), followInterval = ref(''), followBudget = ref(2), transcribingTurnId = ref('');
const formatTime = value => value ? new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString() : '';

const mainElement = ref(null), messagesElement = ref(null), followLatest = ref(true);
function messageScroll() { const el = messagesElement.value; if (el && Number.isFinite(el.scrollHeight)) followLatest.value = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }
async function scrollToLatest(force = false) { const follow = force || followLatest.value; await nextTick(); if (follow && messagesElement.value) messagesElement.value.scrollTop = messagesElement.value.scrollHeight || 0; }
watch(() => [s.threadId, tab.value === 'chat'], () => { followLatest.value = true; void scrollToLatest(true) });
watch(tab, async () => { if (readingItem.value || reportItem.value) closeReader(); stopSpeaking(); mobileMenuOpen.value = false; await nextTick(); mainElement.value?.scrollTo?.({ top: 0 }); });
watch(agentOpen, opened => { if (opened) void scrollToLatest() });
watch(() => [messages.value.length, messages.value.at(-1)?.content, s.activeTurn?.status], () => { void scrollToLatest() }, {flush:'post'});
const modalElement = ref(null); let previousFocus;
const uploadInput = ref(null), uploadKind = ref("document");
let epoch = 0, scopeEpoch = 0, controller, writeSequence = 0;
const gardenThreads = computed(() => s.threads);
const garden = computed(() => gardens.value.find((x) => x.id === gardenId.value));
const assets = computed(() => overview.value?.assets || []);
const photos = computed(() => assets.value.filter((x) => x.kind === "image"));
const tasks = computed(() => overview.value?.workItems || []);
const readings = computed(() => observations.value);
const metrics = computed(() => [{ label: "\u7A7A\u6C14\u6E29\u5EA6", metric: "temperature", unit: "\xB0C" }, { label: "\u7A7A\u6C14\u6E7F\u5EA6", metric: "humidity", unit: "%" }, { label: "\u571F\u58E4\u542B\u6C34\u7387", metric: "soil_moisture", unit: "%" }].map((item) => ({ ...item, reading: [...readings.value].reverse().find((x) => x.metric === item.metric) })));
const latestAvailableReport = computed(() => overview.value?.reports?.find(item => !item.unavailable))
const activeTasks = computed(() => tasks.value.filter((x) => x.status !== "completed"));
const scoped = (path) => `workspaces/${encodeURIComponent(gardenId.value)}/${path}`;
const label = (x) => x.name || x.title || x.filename || x.id;
function messageLines(content) { return String(content).split('\n').map(line => ({bullet:/^\s*[-*]\s+/.test(line), parts:line.replace(/^\s*[-*]\s+/, '').split(/(\*\*[^*]+\*\*)/g)})) }
function fail(e) {
  error.value = e instanceof Error ? e.message : "\u64CD\u4F5C\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5";
}
async function refresh() {
  if (!gardenId.value) return;
  const token = ++epoch;
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  try {
    const gid = gardenId.value;
    const signal = controller.signal;
    const [result, assetList, knowledgeList] = await Promise.all([readGarden(gid, signal), agricultureRead(scoped("assets"), signal), agricultureRead(scoped("knowledge"), signal)]);
    const deviceReadings = await Promise.all((result.devices || []).map((device) => agricultureRead(`devices/${device.id}/readings`, signal)));
    if (token === epoch) {
      overview.value = { ...result, assets: assetList.assets, knowledge: knowledgeList.knowledge };
      observations.value = deviceReadings.flatMap((x) => x.observations || []).sort((a, b) => a.observedAt - b.observedAt);
    }
  } catch (e) {
    if (token === epoch && !controller.signal.aborted) { s.handleError(e); fail(e) }
  } finally {
    if (token === epoch) loading.value = false;
  }
}
watch(() => `${s.sessionEpoch}:${s.workspaceId}`, () => { stopSpeaking(); mobileMenuOpen.value = false; voiceOpen.value = false; ++epoch; ++scopeEpoch; overview.value = null; uploadedAsset.value = null; mediaTurnId.value = ''; mediaAssetId.value = ''; selectedTaskId.value = ''; completionReceipt.value = null; reportScopeOpen.value = false; reportSelection.value = []; sourceReport.value = null; onboarding.value = ''; onboardingGarden.value = ''; completionAssetIds.value = []; pendingMutation.value = null; closeReader(); liveSourceCapture.value = null; dialog.value = ''; formName.value = ''; formDetail.value = ''; plotId.value = ''; assetIds.value = []; knowledgeIds.value = []; observations.value = []; taskQuery.value = ''; resourcesOpen.value = false; error.value = ''; notice.value = ''; if (s.workspaceId) { void refresh(); void loadSkills() } }, { immediate: true });
// A view change releases its busy state; stale request finalizers remain fenced.
watch(() => s.stamp(), () => { busy.value = false });
watch(dialog, value => { if (!value) sourceReport.value = null; });
watch(() => s.threadId, () => { sourceReport.value = null; mediaTurnId.value = ''; mediaAssetId.value = ''; transcribingTurnId.value = ''; uploadedAsset.value = null; });
watch([() => s.artifact?.id, transcribingTurnId], () => {
  if (transcribingTurnId.value && s.artifact?.turnId === transcribingTurnId.value) {
    draft.value = [draft.value.trim(), s.artifact.body].filter(Boolean).join('\n\n'); notice.value = '转写草稿已就绪，请编辑核对后发送'; transcribingTurnId.value = ''
  }
});
watch([dialog, sourceText, readingItem], async ([kind, text, item]) => { if (kind || text || item) { previousFocus ||= document.activeElement; await nextTick(); (modalElement.value?.querySelector('input,select,textarea') || modalElement.value?.querySelector('button') || modalElement.value)?.focus() } else { previousFocus?.focus?.(); previousFocus = undefined } });
function modalKey(event) {
  if (event.key === 'Escape') { mobileMenuOpen.value = false; toolsOpen.value = false; }
  if (!dialog.value && !sourceText.value && !readingItem.value && !reportItem.value && !voiceOpen.value) return;
  if (event.key === 'Escape') { event.preventDefault(); dialog.value = ''; voiceOpen.value = false; closeReader(); return; }
  if (event.key === 'Tab') { const elements = [...(modalElement.value?.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]') || [])]; if (!elements.length) return; const first = elements[0], last = elements.at(-1); if (event.shiftKey && document.activeElement === first) {event.preventDefault();last.focus()} else if (!event.shiftKey && document.activeElement === last) {event.preventDefault();first.focus()} }
}
document.addEventListener('keydown', modalKey);
onBeforeUnmount(() => { stopSpeaking(); ++epoch; ++scopeEpoch; controller?.abort(); document.removeEventListener('keydown', modalKey) });
watch(() => s.latestTurn?.status, (status, old) => { if (status && status !== old && !['running','queued'].includes(status)) void refresh() });
const creatingThread = ref(false), toolsOpen = ref(false), toolsElement = ref(null)
const newChatBlocked = computed(() => creatingThread.value || loading.value || s.loading || generating.value || !!s.pending || busy.value || !!pendingMutation.value)
function toolAction(action) { toolsOpen.value = false; action() }
function outsideTools(event) { if (toolsOpen.value && !toolsElement.value?.contains(event.target) && !event.target.closest('.mobile-more')) toolsOpen.value = false }
onMounted(() => document.addEventListener('pointerdown', outsideTools))
onBeforeUnmount(() => document.removeEventListener('pointerdown', outsideTools))
watch([tab, gardenId, () => s.threadId], () => { toolsOpen.value = false })
async function startNewChat() {
  toolsOpen.value = false
  if (!gardenId.value) return
  if (newChatBlocked.value) { notice.value = '请等待当前操作完成后新建对话'; return }
  if (!s.pendingThread && s.threadId && !s.messages.length && !s.turns.length) { tab.value = 'chat'; resourcesOpen.value = false; closeDrawer(); return }
  const owner = s.sessionEpoch, workspace = s.workspaceId
  const saved = {prompt:s.prompt, includeHistory:s.includeHistory, skillId:s.skillId, assets:[...assetIds.value], knowledge:[...knowledgeIds.value]}
  creatingThread.value = true
  try {
    if (!await s.createThread('新对话') || owner !== s.sessionEpoch || workspace !== s.workspaceId) return
    s.prompt = saved.prompt; s.includeHistory = saved.includeHistory; s.skillId = saved.skillId
    assetIds.value = saved.assets; knowledgeIds.value = saved.knowledge
    tab.value = 'chat'; resourcesOpen.value = false
    if (!s.error && (saved.prompt || saved.assets.length || saved.knowledge.length)) notice.value = '未发送内容已保留'
  } finally { creatingThread.value = false }
}
function createAnswerTask(message) {
  if (generating.value || message !== messages.value.at(-1) || message.role !== 'assistant' || !message.content?.trim()) return;
  open('task');
  formName.value = '现场检查 · ' + String(message.content).replace(/[*#\n]/g, ' ').trim().slice(0, 48);
  formDetail.value = message.content;
}
function open(kind, device) {
  sourceReport.value = null;
  dialog.value = kind;
  formName.value = "";
  formDetail.value = "";
  formDue.value = "";
  thresholdMin.value = "";
  thresholdMax.value = "";
  selectedDevice.value = device?.id || "";
  error.value = "";
}
async function write(path, data, retry = false) {
  if (pendingMutation.value && !retry) { error.value = '上一项操作结果未确认，请先核对原请求'; return }
  const stamp = s.stamp(), token = scopeEpoch, operation = ++writeSequence;
  const body = retry ? pendingMutation.value.body : data instanceof FormData ? data : {commandId: crypto.randomUUID(), ...data};
  const receipt = {path, body}; busy.value = true; error.value = ''; notice.value = '';
  try { const result = await agricultureWrite(path, body, s.csrf); if (!s.current(stamp) || token !== scopeEpoch) return; pendingMutation.value = null; notice.value = '已保存'; if (result.ingestToken) sourceText.value = `设备接入凭据（只显示一次，请妥善保存）\n${result.ingestToken}\n\n该凭据仅允许此设备上报数据。`; return result }
  catch(e) { if (s.current(stamp) && token === scopeEpoch) { if (!e.status || e.status >= 500) pendingMutation.value = receipt; else pendingMutation.value = null; s.handleError(e, stamp); fail(e) } }
  finally { if (s.current(stamp) && token === scopeEpoch && operation === writeSequence) busy.value = false }
}
async function removeAsset(asset) { const stamp = s.stamp(); try { await request(`/assets/${asset.id}`, {method:'DELETE', csrf:s.csrf}); if (s.current(stamp)) { assetIds.value = assetIds.value.filter(id => id !== asset.id); await refresh(); notice.value = '资料已移除，后续处理不再引用'; } } catch(e) { s.handleError(e, stamp) } }
async function retryMutation() { const command = pendingMutation.value; if (command && await write(command.path, command.body, true)) { dialog.value = ''; await refresh() } }
async function disableFollowup(item) { if (await write(`work-items/${item.id}/follow-up`, {threadId: s.threadId, enabled:false})) await refresh() }
function configureFollowup(item) { open('followup'); selectedDevice.value = item.id; followRuns.value = 1; followInterval.value = ''; followBudget.value = 2; const date = new Date(Date.now()+3600000); formDue.value = new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16) }
async function save() {
  if (dialog.value !== 'followup' && !formName.value.trim()) return;
  const kind = dialog.value;
  if (kind === 'followup') {
    if (!s.threadId && !await s.createThread('园区定期跟进')) return;
    const result = await write(`work-items/${selectedDevice.value}/follow-up`, {threadId: s.threadId, enabled: true, nextDueAt: Math.floor(new Date(formDue.value).getTime() / 1000), maxRuns: Number(followRuns.value), maxModelCalls: Number(followBudget.value), ...(followInterval.value ? {intervalSeconds: Number(followInterval.value)} : {})});
    if (result) { dialog.value = ''; await refresh() } return;
  }

  if (kind === "complete") {
    const result2 = await write(`work-items/${selectedDevice.value}/complete`, { note: formName.value, assetIds: [...completionAssetIds.value] });
    if (result2) {
      completionReceipt.value = { ...(tasks.value.find(item => item.id === selectedDevice.value) || {}), note: formName.value, assetIds: [...completionAssetIds.value] };
      dialog.value = "";
      await refresh();
    }
    return;
  }
  if (kind === "learning") {
    const result2 = await write(`knowledge/${selectedDevice.value}/learning`, { answer: formName.value, feedback: formDetail.value });
    if (result2) dialog.value = "";
    return;
  }
  const data = {};
  if (["garden", "plot", "device"].includes(kind)) data.name = formName.value.trim();
  if (kind === "plot") Object.assign(data, { crop: formDetail.value });
  if (kind === "task") Object.assign(data, { title: formName.value, description: formDetail.value, dueAt: formDue.value ? Math.floor(new Date(formDue.value).getTime() / 1000) : void 0, followUpAt: formDue.value ? Math.floor(new Date(formDue.value).getTime() / 1000) : void 0, plotId: plotId.value || void 0 });
  if (kind === "device") Object.assign(data, { kind: formDetail.value || "sensor", plotId: plotId.value || void 0, thresholds: thresholdMin.value || thresholdMax.value ? { [thresholdMetric.value]: { ...thresholdMin.value ? { min: Number(thresholdMin.value) } : {}, ...thresholdMax.value ? { max: Number(thresholdMax.value) } : {} } } : {} });
  if (kind === "event") Object.assign(data, { sourceEventId: crypto.randomUUID(), observedAt: Math.floor(Date.now() / 1000), readings: [{ metric: formName.value, value: Number(formDetail.value), unit: formName.value === "temperature" ? "celsius" : "percent" }], source: "test" });
  const path = kind === "garden" ? "workspaces" : kind === "event" ? `devices/${selectedDevice.value}/events` : scoped({ plot: "plots", task: "work-items", device: "devices" }[kind] || "");
  let result; if (kind === 'garden') { busy.value = true; try { result = await s.createWorkspace(formName.value.trim()) ? {workspace: s.workspace} : null } finally { busy.value = false } } else result = await write(path, data);
  if (result) {
    dialog.value = "";
    if (kind === "garden") {
      onboarding.value = 'plot';
      await refresh();
    } else { await refresh(); if (kind === 'plot') onboarding.value = 'ready'; }
  }
}
function chooseUpload(kind) { if (creatingThread.value) return;
  uploadKind.value = kind;
  uploadInput.value?.click();
}
async function upload(event) { if (creatingThread.value) return;
  const input = event.target || {value:""};
  const file = event.file || input.files?.[0];
  if (!file) return;
  const stamp = s.stamp();
  const body = new FormData();
  body.set("file", file);
  body.set("kind", uploadKind.value);
  const result = await write(scoped("assets"), body);
  input.value = "";
  if (result) {
    await refresh();
    if (!s.current(stamp)) return;
    if (result.asset?.id) { uploadedAsset.value = result.asset; notice.value = '资料已保存，尚未加入本轮，也未发送给模型服务。'; }
  }
}
async function processAsset(asset, action = 'analyze') {
  if ((action === 'analyze' && asset.kind !== 'image') || (action === 'transcribe' && asset.kind !== 'audio')) return;
  const originalDraft = draft.value, workspace = gardenId.value, session = s.sessionEpoch, priorThread = s.threadId;
  if (!s.threadId && !await s.createThread(action === 'transcribe' ? '语音转写' : '资料分析')) return;
  if (gardenId.value !== workspace || s.sessionEpoch !== session || (priorThread && s.threadId !== priorThread)) return;
  if (originalDraft && !draft.value.trim()) draft.value = originalDraft;
  const targetThread = s.threadId;
  const receipt = await write(`assets/${asset.id}/${action}`, { threadId: targetThread });
  if (!receipt || gardenId.value !== workspace || s.sessionEpoch !== session || s.threadId !== targetThread) return;
  mediaTurnId.value = receipt.turn?.id || ''; mediaAssetId.value = asset.id; tab.value = 'chat';
  if (action === 'transcribe') transcribingTurnId.value = receipt.draft === undefined ? receipt.turn?.id || '' : '';
  if (receipt.turn && !s.turns.some(turn => turn.id === receipt.turn.id)) s.turns.push(receipt.turn);
  if (receipt.draft !== undefined) { draft.value = [draft.value.trim(), receipt.draft].filter(Boolean).join('\n\n'); notice.value = '转写完成，请核对并编辑草稿后发送'; }
  else notice.value = receipt.turn ? '处理已提交，可在对话查看真实任务进展' : '资料状态已更新';
  await refresh();
}
function complete(item) {
  completionAssetIds.value = [];
  open("complete");
  selectedDevice.value = item.id;
}
const reportCandidates = computed(() => tasks.value.filter(item => !plotId.value || item.plotId === plotId.value));
watch(plotId, () => { reportSelection.value = reportSelection.value.filter(id => reportCandidates.value.some(item => item.id === id)); });
async function report() { reportSelection.value = reportCandidates.value.map(item => item.id); reportScopeOpen.value = true; }
async function generateReport() {
  const stamp = s.stamp(), workspace = gardenId.value;
  const ids = reportSelection.value.filter(id => reportCandidates.value.some(item => item.id === id));
  if (!ids.length || busy.value) return;
  const result = await write(scoped('reports'), {title: '园区工作简报', plotId: plotId.value || undefined, workItemIds: ids});
  if (result) { reportScopeOpen.value = false; await refresh(); if (!s.current(stamp) || gardenId.value !== workspace) return; const item = result.report; if (item) await viewSource(item, 'reports'); }
}
function reportNextStep(item) { const report = reportItem.value; reportItem.value = null; open('task'); sourceReport.value = {title: report?.title || '园区报告', task: {title:item.title || '', description:item.description || ''}}; formName.value = item.title || ''; formDetail.value = item.description || '';  }

async function viewSource(item, type, fragment = '', listen = false) {
  if (type === 'reports' && item.unavailable) { notice.value = item.reason || '报告来源不可用'; return }
  closeReader();
  const requestNumber = sourceRequest;
  if (type === 'knowledge') { readingItem.value = item; sourceLoading.value = true; sourceFragment.value = fragment; }
  error.value = "";
  const owner = auth.userId, gid = gardenId.value;
  const current = () => requestNumber === sourceRequest && agricultureScopeMatches({ owner, gardenId: gid }, { owner: auth.userId, gardenId: gardenId.value });
  try {
    if (type === "assets") {
      const response = await fetchAssetContent(agricultureAssetContentUrl(gardenId.value, item.id));
      if (!response.ok) throw new Error("\u65E0\u6CD5\u8BFB\u53D6\u539F\u4EF6");
      if (!current()) return;
      if (item.kind === "document" && ["text/plain", "text/markdown", "text/csv"].includes(item.mediaType)) {
        const text = await response.text();
        if (current()) sourceText.value = text;
      } else {
        const blob = await response.blob();
        if (!current()) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = label(item);
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1e3);
        notice.value = "\u539F\u4EF6\u5DF2\u4E0B\u8F7D";
      }
      return;
    }
    const data = await agricultureRead(`${type}/${item.id}${type === "devices" ? "/readings" : ""}`);
    if (!current()) return;
    if (type === "knowledge") {
      const original = assets.value.find(asset => asset.id === item.assetId);
      if (item.assetId && (item.library || ["text/plain", "text/markdown", "text/csv"].includes(original?.mediaType))) {
        const response = await fetchAssetContent(agricultureAssetContentUrl(gid, item.assetId));
        if (!response.ok) throw new Error("无法读取知识原件");
        const text = await response.text();
        if (current()) { readingItem.value = {...item, ...data.knowledge}; sourceText.value = text; if (listen) speak(text); }
        return;
      }
    }
    if (type === "reports" && data.report) { reportItem.value = data.report; return }
    if (type === "knowledge") readingItem.value = {...item, ...data.knowledge};
    sourceText.value = data.content || data.knowledge?.excerpts?.map((x) => `${x.locator}
${x.text}`).join("\n\n") || (data.report?.body ? `${data.report.body}

\u6765\u6E90\uFF1A
${readableSources(data.report.sources)}` : "") || data.asset?.text || JSON.stringify(data, null, 2);
    if (listen && type === 'knowledge' && current()) speak(sourceText.value);
  } catch (e) {
    if (current()) { if (type === 'knowledge') sourceError.value = e instanceof Error ? e.message : '无法读取原文'; else fail(e); }
  } finally { if (current()) sourceLoading.value = false; }
}
async function exportReport(item, format) {
  error.value = ''; notice.value = '';
  if (item.unavailable) { notice.value = item.reason || '报告来源不可用'; return }
  const stamp = s.stamp(), workspace = gardenId.value;
  const result = await write(scoped("exports"), { reportId: item.id, format });
  if (result?.asset) {
    notice.value = '';
    try {
      const response = await fetch(agricultureAssetContentUrl(workspace, result.asset.id), {credentials:'same-origin'});
      if (!response.ok) throw new Error('报告下载失败，请重试');
      const blob = await response.blob();
      if (!s.current(stamp) || gardenId.value !== workspace) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = `${item.title || '园区报告'}.md`; link.click();
      notice.value = 'Markdown 文件已开始下载';
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { if (s.current(stamp) && gardenId.value === workspace) error.value = e.message; }
  }
}
function continueLearningDraft() {
 const item = overview.value?.knowledge?.find(row => row.id === selectedDevice.value);
 if (!item) return;
 const notes = [formName.value.trim(), formDetail.value.trim()].filter(Boolean).join('\n');
 if (notes) draft.value = [draft.value.trim(), `我的学习笔记：\n${notes.slice(0,4000)}`].filter(Boolean).join('\n\n');
 dialog.value = ''; askKnowledge(item);
}
async function learn(item) {
  closeReader();
  knowledgeIds.value = [item.id];
  open("learning");
  selectedDevice.value = item.id;
}
function toggle(list, id) { if (creatingThread.value) return;
  const index = list.indexOf(id);
  if (index < 0) list.push(id);
  else list.splice(index, 1);
}
async function reopenThread(id) { await s.selectThread(id) }
async function send(retry = false) { if (creatingThread.value) return;
  if (retry !== true && selectedSkill.value?.kind && selectedSkill.value.kind !== 'chat') {
    const kind = selectedSkill.value.kind === 'image_analysis' ? 'image' : 'audio';
    const chosen = assets.value.filter(asset => assetIds.value.includes(asset.id) && asset.kind === kind);
    if (chosen.length !== 1) { error.value = `请在资料侧栏明确选择一份${kind === 'image' ? '照片' : '录音'}，再执行此技能`; return }
    await processAsset(chosen[0], kind === 'image' ? 'analyze' : 'transcribe'); return;
  }
  // Vue passes the DOM event to a method listener; only an explicit true is a retry.
  retry = retry === true;
  const prompt = draft.value, includeHistory = s.includeHistory, skillId = s.skillId; if (!s.threadId) { if (!await s.createThread(prompt.trim().slice(0, 40) || '现场问题')) return; s.prompt = prompt; s.includeHistory = includeHistory; s.skillId = skillId; }
  s.agricultureContext = { ...(plotId.value ? {plotId: plotId.value} : {}), assetIds: [...assetIds.value], knowledgeIds: [...knowledgeIds.value] };
  await s.submit(retry);
}
async function cancel() { if (s.activeTurn) await s.cancel(s.activeTurn) }
</script>
<template>
  <div :style="mobileViewportHeight ? {height: mobileViewportHeight} : undefined" class="agri-workbench" :class="{ 'phone-overview': tab === 'overview', 'phone-knowledge': tab === 'knowledge', 'phone-tasks': tab === 'tasks', 'phone-task-detail': tab === 'tasks' && !!selectedTaskId, 'phone-task-form': dialog === 'complete' || dialog === 'task', 'phone-monitor': tab === 'monitor', 'phone-devices': tab === 'devices', 'chat-workspace': tab === 'chat', 'agent-collapsed': !agentOpen && tab !== 'chat', 'resources-open': resourcesOpen }">
    <header class="mobile-workspace-header"><button v-if="tab !== 'knowledge'" :class="{'mobile-garden-selector': tab !== 'chat'}" aria-label="打开园区与历史菜单" @click="mobileMenuOpen = !mobileMenuOpen" :aria-expanded="mobileMenuOpen" aria-controls="garden-menu"><BrandMark v-if="tab !== 'chat'"/>{{ tab === 'chat' ? '☰' : `${garden?.name || '我的园区'} ⌄` }}</button><div><BrandMark v-if="tab === 'chat'"/><strong>{{ tab === 'knowledge' ? '学习知识库' : tab === 'chat' ? '澍雨' : '' }}</strong></div><button v-if="tab === 'chat'" aria-label="新对话" :disabled="newChatBlocked" @click="startNewChat()"><svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M13 5H5v14h14v-8M10 14l1-4L19 2l3 3-8 8z"/></svg></button><button v-else aria-label="打开对话" @click="tab = 'chat'"><BrandMark/></button></header>
    <aside class="agri-sidebar desktop-sidebar">
      <div class="agri-brand"><BrandMark class="agri-drop" /><div><strong>澍雨</strong><small>农业助手</small></div></div>
      <select v-model="gardenId" aria-label="当前园区"><option value="" disabled>选择我的园区</option><option v-for="item in gardens" :key="item.id" :value="item.id">{{ label(item) }}</option></select>
      <button class="agri-new" @click="onboarding = 'choose'; onboardingGarden = gardenId; mobileMenuOpen = false">选择园区</button><button class="agri-new" @click="open('garden')">＋ 新建园区</button>
      <nav aria-label="农业工作台"><button v-for="item in tabs" :key="item.id" :class="{ active: tab === item.id, 'agri-device-nav': item.id === 'devices' }" @click="tab = item.id; mobileMenuOpen = false"><i :class="`bi bi-${item.icon}`"></i>{{ item.label }}</button></nav>

      <button class="agri-return" @click="s.logout()">退出登录</button>
    </aside>
    <aside v-if="mobileMenuOpen" id="garden-menu" ref="drawerElement" class="conversation-drawer" role="dialog" aria-modal="true" aria-label="对话历史">
      <header><div class="drawer-brand"><BrandMark/><strong>澍雨</strong></div><button aria-label="关闭历史侧栏" @click="closeDrawer()">✕</button></header>
      <button class="drawer-new" :disabled="newChatBlocked" @click="drawerAction(() => startNewChat())">＋ 新对话</button>
      <input v-model="historyQuery" type="search" aria-label="搜索历史对话" placeholder="搜索历史对话" />
      <section class="drawer-history"><h2>最近对话</h2><p v-if="drawerError" role="alert">{{ drawerError }}</p><button v-for="thread in filteredHistory" :key="thread.id" :class="{active: s.threadId === thread.id}" @click="chooseHistory(thread)"><i class="bi bi-chat" aria-hidden="true"></i><span>{{ thread.title || thread.name || '现场对话' }}</span></button><p v-if="!filteredHistory.length">{{ historyQuery.trim() ? '没有找到相关对话' : '还没有对话，开始聊聊吧' }}</p></section>
      <footer><label>当前园区<select v-model="gardenId" aria-label="侧栏当前园区"><option value="" disabled>选择园区</option><option v-for="item in gardens" :key="item.id" :value="item.id">{{ label(item) }}</option></select></label><div><button @click="drawerAction(() => open('garden'))">新建园区</button></div><button @click="drawerAction(() => s.logout())">退出登录</button></footer>
    </aside>
    <button v-if="mobileMenuOpen" class="mobile-menu-shade" aria-label="关闭菜单" @click="mobileMenuOpen = false"></button>
    <main ref="mainElement" class="agri-main" :class="{ 'chat-resources': tab === 'chat' }">
      <header v-if="!selectedTaskId || tab !== 'tasks'"><button v-if="tab !== 'chat'" class="agri-agent-toggle" @click="agentOpen = !agentOpen" :aria-expanded="agentOpen"><BrandMark/>{{ agentOpen ? '收起助手' : '问澍雨' }}</button><h1>{{ tab === 'overview' ? '今天园里怎么样？' : tab === 'knowledge' ? '学习知识库' : tabs.find(x => x.id === tab)?.label }}</h1><p>{{ tab === 'overview' ? '现场变化、待办和下一步，都在这里。' : `${garden?.name || '我的园区'} · 把现场情况记录清楚` }}</p></header>
      <div v-if="tab === 'overview' && gardenId" class="friendly-welcome"><section class="friendly-calendar"><div class="friendly-calendar-icon" aria-hidden="true"><span>{{ displayMonth(overview?.presentation?.calendar?.date) }}</span><strong>{{ displayDay(overview?.presentation?.calendar?.date) }}</strong></div><div><small>今日黄历</small><h2>{{ displayDate(overview?.presentation?.calendar?.date) }}</h2><p>{{ displayLunar(overview?.presentation?.calendar?.lunarDate) }}</p><span v-if="overview?.presentation?.calendar?.jieQi || overview?.presentation?.calendar?.season" class="friendly-season">{{ overview.presentation.calendar.jieQi || `${overview.presentation.calendar.season}时节` }}</span><button @click="calendarOpen = !calendarOpen">看黄历 {{ calendarOpen ? '⌃' : '›' }}</button></div><div v-if="calendarOpen" class="calendar-detail"><p>传统黄历 · Asia/Shanghai</p><p>宜：{{ overview?.presentation?.calendar?.yi?.slice(0,2).join('、') || '暂无' }}　忌：{{ overview?.presentation?.calendar?.ji?.slice(0,2).join('、') || '暂无' }}</p><small>传统文化信息，不作为农事作业判断。</small></div></section><section class="friendly-weather"><FriendlyIcon name="weather"/><div><small>园区天气 <span class="friendly-demo">天气样例</span></small><h2>{{ overview?.presentation?.weather?.temperature ?? overview?.presentation?.weather?.high ?? '—' }}<small>℃</small> {{ overview?.presentation?.weather?.condition || '多云' }}</h2><p>{{ overview?.presentation?.weather?.low ?? '—' }}—{{ overview?.presentation?.weather?.high ?? '—' }}℃</p><small>演示天气，非实时观测</small><small v-if="overview?.presentation?.weather?.precipitationProbability != null">样例降雨概率 {{ overview.presentation.weather.precipitationProbability }}%</small></div><div v-if="overview?.presentation?.weather?.forecast?.length" class="friendly-forecast"><div v-for="day in overview.presentation.weather.forecast.slice(0,3)" :key="day.label"><FriendlyIcon :name="day.icon === 'rain' ? 'rain' : 'weather'"/><span>{{ day.label }}<small>{{ day.condition }}</small></span></div></div></section><section class="friendly-ask"><BrandMark/><div><h2>问澍雨</h2><p>点一下，直接说</p><div><button class="agri-primary" @click="voiceOpen = true">🎙 说话</button><button @click="chooseUpload('image')">📷 拍照</button></div><button @click="agentOpen = true; tab = 'chat'">打开对话 ›</button><button @click="speaking ? stopSpeaking() : speak(`当前园区有${activeTasks.length}项待处理任务。${activeTasks.slice(0,4).map(x=>x.title).join('。')}`)">{{ speaking ? '停止朗读' : '🔊 听今日提醒' }}</button></div></section></div><p v-if="speechMessage" role="status">{{ speechMessage }}</p>
      <div v-if="liveDemo?.enabled && !['overview','monitor','devices'].includes(tab)" class="live-banner"><span><i></i>演示模式 · 设备与画面为模拟</span></div>
      <div class="agri-context" v-if="gardenId && tab !== 'knowledge' && !(tab === 'tasks' && selectedTaskId)"><select v-model="plotId" aria-label="选择地块"><option value="">全部地块</option><option v-for="plot in overview?.plots || []" :key="plot.id" :value="plot.id">{{ label(plot) }}</option></select><details class="context-more"><summary>更多</summary><button @click="open('plot')">＋ 添加地块</button><button :disabled="loading" @click="refresh">{{ loading ? '读取中…' : '刷新' }}</button></details></div>
      <p v-if="error || s.error" class="agri-error" role="alert">{{ error || s.error }}</p><p v-if="pendingMutation" class="agri-error">操作结果尚未确认。<button :disabled="busy" @click="retryMutation">用相同编号核对原请求</button></p><p v-if="notice" class="agri-notice" role="status">{{ notice }}</p><div v-if="uploadedAsset" class="agri-upload-receipt"><span>{{ label(uploadedAsset) }} · {{ mediaAssetId === uploadedAsset.id && mediaTurn ? '处理状态见下方' : uploadedAsset.kind === 'image' ? '照片已保存，尚未分析' : '已保存，尚未转写' }}</span><button v-if="uploadedAsset.kind === 'image'" class="agri-primary" :disabled="busy || generating" @click="processAsset(uploadedAsset)">✧ 分析照片</button><button v-if="uploadedAsset.kind === 'audio'" :disabled="busy || generating" @click="processAsset(uploadedAsset, 'transcribe')">转成文字</button><button @click="toggle(assetIds, uploadedAsset.id)">{{ assetIds.includes(uploadedAsset.id) ? '取消本轮引用' : '加入本轮' }}</button><button @click="tab = 'chat'">查看资料</button></div>
      <section v-if="!gardenId" class="agri-card agri-empty"><i class="bi bi-flower1"></i><h2>从自己的园区开始</h2><p>创建园区，添加地块和现场资料。这里会呈现你的真实记录。</p><button class="agri-primary" @click="open('garden')">创建我的园区</button></section>
      <template v-else>
        <MobileGarden class="phone-overview-content" v-if="tab === 'overview'" :garden="garden" :overview="overview" :live="liveDemo" :error="liveError" :uncertain="liveUncertain" :pending="livePending" @explain="liveExplain" @reconcile="liveReconcile" @retry="liveRetry" :metrics="metrics" :observations="observations" :tasks="activeTasks" :workspace-id="gardenId" @task="id => { selectedTaskId = id; tab = 'tasks' }" @navigate="selectedTaskId = ''; tab = $event" @report="report" />
        <button v-if="['monitor','tasks','devices'].includes(tab) && !selectedTaskId" class="mobile-back" @click="tab = 'overview'">‹ 返回园区</button>
        <LiveFieldPanel v-if="liveDemo?.enabled && ['overview','monitor','devices'].includes(tab)" :live="liveDemo" :view="tab" :workspace-id="gardenId" :pending="livePending" :error="liveError" :uncertain="liveUncertain" @action="liveAction" @explain="liveExplain" @capture-source="liveCaptureSource" @capture-add="liveCaptureAdd" @create-task="item => { open('task'); formName = item.title || ''; formDetail = item.description || '' }" @register-device="open('device')" @reconcile="liveReconcile" @retry="liveRetry" />
        <div v-if="liveDemo?.enabled && tab === 'overview'" class="friendly-next-grid"><section class="agri-card"><h2>接下来做什么</h2><p v-if="!activeTasks.length" class="agri-muted">暂无待处理任务</p><div v-for="item in activeTasks.slice(0,3)" :key="item.id" class="agri-row"><span>🍃 {{ label(item) }}<small>{{ item.description || '请核对现场记录' }}</small></span><button @click="tab = 'tasks'">去看看 ›</button></div></section><section class="agri-card"><div class="agri-section-title"><h2>园区简报</h2><button :disabled="busy" @click="report">生成简报</button></div><div v-if="latestAvailableReport" class="agri-row"><span>📄 {{ label(latestAvailableReport) }}<small>{{ reportKindLabel(latestAvailableReport) }}</small></span><button @click="viewSource(latestAvailableReport, 'reports')">看报告 ›</button></div><p v-else class="agri-muted">{{ overview?.reports?.length ? '暂无可读取的报告' : '还没有报告，记录现场情况后可生成。' }}</p><p v-for="item in (overview?.reports || []).filter(report => report.unavailable)" :key="item.id" class="agri-muted">来源不可用的报告 · {{ item.reason || '报告来源不可用' }}</p></section></div>
        <template v-if="!liveDemo?.enabled && (tab === 'overview' || tab === 'monitor')">
          <div class="agri-metrics"><section v-for="metric in metrics" :key="metric.metric" class="agri-card"><div><i class="bi bi-droplet"></i> {{ metric.label }}</div><strong>{{ metric.reading ? `${metric.reading.value}${metric.unit}` : '—' }}</strong><small>{{ metric.reading ? `${observationSourceLabel(metric.reading.source)} · ${formatTime(metric.reading.observedAt)}` : '等待监测数据' }}</small></section></div>
          <section class="agri-card agri-scene"><div class="agri-section-title"><h2>现场动态</h2><button @click="chooseUpload('image')">＋ 补充照片</button></div><div v-if="photos.length" class="agri-photos"><figure v-for="photo in photos.slice(0, 2)" :key="photo.id"><img :src="agricultureAssetContentUrl(gardenId, photo.id)" :alt="label(photo)"><figcaption>人工上传 · {{ label(photo) }}</figcaption></figure></div><div v-else class="agri-field-empty"><i class="bi bi-camera"></i><strong>还没有现场照片</strong><span>上传园区、植株或叶片照片，保留第一手观察。</span><button @click="chooseUpload('image')">上传现场照片</button></div><footer>现场记录 → 异常筛查 → 人工核实 <span>设备采集：{{ overview?.devices?.length ? '查看设备状态' : '待接入' }}</span></footer></section>
          <section class="agri-card"><div class="agri-section-title"><h2>现在需要关注 <small>{{ activeTasks.length + (overview?.alerts?.filter((x) => x.status === 'open').length || 0) }} 项</small></h2></div><div v-for="alert in overview?.alerts?.filter((x) => x.status === 'open') || []" :key="alert.id" class="agri-row"><span>监测异常 · {{ metricLabel(alert.metric) }}<strong class="agri-observation-source">{{ observationSourceLabel(alert.reading?.source) }}</strong><small>{{ alert.message || `${alert.reading?.value ?? alert.value ?? ''} 超出已配置阈值，请现场核实` }}</small></span><button @click="tab = 'monitor'">查看读数</button></div><div v-if="!activeTasks.length && !overview?.alerts?.some((x) => x.status === 'open')" class="agri-muted">暂无待处理事项。新增现场记录后，在这里跟进。</div><div v-for="item in activeTasks.slice(0, 4)" :key="item.id" class="agri-row"><span><i class="bi bi-leaf"></i> {{ label(item) }}</span><small>{{ item.dueAt ? formatTime(item.dueAt) : '未设截止时间' }}</small><button @click="tab = 'tasks'">查看任务 ›</button></div></section>
          <section class="agri-card"><div class="agri-section-title"><h2>正在跟进</h2><button @click="report" :disabled="busy">生成今日简报</button></div><div class="agri-muted">{{ tasks.filter(x => x.status === 'completed').length }} 项已完成 · 所有处理记录都可以追溯</div><div v-for="follow in overview?.followUps || []" :key="follow.id" class="agri-row"><span>到期跟进 · {{ (follow.nextDueAt || follow.dueAt) ? formatTime(follow.nextDueAt || follow.dueAt) : '' }}<small>{{ statusLabel(follow.status) }} · 剩余 {{ follow.remainingRuns || 0 }} 次 · {{ follow.reason }}</small></span><button @click="draft = '请结合最新园区记录跟进待办的现场变化'; tab = 'chat'">主动跟进</button></div><div v-for="item in overview?.reports || []" :key="item.id" class="agri-row"><span>{{ item.unavailable ? '来源不可用的报告' : label(item) }}<template v-if="!item.unavailable"> · {{ reportKindLabel(item) }}</template><small v-if="item.unavailable">{{ item.reason || '报告来源不可用' }}</small></span><button :disabled="item.unavailable" @click="viewSource(item, 'reports')">查看报告</button></div></section>
          <section v-if="tab === 'monitor'" class="agri-card"><h2>监测记录</h2><p class="agri-muted">手工录入会明确标识来源，不代表设备实时上报。</p><div v-if="readings.length" class="agri-reading-table"><div v-for="(reading, index) in [...readings].reverse()" :key="index" class="agri-row"><span>{{ reading.metric === 'temperature' ? '空气温度' : '空气湿度' }} <strong>{{ reading.value }}{{ reading.unit === 'celsius' ? '°C' : '%' }}</strong><small>{{ formatTime(reading.observedAt) }} · {{ observationSourceLabel(reading.source) }}</small></span></div></div><p v-else>暂无读数。请到农业设备登记设备并录入测试事件。</p><button @click="tab = 'devices'">管理设备</button></section>
        </template>
        <section v-if="tab === 'chat'" class="agri-card"><button class="resource-close" @click="resourcesOpen = false">关闭资料 ✕</button><div class="agri-section-title"><h2>会话与资料</h2><button :disabled="newChatBlocked" @click="startNewChat()">＋ 新对话</button></div><div class="resource-tabs"><button :class="{active:resourcesTab === 'assets'}" @click="resourcesTab = 'assets'">本轮资料</button><button :class="{active:resourcesTab === 'threads'}" @click="resourcesTab = 'threads'">会话记录</button></div><div v-if="resourcesTab === 'threads'" class="agri-thread-list"><button v-for="thread in gardenThreads" :key="thread.id" :title="thread.title" :class="{selected:s.threadId === thread.id}" @click="reopenThread(thread.id)">{{ thread.title }}</button><p v-if="!gardenThreads.length" class="agri-muted">还没有会话，开始一次现场对话。</p></div><template v-else><div class="resource-upload-actions"><button @click="chooseUpload('document')">上传资料</button><button @click="chooseUpload('image')">上传照片</button></div><p v-if="!assets.length" class="agri-muted">上传资料后，可明确选择加入本轮。</p><div v-for="asset in assets" :key="asset.id" class="agri-row resource-asset"><label class="resource-asset-label"><input type="checkbox" :disabled="creatingThread" :checked="assetIds.includes(asset.id)" @change="toggle(assetIds, asset.id)"><span :title="label(asset)">{{ label(asset) }}</span></label><small class="resource-asset-status">{{ assetStatusLabel(asset) }} {{ asset.error || '' }}</small><div class="resource-asset-actions"><button @click="viewSource(asset, 'assets')">原文</button><button v-if="asset.kind === 'image'" :disabled="busy" @click="processAsset(asset)">分析照片</button><button :disabled="busy" @click="removeAsset(asset)">移除资料</button><button v-if="asset.kind === 'audio'" @click="processAsset(asset, 'transcribe')">转写</button></div><small v-if="asset.kind === 'image' || asset.kind === 'audio'" class="agri-media-disclosure">{{ asset.kind === 'audio' ? '转写会将整段原录音及文件内容发送给配置的模型服务，可能含背景声音；结果为可编辑草稿。' : '分析会将此照片发送给配置的模型服务。' }} 本地服务器保留任务记录。</small></div></template></section>
        <MobileTaskFlow v-if="tab === 'tasks'" :tasks="tasks" :records="overview?.records || []" :plots="overview?.plots || []" :selected-id="selectedTaskId" :receipt="completionReceipt" :workspace-id="gardenId" :busy="busy" @select="id => selectedTaskId = id" @create="open('task')" @complete="complete" @followup="configureFollowup" @recheck="item => { completionReceipt = null; open('task'); formName = `复查：${label(item)}`; formDetail = item.description || '' }" @dismiss="completionReceipt = null; selectedTaskId = ''" />
        <section v-if="tab === 'tasks'" class="agri-card desktop-task-flow" :class="{'task-detail-shell':selectedTaskId}"><div v-if="!selectedTaskId" class="task-stats"><div><strong>{{ taskStats.open }}</strong><small>待处理</small></div><div><strong>{{ taskStats.completed }}</strong><small>已完成</small></div><div><strong>{{ taskStats.overdue }}</strong><small>已逾期</small></div></div><div v-if="!selectedTaskId" class="workspace-filters"><button :class="{selected:taskFilter === 'open'}" @click="taskFilter = 'open'">待处理</button><button :class="{selected:taskFilter === 'completed'}" @click="taskFilter = 'completed'">已完成</button><button :class="{selected:!taskFilter}" @click="taskFilter = ''">全部</button><input v-model="taskQuery" aria-label="搜索任务" placeholder="搜索任务与现场说明"></div><p v-if="!selectedTaskId && tasks.length && !filteredTasks.length" class="agri-muted">没有匹配的任务，试试调整筛选。</p><div class="agri-section-title"><h2 v-if="!selectedTaskId">现场待办</h2><button v-if="selectedTaskId" @click="selectedTaskId = ''">‹ 返回待办</button><button v-if="!selectedTaskId" @click="open('task')">＋ 新建任务</button></div><p v-if="!tasks.length" class="agri-muted">还没有待办。把要核查的事情、截止时间记下来。</p><div class="task-card-grid"><article v-for="item in (selectedTaskId ? tasks.filter(task => task.id === selectedTaskId) : filteredTasks)" :key="item.id" class="agri-task task-card" :class="{'task-detail':selectedTaskId}"><header><span :class="['task-status',item.status]">{{ statusLabel(item.status) }}</span></header><h3>{{ label(item) }} <span v-if="isOverdue(item)" class="task-overdue">逾期</span></h3><h4 v-if="selectedTaskId">任务说明与检查步骤</h4><p v-for="(line, index) in messageLines(item.description || '暂无现场说明').filter(line => line.parts.join('').trim())" :key="index"><span v-if="line.bullet">• </span><template v-for="(part, p) in line.parts" :key="p"><strong v-if="part.startsWith('**') && part.endsWith('**')">{{ part.slice(2,-2) }}</strong><span v-else>{{ part }}</span></template></p><div class="task-meta"><span>⌖ {{ overview?.plots?.find(plot => plot.id === item.plotId)?.name || '全部园区' }}</span><span>◷ {{ item.dueAt ? formatTime(item.dueAt) : '未设截止时间' }}</span></div><div v-for="record in overview?.records?.filter(record => record.workItemId === item.id) || []" :key="record.id" class="agri-record-note">完成记录：{{ record.note }}<img v-for="id in record.assetIds || []" :key="id" :src="agricultureAssetContentUrl(gardenId,id)" alt="完成记录关联照片" class="task-record-photo"><small>{{ formatTime(record.completedAt) }}</small></div><div class="task-card-actions"><button v-if="item.status !== 'completed'" class="agri-primary" :disabled="busy" @click="complete(item)">{{ selectedTaskId ? '我已检查，写记录' : '标记完成并记录' }}</button><details class="task-follow-settings"><summary>跟进设置</summary><p>仅在明确授权后按次数和预算执行。</p><button @click="configureFollowup(item)">授权自动跟进</button><button @click="disableFollowup(item)">停止自动跟进</button></details></div></article></div><section v-if="!selectedTaskId" class="task-reports"><div class="agri-section-title"><h2>园区报告</h2><button @click="report">生成园区报告</button></div><p v-if="!overview?.reports?.length" class="agri-muted">完成现场记录后，可生成可追溯的园区报告。</p><div v-for="item in overview?.reports || []" :key="item.id" class="agri-row"><span>{{ item.unavailable ? '来源不可用的报告' : label(item) }}<template v-if="!item.unavailable"> · {{ reportKindLabel(item) }}</template><small v-if="item.unavailable">{{ item.reason || '报告来源不可用' }}</small></span><button :disabled="item.unavailable" @click="viewSource(item, 'reports')">查看</button><button :disabled="item.unavailable" @click="exportReport(item, 'md')">导出 Markdown</button></div></section></section>
        <section v-if="tab === 'knowledge' && uploadedAsset?.kind === 'document'" class="knowledge-upload-receipt" role="status"><h2>资料已保存</h2><p>{{ label(uploadedAsset) }}</p><p>{{ assetStatusLabel(uploadedAsset) }}</p><p>原件已保留。正文是否可阅读，以实际提取状态为准。</p><button @click="viewSource(uploadedAsset, 'assets')">查看提取内容与状态</button><button @click="uploadedAsset = null">完成</button></section><KnowledgeLibrary @ask="askKnowledge" @voice="voiceOpen = true" @listen="item => viewSource(item, 'knowledge', '', true)" v-if="tab === 'knowledge'" :key="`${s.sessionEpoch}:${gardenId}`" :items="overview?.knowledge || []" :selected="knowledgeIds" @read="item => viewSource(item, 'knowledge')" @learn="learn" @toggle="id => toggle(knowledgeIds, id)" @upload="chooseUpload('document')"><details class="knowledge-originals"><summary>原件与媒体（{{ assets.length }}）</summary><div v-for="asset in assets" :key="asset.id" class="agri-row"><span>{{ label(asset) }} · {{ assetStatusLabel(asset) }} {{ asset.error || '' }}</span><button @click="viewSource(asset, 'assets')">阅读原文</button><button @click="toggle(assetIds, asset.id)">{{ assetIds.includes(asset.id) ? '取消引用' : '加入对话引用' }}</button><button v-if="asset.kind === 'image'" :disabled="busy" @click="processAsset(asset)">分析照片</button><button v-if="asset.kind === 'audio'" :disabled="busy" @click="processAsset(asset, 'transcribe')">转写音频</button><small v-if="asset.kind === 'image' || asset.kind === 'audio'" class="agri-media-disclosure">{{ asset.kind === 'audio' ? '转写会发送整段原录音及文件内容，可能含背景声音；结果为可编辑草稿。' : '分析会发送此照片。' }} 接收方为配置的模型服务，本地服务器保留任务记录。</small></div></details></KnowledgeLibrary>
        <section v-if="tab === 'devices' && !liveDemo?.enabled" class="agri-card"><div class="agri-section-title"><h2>农业设备</h2><button @click="open('device')">＋ 登记设备</button></div><p class="agri-muted">设备登记后默认为待接入。手工测试事件会保留来源标识。</p><p v-if="!overview?.devices?.length">尚未登记设备</p><article v-for="item in overview?.devices || []" :key="item.id" class="agri-task"><h3>{{ label(item) }} <small>{{ statusLabel(item.connectionStatus, '等待设备状态') }}</small></h3><p>{{ deviceKindLabel(item.kind) }} · {{ item.lastSeenAt ? formatTime(item.lastSeenAt) : '暂无上报' }}</p><button @click="open('event', item)">录入手工测试事件</button><button @click="viewSource(item, 'devices')">查看设备记录</button></article></section>
      </template>
    </main>
    <aside class="agri-agent" :class="{ 'agent-hidden': !agentOpen && tab !== 'chat' }"><header><BrandMark class="agri-drop" /><div><h2>澍雨 Agent</h2><button type="button" class="mobile-context-pill" aria-label="查看当前园区与对话资料" :disabled="creatingThread" @click="resourcesOpen = true">{{ plotId ? `${garden?.name || '我的园区'} · ${overview?.plots.find(x => x.id === plotId)?.name || '所选地块'}` : `${garden?.name || '我的园区'} · 全部地块` }}</button></div><button v-if="tab === 'chat'" class="resource-toggle" @click="resourcesOpen = !resourcesOpen" :aria-expanded="resourcesOpen">资料</button><button class="agent-settings" @click="dialog = 'settings'" aria-label="对话设置">⚙</button><button v-if="tab !== 'chat'" @click="agentOpen = false" aria-label="收起助手">×</button></header><div ref="messagesElement" class="agri-messages" aria-live="polite" @scroll="messageScroll"><div v-if="!messages.length" class="phone-chat-welcome"><img src="/brand/shuyu-raindrop-v1.png" alt="澍雨"><p>今天园里有什么新情况？</p><div class="mobile-suggestions"><button v-for="text in ['叶片发黄，先检查什么？','帮我梳理今天的田间观察']" :key="text" :disabled="creatingThread" @click="draft = text">{{ text }}</button></div></div><div v-if="!messages.length" class="agri-welcome"><BrandMark class="agri-drop" /><h2>先从现场开始</h2><p>拍一张照片，描述你的观察。我们结合园区记录，核对资料，再决定下一步。</p><div class="agri-quick"><button @click="chooseUpload('image')" :disabled="!gardenId"><i class="bi bi-image"></i> 照片观察</button><button @click="tab = 'monitor'"><i class="bi bi-bar-chart"></i> 监测记录</button><button @click="tab = 'knowledge'"><i class="bi bi-book"></i> 知识库</button></div><p class="agri-muted">没有足够依据时，助手会继续询问。现场处置请先核实。</p></div><article v-for="(message, i) in messages" :key="i" :class="['agri-message', message.role]"><small><BrandMark v-if="message.role !== 'user'" class="agri-message-avatar" />{{ message.role === 'user' ? '我' : '澍雨 Agent' }}</small><img v-for="id in message.assetIds?.filter(id => assets.some(asset => asset.id === id && asset.kind === 'image')) || []" :key="id" class="agri-message-photo" :src="agricultureAssetContentUrl(gardenId, id)" alt="本次现场照片"><div class="agri-message-body"><p v-for="(line,lineIndex) in messageLines(message.content || (generating ? '正在整理现场信息…' : '未生成答案'))" :key="lineIndex" :class="{'message-list-line':line.bullet}"><span v-if="line.bullet" aria-hidden="true">• </span><template v-for="(part,partIndex) in line.parts" :key="partIndex"><strong v-if="part.startsWith('**') && part.endsWith('**')">{{ part.slice(2,-2) }}</strong><span v-else>{{ part }}</span></template></p></div><button v-if="message.role === 'assistant' && i === messages.length - 1 && !generating && message.content?.trim()" class="mobile-answer-task" @click="createAnswerTask(message)"><i class="bi bi-clipboard-check" aria-hidden="true"></i> 生成检查任务</button></article><div v-if="uploadedAsset" class="mobile-upload-receipt"><img v-if="uploadedAsset.kind === 'image'" :src="agricultureAssetContentUrl(gardenId, uploadedAsset.id)" alt="本次上传的照片"><button class="upload-dismiss" aria-label="关闭上传卡片" @click="uploadedAsset = null">×</button><span>{{ label(uploadedAsset) }} · {{ mediaAssetId === uploadedAsset.id && mediaTurn ? '处理状态见下方' : uploadedAsset.kind === 'image' ? '照片已保存，尚未分析' : '已保存，尚未转写' }}</span><button v-if="uploadedAsset.kind === 'image'" class="agri-primary" :disabled="busy || generating" @click="processAsset(uploadedAsset)">✧ 分析照片</button><button v-if="uploadedAsset.kind === 'audio'" :disabled="busy || generating" @click="processAsset(uploadedAsset, 'transcribe')">转成文字</button><button @click="toggle(assetIds, uploadedAsset.id)">{{ assetIds.includes(uploadedAsset.id) ? '取消本轮引用' : '加入本轮' }}</button></div><section v-if="mediaTurn" class="mobile-media-result" role="status"><strong>{{ mediaTurn.processingKind === 'audio_transcription' ? '录音转写' : '照片分析' }} · {{ statusLabel(mediaTurn.status) }}</strong><p v-if="mediaTurn.error">{{ typeof mediaTurn.error === 'string' ? mediaTurn.error : mediaTurn.error.message }}</p><template v-if="s.artifact?.turnId === mediaTurnId"><p>{{ s.artifact.body }}</p><button v-if="assets.find(row => row.id === mediaAssetId)?.kind === 'image'" @click="continueWithPhoto">结合这张继续问</button><p v-else>文字已加入可编辑草稿，核对后发送。</p></template></section><div v-if="s.activeTurn?.toolEvents?.length" class="agri-tool-events"><p v-for="(event,index) in s.activeTurn.toolEvents" :key="index">{{ event.label || event.name }} · {{ statusLabel(event.status) }}</p></div><p v-if="generating" class="agri-progress" role="status">{{ phase || '正在处理' }} <button @click="cancel" :disabled="!taskId">停止生成</button></p></div><button v-if="sourceRows(s.artifact?.sources).length" class="agri-source-button" @click="showAnswerSources">查看本轮来源 ↗</button><p v-if="s.error" class="agri-error" role="alert">{{ s.error }}</p><p v-if="s.pollError" class="agri-error">{{ s.pollError }}</p><p v-if="savedTurnError(s.latestTurn)" class="agri-error saved-turn-error">{{ savedTurnError(s.latestTurn) }}</p><button v-if="s.pending" @click="send(true)">确认原请求（使用相同编号）</button><div class="agri-citations" v-if="assetIds.length || knowledgeIds.length">已选 {{ assetIds.length }} 份资料 · {{ knowledgeIds.length }} 条知识 <button :disabled="creatingThread" @click="assetIds = []; knowledgeIds = []">清除</button></div><p v-if="error && tab === 'chat'" class="agri-error" role="alert">{{ error }}</p><p v-if="notice && tab === 'chat'" class="agri-notice" role="status">{{ notice }}</p><div class="agri-skill-bar"><select v-model="s.skillId" aria-label="本轮技能" :disabled="creatingThread || !!s.pending || generating"><option v-if="!skills.length" value="shuyu.analyze.v1">通用分析</option><option v-for="skill in skills" :key="skill.id" :value="skill.id">{{ skill.label }}</option></select><button v-if="selectedSkill?.kind === 'chat'" @click="suggestSkill">建议问题</button><button v-if="skillsError" @click="loadSkills">{{ skillsError }}</button><small v-if="selectedSkill && selectedSkill.kind !== 'chat'">发送所选单个文件至模型服务，录音包含整段内容</small></div><div v-if="tab === 'chat'" class="mobile-round-context" aria-label="本轮上下文"><span>本轮</span><button type="button" :disabled="creatingThread" @click="dialog = 'settings'">{{ selectedSkill?.label || '通用分析' }}⌄</button><button type="button" :disabled="creatingThread" @click="resourcesTab = 'assets'; resourcesOpen = true">资料 · {{ assetIds.length + knowledgeIds.length }}⌄</button></div><form class="agri-composer" :class="{'composer-locked':creatingThread}" @submit.prevent="send"><button type="button" class="mobile-voice" aria-label="录制语音" @click="voiceOpen = true"><i class="bi bi-mic" aria-hidden="true"></i></button><div class="agri-upload-buttons"><button type="button" aria-label="上传资料" @click="chooseUpload('document')" :disabled="!gardenId"><i class="bi bi-image"></i></button><button type="button" aria-label="上传现场照片" @click="chooseUpload('image')" :disabled="!gardenId"><i class="bi bi-camera"></i></button><button type="button" aria-label="上传语音" @click="chooseUpload('audio')" :disabled="!gardenId"><i class="bi bi-mic"></i></button></div><textarea @keydown.ctrl.enter.prevent="send()" @keydown.meta.enter.prevent="send()" v-model="draft" aria-label="描述现场或询问下一步" placeholder="说说园里的情况…" rows="2" :disabled="!gardenId || creatingThread"></textarea><button type="button" class="mobile-more" aria-controls="chat-tools" aria-label="照片与更多" :aria-expanded="toolsOpen" :disabled="creatingThread" @click="toolsOpen = !toolsOpen">＋</button><button class="agri-send" :class="{'mobile-send-empty':!canSend}" aria-label="发送" :disabled="!gardenId || creatingThread || generating || !canSend">➤</button><div v-if="toolsOpen" ref="toolsElement" id="chat-tools" role="group" class="mobile-chat-tools" aria-label="对话工具"><button type="button" v-for="tool in [{icon:'camera',label:'拍照 / 相册',action:()=>chooseUpload('image')},{icon:'mic',label:'录制语音',action:()=>voiceOpen=true},{icon:'mic',label:'录音文件',action:()=>chooseUpload('audio')},{icon:'journal-text',label:'上传资料',action:()=>chooseUpload('document')},{icon:'clipboard-check',label:'待办',action:()=>open('task')},{icon:'gear',label:'设置',action:()=>open('settings')}]" :key="tool.label" @click="toolAction(tool.action)"><i :class="['bi','bi-'+tool.icon]" aria-hidden="true"></i><span>{{ tool.label }}</span></button></div></form></aside>
    <nav class="mobile-workspace-nav" aria-label="手机工作台"><button v-for="item in mobileTabs" :key="item.id" :class="{active: item.id === tab || (item.id === 'overview' && ['monitor','tasks','devices'].includes(tab))}" @click="tab = item.id; mobileMenuOpen = false"><i :class="`bi bi-${item.icon}`" aria-hidden="true"></i><span>{{ item.label }}</span></button></nav>
    <input ref="uploadInput" class="agri-hidden" type="file" :capture="uploadKind === 'image' ? 'environment' : undefined" :accept="uploadKind === 'image' ? 'image/*' : uploadKind === 'audio' ? 'audio/*' : '.txt,.md,.pdf,.docx,.pptx,.csv'" @change="upload">
    <div v-if="dialog || sourceText || readingItem" class="agri-modal-backdrop" :class="{'complete-page-backdrop':['complete','learning','garden','plot'].includes(dialog), 'task-confirm-backdrop':dialog === 'task'}" @click.self="dialog = ''; closeReader()"><section ref="modalElement" tabindex="-1" class="agri-modal" :class="{'complete-page-modal':['complete','learning','garden','plot'].includes(dialog), 'reader-modal':readingItem, 'task-confirm-modal':dialog === 'task'}" role="dialog" aria-modal="true" aria-label="园区记录"><button class="agri-close" @click="dialog = ''; closeReader()">{{ dialog === 'learning' ? '‹ 返回学习' : ['complete','task','garden','plot'].includes(dialog) ? '‹ 返回' : '关闭 ✕' }}</button><KnowledgeReader @learn="learn" @ask="askKnowledge" @speak="speak(sourceText)" @stop="stopSpeaking" :speaking="speaking" :speech-message="speechMessage" v-if="readingItem" :item="readingItem" :text="sourceText" :items="overview?.knowledge || []" :selected="knowledgeIds" :loading="sourceLoading" :error="sourceError" :fragment="sourceFragment" :download-url="readingItem.assetId ? agricultureAssetContentUrl(gardenId, readingItem.assetId) : ''" @close="closeReader" @toggle="id => toggle(knowledgeIds, id)" @article="openRelated" /><div v-else-if="sourceText"><img v-if="liveSourceCapture && sourceText.startsWith('模拟抓拍来源')" :src="agricultureAssetContentUrl(gardenId, liveSourceCapture.assetId)" alt="模拟抓拍来源画面" style="width:100%;border-radius:10px"><pre>{{ sourceText }}</pre></div><section v-else-if="dialog === 'settings'" class="agri-data-use"><h2>对话设置</h2><label>本轮技能<select v-model="s.skillId" :disabled="creatingThread || !!s.pending || generating"><option v-if="!skills.length" value="shuyu.analyze.v1">通用分析</option><option v-for="skill in skills" :key="skill.id" :value="skill.id">{{ skill.label }}</option></select></label><button v-if="selectedSkill?.kind === 'chat'" @click="suggestSkill">建议问题</button><button v-if="skillsError" @click="loadSkills">重试加载技能</button><label class="agri-history-choice"><input v-model="s.includeHistory" type="checkbox" :disabled="!!s.pending || s.submitting">带入本对话最近6轮</label><p>默认不带历史。开启后，历史可能包含此前使用过的资料。</p><h3>数据如何使用</h3><p>普通对话可读取当前园区的监测与农事记录，按所选地块限定范围。只有明确选择的资料和知识加入本轮；上传仅保存。</p><p>发送后，选中内容交给配置的模型服务；本地服务器保留任务记录。照片分析与录音转写只处理所选文件，不带对话历史。</p></section><form v-else :class="{'mobile-completion-form':['complete','learning','garden','plot'].includes(dialog), 'learning-note-form':dialog === 'learning', 'mobile-action-form':dialog === 'task'}" @submit.prevent="save"><h2>{{ ({ garden: '创建园区', plot: '添加地块', task: sourceReport ? '复盘与下一步' : '新建待办', device: '登记设备', event: '录入手工测试事件', learning: '写下这次学到的', complete: '记录实际情况', followup: '授权有限次自动跟进', thread: '开始新的现场对话' })[dialog] }}</h2><div v-if="dialog === 'garden' || dialog === 'plot'" class="setup-illustration" aria-label="园区插画示意"></div><article v-if="dialog === 'task' && sourceReport" class="completion-task-summary"><small>复盘与下一步 · 来源报告</small><h3>{{ sourceReport.title }}</h3><p>已有待办建议：{{ sourceReport.task.title }}</p></article><article v-if="dialog === 'learning'" class="completion-task-summary learning-source-card"><div class="learning-source-cover" aria-label="农业知识插画示意"></div><small>学习笔记</small><strong>{{ overview?.knowledge?.find(item => item.id === selectedDevice)?.title }}</strong><p>{{ overview?.knowledge?.find(item => item.id === selectedDevice)?.summary }}</p></article><article v-if="dialog === 'complete'" class="completion-task-summary">{{ tasks.find(item => item.id === selectedDevice)?.title }}</article><label v-if="dialog !== 'followup'">{{ dialog === 'event' ? '监测指标' : dialog === 'learning' ? '我的理解与答案' : dialog === 'complete' ? '实际处理与现场结果' : '名称' }}<select v-if="dialog === 'event'" v-model="formName" required><option value="" disabled>请选择指标</option><option value="temperature">空气温度 °C</option><option value="humidity">空气湿度 %</option></select><textarea v-else-if="dialog === 'learning'" v-model="formName" required maxlength="4000" rows="5" aria-label="我的理解"></textarea><textarea v-else-if="dialog === 'complete'" v-model="formName" required maxlength="4000" rows="5" aria-label="实际处理与现场结果"></textarea><input v-else v-model="formName" required maxlength="160"></label><label v-if="dialog !== 'complete' && dialog !== 'garden' && dialog !== 'followup' && dialog !== 'thread'">{{ dialog === 'garden' ? '位置' : dialog === 'plot' ? '作物' : dialog === 'event' ? '数值（手工）' : dialog === 'device' ? '设备类型' : dialog === 'learning' ? '还不清楚的问题与下一步' : '现场说明' }}<select v-if="dialog === 'device'" v-model="formDetail"><option value="sensor">环境传感器</option><option value="camera">摄像头</option></select><textarea v-else-if="dialog === 'task'" v-model="formDetail" maxlength="4000" rows="5" aria-label="现场说明"></textarea><textarea v-else-if="dialog === 'learning'" v-model="formDetail" maxlength="4000" rows="5" aria-label="还不清楚的问题"></textarea><input v-else v-model="formDetail" :type="dialog === 'event' ? 'number' : 'text'" :step="dialog === 'event' ? 'any' : undefined"></label><label v-if="dialog === 'device'">所属地块<select v-model="plotId" required><option value="" disabled>请先选择地块</option><option v-for="plot in overview?.plots || []" :key="plot.id" :value="plot.id">{{ label(plot) }}</option></select></label><template v-if="dialog === 'device'"><label>关注指标（阈值可留空）<select v-model="thresholdMetric"><option value="temperature">空气温度 °C</option><option value="humidity">空气湿度 %</option></select></label><label>下限<input v-model="thresholdMin" type="number" step="any"></label><label>上限<input v-model="thresholdMax" type="number" step="any"></label></template><label v-if="dialog === 'task' || dialog === 'followup'">到期跟进时间<input v-model="formDue" type="datetime-local" :required="dialog === 'followup'"></label><template v-if="dialog === 'followup'"><p>明确授权在此园区读取新数据并调用模型。到达次数或预算即停止；可随时撤销。</p><label>最大执行次数<input v-model="followRuns" type="number" min="1" max="30" required></label><label>间隔秒数（留空只执行一次）<input v-model="followInterval" type="number" min="60"></label><label>每次最多模型调用数<input v-model="followBudget" type="number" min="1" max="8" required></label></template><fieldset v-if="dialog === 'complete'"><legend>现场照片</legend><button type="button" @click="chooseUpload('image')">＋ 添加照片</button><label v-for="asset in assets.filter(row => row.kind === 'image')" :key="asset.id"><input type="checkbox" :checked="completionAssetIds.includes(asset.id)" @change="toggle(completionAssetIds, asset.id)"><img :src="agricultureAssetContentUrl(gardenId, asset.id)" alt="可选现场照片" class="completion-thumbnail">{{ label(asset) }}</label></fieldset><p v-if="error" class="agri-error">{{ error }}</p><button class="agri-primary" :disabled="busy">{{ busy ? '保存中…' : dialog === 'complete' ? '保存并完成任务' : dialog === 'learning' ? '保存学习记录' : dialog === 'task' && sourceReport ? '确认并创建待办' : '保存记录' }}</button><button v-if="dialog === 'learning'" type="button" class="learning-continue" @click="continueLearningDraft">带着这篇继续问（不保存笔记）</button></form></section></div>
    <div v-if="reportScopeOpen" class="agri-modal report-scope-modal" role="dialog" aria-modal="true" aria-label="选择报告范围"><section><button @click="reportScopeOpen = false">返回</button><h2>生成工作简报</h2><p>选择需要汇总的任务与记录</p><details><summary>已有报告（{{ overview?.reports?.length || 0 }}）</summary><button v-for="item in overview?.reports || []" :key="item.id" :disabled="item.unavailable" @click="reportScopeOpen = false; viewSource(item, 'reports')">{{ item.title || '园区报告' }}</button></details><label>所属地块<select v-model="plotId"><option value="">全部地块</option><option v-for="plot in overview?.plots || []" :key="plot.id" :value="plot.id">{{ label(plot) }}</option></select></label><label class="report-task-choice" v-for="item in reportCandidates" :key="item.id"><input type="checkbox" v-model="reportSelection" :value="item.id">{{ item.title }}</label><p v-if="!reportCandidates.length">当前地块暂无可汇总任务</p><button class="agri-primary" :disabled="busy || !reportSelection.length" @click="generateReport">生成简报 · {{ reportSelection.length }}项</button></section></div>
    <div v-if="onboarding" class="onboarding-screen" :class="{'onboarding-behind-form':dialog}"><template v-if="onboarding === 'choose'"><h1>选择园区</h1><p>选择要进入的园区，开始管理农事。</p><button v-for="item in gardens" :key="item.id" class="onboarding-garden" :class="{selected:onboardingGarden === item.id}" @click="onboardingGarden = item.id"><div class="onboarding-cover" role="img" aria-label="园区插画示意"></div><h2>{{ label(item) }}</h2><span>{{ onboardingGarden === item.id ? '✓ 已选择' : '选择园区' }}</span></button><button class="onboarding-option" @click="open('garden')">＋ 新建园区</button><button class="agri-primary" :disabled="!onboardingGarden" @click="gardenId = onboardingGarden; onboarding = ''">进入园区 →</button><button @click="onboarding = ''">返回</button></template><template v-else-if="onboarding === 'plot'"><h1>添加地块</h1><p>完善地块的基本信息，方便后续记录与查看。</p><div class="onboarding-cover"></div><button class="agri-primary" @click="open('plot')">＋ 添加地块</button><button @click="onboarding = ''">稍后添加，进入园区</button></template><template v-else><img class="onboarding-mascot" src="/brand/shuyu-raindrop-v1.png" alt="澍雨"><h1>园区准备好了</h1><p>现在可以开始记录和管理你的园区了。</p><article class="onboarding-option"><h2>{{ garden?.name }}</h2><p>{{ overview?.plots?.map(item => item.name).join('、') }}</p></article><button class="onboarding-option" @click="onboarding = ''; tab = 'overview'">园区 · 看现场与待办 ›</button><button class="onboarding-option" @click="onboarding = ''; tab = 'knowledge'">学习 · 查农业资料 ›</button><button class="agri-primary" @click="onboarding = ''; tab = 'overview'">去看看园区 →</button></template></div>
    <ReportDocument v-if="reportItem" :report="reportItem" :busy="busy" :error="error" :notice="notice" @close="reportItem = null" @next-step="reportNextStep" @export="format => exportReport(reportItem, format)" /><div v-if="voiceOpen" class="voice-overlay"><VoiceRecorder :key="`${s.sessionEpoch}:${gardenId}`" @close="voiceOpen = false" @fallback="chooseUpload('audio')" @file="file => { uploadKind = 'audio'; upload({file}) }"/></div>
  </div>
</template>
