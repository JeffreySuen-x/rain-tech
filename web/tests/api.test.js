import { afterEach, expect, it, vi } from 'vitest'
import { request } from '../src/api.js'
afterEach(() => vi.unstubAllGlobals())
it('uses same-origin credentials and csrf for mutations', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) }); vi.stubGlobal('fetch', fetcher)
  await request('/auth/login', { method: 'POST', csrf: 'token', body: { username: 'u', password: 'p' } })
  expect(fetcher).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ credentials: 'same-origin', headers: { 'X-CSRF-Token': 'token', 'Content-Type': 'application/json' } }))
})
it('preserves server error message and status for lifecycle decisions', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ error: { code: 'model_not_configured', message: '模型尚未配置' } }) }))
  await expect(request('/turns/t')).rejects.toMatchObject({ message: '模型尚未配置', code: 'model_not_configured', status: 503 })
})
it('handles DELETE 204 without parsing a missing JSON body', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 204 }))
  expect(await request('/memories/m', { method: 'DELETE', csrf: 'token' })).toBeNull()
})
it('sends uploaded multipart file with CSRF and lets the browser provide the boundary', async () => {
  const file = new FormData(); file.set('file', new Blob(['现场记录']), 'field.txt'); file.set('kind', 'document')
  const fetcher = vi.fn().mockResolvedValue({ok:true,status:201,json:async()=>({asset:{id:'a'}})});vi.stubGlobal('fetch',fetcher)
  await request('/workspaces/w/assets',{method:'POST',body:file,csrf:'token'})
  expect(fetcher.mock.calls[0][1].body).toBe(file)
  expect(fetcher.mock.calls[0][1].headers).toEqual({'X-CSRF-Token':'token'})
})
