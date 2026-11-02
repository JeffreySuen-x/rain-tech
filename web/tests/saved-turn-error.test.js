import {expect,it} from 'vitest'
import {readFileSync} from 'node:fs'
import {savedTurnError} from '../src/agriculture/presentation.js'
it('labels stored request failures with provenance and request time',()=>{
 const result=savedTurnError({error:'服务器尚未配置模型服务',createdAt:1700000000})
 expect(result).toContain('上次请求未完成（已保存记录 · ')
 expect(result).toContain('服务器尚未配置模型服务')
 expect(result).toContain(new Date(1700000000000).toLocaleString())
 expect(savedTurnError({error:{message:'synthetic'},createdAt:'invalid'})).toBe('上次请求未完成（已保存记录）：synthetic')
 expect(savedTurnError({})).toBe('')
})
it('keeps current operation alerts separate from persisted turn failure text',()=>{
 const source=readFileSync(new URL('../src/agriculture/AgricultureWorkbench.vue',import.meta.url),'utf8')
 expect(source).toContain('v-if="s.error" class="agri-error" role="alert">{{ s.error }}')
 expect(source).toContain('class="agri-error saved-turn-error">{{ savedTurnError(s.latestTurn) }}')
})
