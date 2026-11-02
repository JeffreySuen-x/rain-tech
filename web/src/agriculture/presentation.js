export function assetStatusLabel(asset) {
  const status = { ready: asset.kind === 'document' ? '可阅读与引用' : '处理完成', stored: asset.kind === 'image' ? '照片已保存，尚未分析' : asset.kind === 'audio' ? '音频已保存，尚未转写' : '已保存', queued: '等待处理', processing: '正在处理', running: '正在处理', failed: '处理失败，请查看提示', error: '处理出错，请查看提示', revoked: '已移除', completed: '处理完成' }
  return status[asset.status] || '等待状态更新'
}
/** Current domain references are flat. Also unwrap a reference envelope when reading older artifacts. */
export function sourceRows(sources) {
  if (!sources) return []
  const list = Array.isArray(sources) ? sources : [sources]
  return list.filter(source => source != null).flatMap(source => Array.isArray(source?.references) ? sourceRows(source.references) : [{ title: typeof source === 'string' ? '来源' : source.title || '来源', locator: source?.locator || '', excerpt: typeof source === 'string' ? source : source.excerpt || '', version: source?.version }])
}
export const sourceText = sources => sourceRows(sources).map(source => [source.title, source.locator && `位置：${source.locator}`, source.version && `版本：${source.version}`, source.excerpt].filter(Boolean).join('\n')).join('\n\n')
const statusLabels = { scheduled:'待执行', open:'待处理', completed:'已完成', ready:'已就绪', stored:'已保存', processing:'处理中', running:'执行中', queued:'已排队', failed:'处理失败', error:'处理出错', cancelled:'已取消', needs_review:'需要核对', needs_input:'等待授权', authorized:'已授权', paused:'已暂停', disabled:'已停止', exhausted:'次数已用完', unconnected:'待接入', online:'在线', offline:'离线', stale:'数据已过期' }
export const statusLabel = (status, fallback = '等待状态更新') => statusLabels[status] || fallback
export const deviceKindLabel = kind => ({sensor:'环境传感器',camera:'摄像头'})[kind] || '农业设备'
export const observationSourceLabel = source => source === 'demo' ? '模拟数据 · 非实测' : source === 'test' ? '手工测试' : source === 'device' ? '设备上报' : '来源未标明'
export const metricLabel = metric => ({temperature:'空气温度',humidity:'空气湿度',soil_moisture:'土壤含水率'})[metric] || '监测指标'
export function reportKindLabel(report) {
  if (report.generationType === 'agent_followup' || report.type === 'agent_followup') return 'Agent跟进报告'
  if (report.generationType === 'deterministic_facts' || report.type === 'fact_summary') return '事实简报'
  return '园区报告'
}

// Persisted turn failures describe that request, not the current provider state.
export function savedTurnError(turn) {
  if (!turn?.error) return ''
  const detail = typeof turn.error === 'string' ? turn.error : turn.error.message
  if (!detail) return ''
  const date = turn.createdAt ? new Date(typeof turn.createdAt === 'number' ? turn.createdAt * 1000 : turn.createdAt) : null
  const time = date && Number.isFinite(date.getTime()) ? ` · ${date.toLocaleString()}` : ''
  return `上次请求未完成（已保存记录${time}）：${detail}`
}
