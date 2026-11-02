import { request } from '../api.js'
export const agricultureCommandId = () => crypto.randomUUID()
export const listGardens = () => request('/workspaces')
export const readGarden = (id, signal) => request(`/workspaces/${encodeURIComponent(id)}/agriculture`, { signal })
export const agricultureRead = (path, signal) => request(`/${path}`, { signal })
export function agricultureWrite(path, data, csrf) {
  const multipart = data instanceof FormData
  if (multipart && !data.has('commandId')) data.set('commandId', agricultureCommandId())
  return request(`/${path}`, { method: 'POST', csrf, body: multipart ? data : { commandId: agricultureCommandId(), ...data } })
}
export const agricultureAssetContentUrl = (_workspaceId, id) => `/api/v1/assets/${encodeURIComponent(id)}/content`
