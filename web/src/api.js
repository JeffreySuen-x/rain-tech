export class ApiError extends Error {
  constructor(message, code, status) { super(message); this.code = code; this.status = status }
}
export async function request(path, { method = 'GET', body, csrf = '', signal } = {}) {
  let response
  try {
    response = await fetch(`/api/v1${path}`, {
      method, signal, credentials: 'same-origin', headers: {
        ...(body === undefined || body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...(method === 'GET' ? {} : { 'X-CSRF-Token': csrf }),
      }, ...(body === undefined ? {} : { body: body instanceof FormData ? body : JSON.stringify(body) }),
    })
  } catch (error) { if (error.name === 'AbortError') throw error; throw new ApiError('暂时连接不到服务器。请检查连接后重试。', 'network_error', 0) }
  if (response.status === 204) return null
  let data
  try { data = await response.json() } catch (error) { if (error.name === 'AbortError') throw error; throw new ApiError('服务器返回了无法读取的响应。', 'invalid_response', response.status) }
  if (!response.ok) throw new ApiError(data.error?.message || '请求未完成，请稍后重试。', data.error?.code || 'request_failed', response.status)
  return data
}
