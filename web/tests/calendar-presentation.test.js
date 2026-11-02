import { expect, it, vi, afterEach } from 'vitest'
import { displayDate, displayDay, displayMonth, displayLunar } from '../src/agriculture/calendarPresentation.js'
afterEach(() => vi.useRealTimers())
it('uses server calendar day across Shanghai midnight without substituting the client date', () => {
 vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-26T16:00:01Z'))
 expect(displayDay('2026-10-26')).toBe(26)
 expect(displayDay('2026-10-27')).toBe(27)
 expect(displayDate('2026-10-27')).toContain('27')
 expect(displayMonth('2026-11-01')).toBe('11月')
})
it('shows explicit placeholders for absent or invalid calendar dates', () => {
 for (const value of [undefined, '', 'bad', '2026-02-30', '2026-13-01']) {
  expect(displayDay(value)).toBe('—'); expect(displayDate(value)).toBe('日期暂不可用')
 }
})
it('shows the supplied lunar month and day legibly', () => {
 expect(displayLunar('二〇二六年九月十七')).toBe('农历 九月十七')
 expect(displayLunar('')).toBe('农历暂不可用')
})
