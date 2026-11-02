// The server's Shanghai calendar date is the sole source; never substitute the client clock.
function calendarDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const date = new Date(`${value}T12:00:00+08:00`)
  if (!Number.isFinite(date.getTime()) || new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date) !== value) return null
  return date
}
export function displayDate(value) {
  const date = calendarDate(value)
  return date ? new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'short', timeZone: 'Asia/Shanghai' }).format(date).replace('周', ' · 周') : '日期暂不可用'
}
export function displayDay(value) { return calendarDate(value) ? Number(value.slice(-2)) : '—' }
export function displayMonth(value) { return calendarDate(value) ? `${Number(value.slice(5, 7))}月` : '待更新' }
export function displayLunar(value) { return typeof value === 'string' && value.trim() ? `农历 ${value.replace(/^.*?年/, '').replace(/^农历\s*/, '').trim()}` : '农历暂不可用' }
