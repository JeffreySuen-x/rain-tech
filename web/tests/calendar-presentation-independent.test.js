import { expect, it } from 'vitest'
import { displayDate, displayDay, displayMonth } from '../src/agriculture/calendarPresentation.js'
it('independent Gregorian edge cases accept leap days and reject rollover, timestamps and other types',()=>{
 expect(displayDay('2024-02-29')).toBe(29)
 expect(displayMonth('2024-02-29')).toBe('2月')
 for(const value of ['2023-02-29','2026-04-31','2026-00-10','2026-10-00','2026-10-27T00:00:00Z',' 2026-10-27',null,123,{},'2026-1-01']){
  expect(displayDate(value)).toBe('日期暂不可用');expect(displayDay(value)).toBe('—');expect(displayMonth(value)).toBe('待更新')
 }
})
it('independent server dates retain weekday and date under an overseas process time zone',()=>{
 expect(displayDate('2026-10-27')).toContain('27日')
 expect(displayDate('2026-10-27')).toContain('周二')
 expect(displayDay('2026-01-01')).toBe(1)
})
