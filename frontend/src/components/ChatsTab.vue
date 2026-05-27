<template>
  <div class="tab-pane active">
    <div class="chat-controls">
      <!-- Search box -->
      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input
          ref="searchInput"
          class="search-input"
          v-model="search"
          type="text"
          placeholder="Поиск по названию, @username… (нажмите /)"
          @keydown.escape="clearSearch"
        />
        <span v-if="search" class="search-clear" @click="clearSearch">✕</span>
        <span v-if="search" class="search-count">
          {{ filtered.length }} / {{ baseFiltered.length }}
        </span>
      </div>

      <button class="filter-btn" v-for="f in filters" :key="f.id"
              :class="{ active: activeFilter === f.id }"
              @click="activeFilter = f.id">{{ f.label }}</button>
      <button class="btn btn-primary btn-sm" @click="loadChats">↻ Обновить</button>
      <button class="btn btn-success btn-sm" :disabled="saving" @click="saveBackup">
        {{ saving ? '…' : '💾 Сохранить в MD' }}
      </button>
      <a class="btn btn-sm" href="/api/chats/export-csv" style="background:var(--card);color:var(--text);">⬇ CSV</a>
      <a class="btn btn-sm" href="/api/chats/export-xlsx" style="background:var(--card);color:var(--text);">⬇ Excel</a>
    </div>
    <div class="alert" :class="alertType === 'success' ? 'alert-success show' : 'alert-error show'"
         v-if="alertMsg" style="margin-bottom:12px;">{{ alertMsg }}</div>

    <div id="chats-container">
      <div v-if="loading" class="loading-row"><div class="spinner"></div> Загрузка чатов…</div>
      <div v-else-if="error" class="alert alert-error show">{{ error }}</div>
      <div v-else-if="!filtered.length" class="empty-search">
        <div v-if="search">
          <div style="font-size:32px;margin-bottom:8px;">🔍</div>
          <div>Ничего не найдено по запросу <strong>«{{ search }}»</strong></div>
          <button class="btn btn-ghost btn-sm" style="margin-top:12px;" @click="clearSearch">Сбросить поиск</button>
        </div>
        <div v-else>Чатов не найдено</div>
      </div>
      <div v-else class="chat-table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Название</th><th>Тип</th><th>Ссылка</th><th>Участников</th><th>Экспорт</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in filtered" :key="c.id">
              <td>
                <span v-if="search" v-html="highlight(c.title)"></span>
                <span v-else>{{ c.title }}</span>
              </td>
              <td>
                <span class="badge" :class="c.archived ? 'badge-archive' : c.type === 'channel' ? 'badge-channel' : 'badge-group'">
                  {{ c.archived ? 'Архив' : c.type === 'channel' ? 'Канал' : 'Группа' }}
                </span>
              </td>
              <td>
                <a v-if="c.link" :href="c.link" target="_blank" class="chat-link">
                  <span v-if="search" v-html="highlight('@' + c.username)"></span>
                  <span v-else>{{ c.username }}</span>
                </a>
                <span v-else style="color:var(--subtext);font-size:12px">приватный</span>
              </td>
              <td>{{ c.members_count ? c.members_count.toLocaleString() : '—' }}</td>
              <td>
                <button v-if="!exports[c.id] || exports[c.id].status === 'not_started'"
                        class="btn btn-sm btn-primary"
                        style="font-size:12px;padding:5px 10px;"
                        @click="startExport(c)">Экспорт</button>
                <div v-else-if="exports[c.id].status === 'running'" style="min-width:120px;">
                  <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--subtext);margin-bottom:3px;">
                    <span>{{ exports[c.id].progress }} / {{ exports[c.id].total || '?' }}</span>
                    <span>{{ exports[c.id].total ? Math.round(exports[c.id].progress / exports[c.id].total * 100) : 0 }}%</span>
                  </div>
                  <div class="progress-bar-wrap" style="height:5px;"><div class="progress-bar" :style="{ width: exports[c.id].total ? (exports[c.id].progress / exports[c.id].total * 100) + '%' : '0%' }"></div></div>
                </div>
                <div v-else-if="exports[c.id].status === 'done'" style="display:flex;gap:6px;">
                  <a :href="'/api/export/' + c.id + '/download'" class="btn btn-sm btn-success" style="font-size:12px;padding:5px 10px;">⬇ Скачать</a>
                  <button class="btn btn-sm" style="font-size:12px;padding:5px 8px;background:var(--card);color:var(--text);" @click="resetExport(c.id)">↺</button>
                </div>
                <span v-else-if="exports[c.id].status === 'error'" style="color:var(--danger);font-size:12px;">{{ exports[c.id].error || 'Ошибка' }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api.js'

const chats = ref([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const searchInput = ref(null)
const activeFilter = ref('all')
const exports = ref({})
const saving = ref(false)
const alertMsg = ref('')
const alertType = ref('success')

const filters = [
  { id: 'all', label: 'Все' },
  { id: 'group', label: 'Группы' },
  { id: 'channel', label: 'Каналы' },
  { id: 'archived', label: 'Архив' },
]

// Filtered by tab only (for the N/M counter denominator)
const baseFiltered = computed(() => {
  let list = chats.value
  if (activeFilter.value === 'archived') return list.filter(c => c.archived)
  if (activeFilter.value !== 'all') return list.filter(c => c.type === activeFilter.value && !c.archived)
  return list
})

const filtered = computed(() => {
  let list = baseFiltered.value
  const q = search.value.trim().toLowerCase()
  if (!q) return list
  return list.filter(c =>
    c.title.toLowerCase().includes(q) ||
    (c.username && c.username.toLowerCase().includes(q))
  )
})

function highlight(text) {
  if (!search.value || !text) return text
  const q = search.value.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.replace(new RegExp(q, 'gi'), m => `<mark class="hl">${m}</mark>`)
}

function clearSearch() {
  search.value = ''
  searchInput.value?.focus()
}

function onKeydown(e) {
  if (e.key === '/' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
    e.preventDefault()
    searchInput.value?.focus()
  }
}

async function loadChats() {
  loading.value = true; error.value = ''
  const res = await api('/api/chats')
  loading.value = false
  if (res.error) error.value = res.error
  else chats.value = res.chats || []
}

async function startExport(chat) {
  exports.value[chat.id] = { status: 'running', progress: 0, total: 0 }
  await api(`/api/export/${chat.id}/start`, { method: 'POST', body: JSON.stringify({ limit: 0 }) })
  pollExport(chat.id)
}

function pollExport(chatId) {
  const interval = setInterval(async () => {
    const s = await api(`/api/export/${chatId}/status`)
    exports.value[chatId] = s
    if (s.status === 'done' || s.status === 'error') clearInterval(interval)
  }, 1500)
}

function resetExport(chatId) {
  delete exports.value[chatId]
}

async function saveBackup() {
  saving.value = true; alertMsg.value = ''
  const res = await api('/api/backup/now', { method: 'POST' })
  saving.value = false
  if (res.success) { alertType.value = 'success'; alertMsg.value = `✓ Сохранено ${res.count} чатов → ${res.file}` }
  else { alertType.value = 'error'; alertMsg.value = res.error || 'Ошибка' }
  setTimeout(() => alertMsg.value = '', 5000)
}

onMounted(() => { loadChats(); document.addEventListener('keydown', onKeydown) })
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.search-wrap {
  position: relative;
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 220px;
  max-width: 380px;
}
.search-icon {
  position: absolute;
  left: 10px;
  font-size: 14px;
  pointer-events: none;
  opacity: .6;
}
.search-wrap .search-input {
  width: 100%;
  padding-left: 32px;
  padding-right: 80px;
}
.search-clear {
  position: absolute;
  right: 52px;
  cursor: pointer;
  font-size: 13px;
  color: var(--subtext);
  padding: 4px 6px;
  border-radius: 4px;
  line-height: 1;
}
.search-clear:hover { color: var(--text); }
.search-count {
  position: absolute;
  right: 8px;
  font-size: 11px;
  color: var(--subtext);
  white-space: nowrap;
  pointer-events: none;
}
.empty-search {
  text-align: center;
  padding: 60px 24px;
  color: var(--subtext);
}
</style>
