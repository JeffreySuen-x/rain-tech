import { afterEach, expect, it, vi } from 'vitest'
import { createRenderer, nextTick } from 'vue'
import { useLiveDemo } from '../src/agriculture/useLiveDemo.js'
import { request } from '../src/api.js'
vi.mock('../src/api.js', () => ({request:vi.fn()}))
let app
afterEach(() => { app?.unmount(); vi.unstubAllGlobals(); vi.clearAllMocks() })

it('independently retries an uncertain write with its exact receipt after read reconciliation', async () => {
  vi.stubGlobal('document', {hidden:false, addEventListener(){}, removeEventListener(){}})
  vi.stubGlobal('crypto', {randomUUID:vi.fn(()=>'independent-command')})
  const facts={enabled:true,version:5}
  let writes=0
  request.mockImplementation((_url, opts={}) => {
    if(opts.method==='POST') {
      writes++
      return writes===1 ? Promise.reject(new Error('response lost')) : Promise.resolve({liveDemo:{enabled:true,version:4}})
    }
    return Promise.resolve({liveDemo:facts})
  })
  let hook
  const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
  app=renderer.createApp({setup(){hook=useLiveDemo(()=>({workspaceId:'w',plotId:'p'}),()=> 'csrf');return ()=>null}})
  app.mount({})
  await nextTick();await Promise.resolve()
  await hook.action('camera.capture',{cameraId:'demo-camera-1'})
  expect(hook.uncertain.value).toBe(true)
  const receipt=structuredClone(request.mock.calls.find(([,o])=>o?.method==='POST')[1].body)
  await hook.reconcile()
  expect(hook.uncertain.value).toBe(true)
  await hook.action('robot.start')
  expect(writes).toBe(1)
  await hook.retry()
  const posted=request.mock.calls.filter(([,o])=>o?.method==='POST')
  expect(posted).toHaveLength(2)
  expect(posted[1][1].body).toEqual(receipt)
  expect(hook.uncertain.value).toBe(false)
  expect(hook.live.value.version).toBe(5)
})
