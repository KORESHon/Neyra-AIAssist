const TOKEN_KEY = 'neyra_api_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? ''
}

export function setToken(t: string): void {
  const s = t.trim()
  if (s) localStorage.setItem(TOKEN_KEY, s)
  else localStorage.removeItem(TOKEN_KEY)
}

function headers(): HeadersInit {
  const h: Record<string, string> = { Accept: 'application/json' }
  const tok = getToken().trim()
  if (tok) h.Authorization = `Bearer ${tok}`
  return h
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(path, { headers: headers() })
  const j = (await r.json()) as T & { ok?: boolean; error?: { message?: string } }
  if (!r.ok) {
    const msg = (j as { error?: { message?: string } }).error?.message ?? r.statusText
    throw new Error(msg || `HTTP ${r.status}`)
  }
  if (j && typeof j === 'object' && 'ok' in j && j.ok === false) {
    const msg = (j as { error?: { message?: string } }).error?.message ?? 'API error'
    throw new Error(msg)
  }
  return j as T
}
