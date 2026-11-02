import { expect, it } from 'vitest'
import { reportKindLabel, metricLabel, statusLabel, deviceKindLabel, observationSourceLabel } from '../src/agriculture/presentation.js'
it('labels domain values in Chinese without mutating device state or treating a test as hardware',()=>{
  expect(metricLabel('temperature')).toBe('空气温度');expect(metricLabel('humidity')).toBe('空气湿度');const device={kind:'sensor',connectionStatus:'unconnected',source:'test'}
  expect(deviceKindLabel(device.kind)).toBe('环境传感器');expect(statusLabel(device.connectionStatus)).toBe('待接入');expect(observationSourceLabel(device.source)).toBe('手工测试');expect(device.connectionStatus).toBe('unconnected')
  expect(statusLabel('open')).toBe('待处理');expect(statusLabel('completed')).toBe('已完成');expect(statusLabel(undefined,'事实报告')).toBe('事实报告');expect(observationSourceLabel('device')).toBe('设备上报');expect(observationSourceLabel(undefined)).toBe('来源未标明')
})

it('distinguishes model follow-up reports from deterministic fact summaries',()=>{
  expect(reportKindLabel({generationType:'agent_followup'})).toBe('Agent跟进报告');expect(reportKindLabel({type:'agent_followup'})).toBe('Agent跟进报告');expect(reportKindLabel({generationType:'deterministic_facts'})).toBe('事实简报');expect(reportKindLabel({type:'fact_summary'})).toBe('事实简报');expect(reportKindLabel({})).toBe('园区报告');expect(statusLabel('scheduled')).toBe('待执行')
})
