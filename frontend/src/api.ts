const BASE = '' // proxy in dev, or set VITE_API_URL in production

export type Settings = {
  keywords: string[]
  negative_keywords: string[]
  authorities: { did: string; label: string }[]
}

export async function getSettings(): Promise<Settings> {
  const r = await fetch(`${BASE}/admin/settings`)
  if (!r.ok) throw new Error(r.statusText)
  return r.json()
}

export async function saveSettings(data: Settings): Promise<{ ok: boolean }> {
  const r = await fetch(`${BASE}/admin/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!r.ok) {
    const t = await r.text()
    throw new Error(t || r.statusText)
  }
  return r.json()
}

export type DevPost = {
  uri: string
  score: number
  rank_score?: number
  handle: string
  display_name: string
  text: string
  like_count: number
  repost_count: number
  reply_count: number
  created: string
  llm_status: string
  quoted_text: string
  link: string
}

export type DevFeedResponse = {
  posts: DevPost[]
  message?: string
}

export async function getDevFeed(params: {
  limit?: number
  gravity?: number
  lookback_hours?: number
  show_all?: boolean
}): Promise<DevFeedResponse> {
  const sp = new URLSearchParams()
  if (params.limit != null) sp.set('limit', String(params.limit))
  if (params.gravity != null) sp.set('gravity', String(params.gravity))
  if (params.lookback_hours != null) sp.set('lookback_hours', String(params.lookback_hours))
  if (params.show_all !== undefined) sp.set('show_all', params.show_all ? '1' : '0')
  const r = await fetch(`${BASE}/dev/feed?${sp}`)
  if (!r.ok) throw new Error(r.statusText)
  return r.json()
}

export async function deletePost(uri: string): Promise<{ ok: boolean }> {
  const r = await fetch(`${BASE}/dev/feed/delete-post`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uri }),
  })
  if (!r.ok) {
    const t = await r.text()
    throw new Error(t || r.statusText)
  }
  return r.json()
}

export async function classifyPost(uri: string, text: string, quoted_text?: string): Promise<{ ok: boolean; relevant: boolean }> {
  const body: { uri: string; text: string; quoted_text?: string } = { uri, text }
  if (quoted_text) body.quoted_text = quoted_text
  const r = await fetch(`${BASE}/dev/feed/classify-post`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const msg = typeof data.detail === 'string' ? data.detail : (data.detail?.msg ?? 'Classify failed')
    throw new Error(msg)
  }
  return data
}

export async function setPostStatus(uri: string, status: 'approved' | 'rejected'): Promise<{ ok: boolean; status: string }> {
  const r = await fetch(`${BASE}/dev/feed/set-status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uri, status }),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const msg = typeof data.detail === 'string' ? data.detail : (data.detail?.msg ?? 'Set status failed')
    throw new Error(msg)
  }
  return data
}
