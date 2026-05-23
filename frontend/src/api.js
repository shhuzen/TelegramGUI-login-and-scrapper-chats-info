export async function api(path, opts = {}) {
  const defaults = { headers: { 'Content-Type': 'application/json' } }
  const res = await fetch(path, { ...defaults, ...opts, headers: { ...defaults.headers, ...(opts.headers || {}) } })
  const data = await res.json().catch(() => ({}))
  return data
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
