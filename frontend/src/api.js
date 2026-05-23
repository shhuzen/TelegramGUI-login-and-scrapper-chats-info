export async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) }
  const token = sessionStorage.getItem('tab_token')
  if (token) headers['X-Tab-Token'] = token
  const res = await fetch(path, { ...opts, headers })
  const data = await res.json().catch(() => ({}))
  return data
}

export function setTabToken(token) {
  if (token) sessionStorage.setItem('tab_token', token)
}

export function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')
}

export function formatDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ru-RU')
  } catch { return iso }
}
