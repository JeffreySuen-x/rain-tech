// Navigation and search operate on the complete authorized collection before pagination.
export const memberships = item => item.library?.memberships || []
export function libraryTracks(items) {
  const tracks = new Map()
  for (const item of items) for (const m of memberships(item)) {
    if (!tracks.has(m.trackId)) tracks.set(m.trackId, {id:m.trackId, title:m.trackTitle, groups:new Map(), count:0, order:Infinity})
    const track = tracks.get(m.trackId)
    const order = Number.isFinite(m.order) ? m.order : Infinity
    track.order = Math.min(track.order, order)
    if (!track.groups.has(m.groupId)) track.groups.set(m.groupId, {id:m.groupId, title:m.groupTitle, order})
    else track.groups.get(m.groupId).order = Math.min(track.groups.get(m.groupId).order, order)
  }
  for (const track of tracks.values()) track.count = items.filter(item => memberships(item).some(m => m.trackId === track.id)).length
  return [...tracks.values()].sort((a,b) => (a.id === 'shared' ? -1 : b.id === 'shared' ? 1 : a.order-b.order)).map(track => ({...track, groups:[...track.groups.values()].sort((a,b) => a.order-b.order)}))
}
export function libraryPage(items, {query='', track='', group='', page=1, size=12}={}) {
  const needle = query.trim().toLocaleLowerCase()
  const filtered = items.filter(item => (!track || (track === 'mine' ? !item.library : memberships(item).some(m => m.trackId === track && (!group || m.groupId === group)))))
    .filter(item => [item.title,item.summary,item.category,item.library?.articleId,...memberships(item).flatMap(m => [m.trackTitle,m.groupTitle,m.sectionLabel,m.readingGoal]),...(item.excerpts || []).map(x => x.text)].join(' ').toLocaleLowerCase().includes(needle))
  if (track && track !== 'mine') filtered.sort((a,b) => Math.min(...memberships(a).filter(m => m.trackId === track && (!group || m.groupId === group)).map(m => m.order)) - Math.min(...memberships(b).filter(m => m.trackId === track && (!group || m.groupId === group)).map(m => m.order)))
  const pages = Math.max(1,Math.ceil(filtered.length/size)), current = Math.min(pages,Math.max(1,page))
  return {items:filtered.slice((current-1)*size,current*size),total:filtered.length,pages,page:current}
}
export function readingLines(text) {
  const lines = String(text || '').split(/\r?\n/)
  let start = 0
  if (lines[0]?.replace(/^\uFEFF/,'').trim() === '---') { const end = lines.findIndex((line,i) => i > 0 && line.trim() === '---'); if (end > 0) start = end+1 }
  return lines.slice(start).map((text,i) => ({text, line:start+i+1, heading:/^#{1,6}\s/.test(text), title:text.replace(/^#{1,6}\s/, '')}))
}

// Only known leading catalog metadata is omitted from tutorial card previews.
// Readers and stored originals keep every line and the original locations.
export function knowledgePreview(item) {
  if (!item.library) return String(item.summary || (item.excerpts || []).map(x=>x.text).join('\n')).split('\n').map(x=>x.trim()).filter(x=>x && !/^#{1,6}\s/.test(x)).join(' ').replace(/\*\*/g,'').slice(0,160)
  const rows = readingLines((item.excerpts || []).map(x=>x.text).join('\n'))
  const metadata = /^(?:[-*]\s*)?(?:固定\s*ID|ID|版本|更新(?:日期|时间)?|标签|前置(?:知识|篇|条件)?|关联(?:篇|文章)?|导航|修订(?:摘要)?|来源类型)\s*[:：]/i
  let start = 0
  while (start < rows.length && (!rows[start].text.trim() || rows[start].heading || metadata.test(rows[start].text.trim()))) start++
  const paragraph = []
  for (const row of rows.slice(start)) {
    if (!row.text.trim() || row.heading) break
    paragraph.push(row.text.trim())
  }
  const text = paragraph.join(' ').replace(/\*\*/g,'')
  return text.length > 160 ? `${text.slice(0,160)}…` : text
}
