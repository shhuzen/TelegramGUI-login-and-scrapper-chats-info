<template>
  <div class="tab-pane active">
    <div class="chat-controls">
      <input class="search-input" v-model="search" type="text" placeholder="Поиск по названию..." />
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
      <div v-else-if="!filtered.length" style="text-align:center;padding:40px;color:var(--subtext);">Чатов не найдено</div>
      <div v-else class="chat-table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Название</th><th>Тип</th><th>Ссылка</th><th>Участников</th><th>Экспорт</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in filtered" :key="c.id">
              <td>{{ c.title }}</td>
              <td>
                <span class="badge" :class="c.archived ? 'badge-archive' : c.type === 'channel' ? 'badge-channel' : 'badge-group'">
                  {{ c.archived ? 'Архив' : c.type === 'channel' ? 'Канал' : 'Группа' }}
                </span>
              </td>
              <td>
                <a v-if="c.link" :href="c.link" target="_blank" class="chat-link">{{ c.username }}</a>
                <span v-else style="color:var(--subtext);font-size:12px">приватный</span>
              </td>
              <td>{{ c.members_count ? c.members_count.toLocaleString() : '—' }}</td>
              <td>
                <!-- not started -->
                <button v-if="!exports[c.id] || exports[c.id].status === 'not_started'"
                        class="btn btn-sm btn-primary"
                        style="font-size:12px;padding:5px 10px;"
                        @click="startExport(c)">Экспорт</button>
                <!-- running -->
                <div v-else-if="exports[c.id].status === 'running'" style="min-width:120px;">
                  <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--subtext);margin-bottom:3px;">
                    <span>{{ exports[c.id].progress }} / {{ exports[c.id].total || '?' }}</span>
                    <span>{{ exports[c.id].total ? Math.round(exports[c.id].progress / exports[c.id].total * 100) : 0 }}%</span>
                  </div>
                  <div class="progress-bar-wrap" style="height:5px;"><div class="progress-bar" :style="{ width: exports[c.id].total ? (exports[c.id].progress / exports[c.id].total * 100) + '%' : '0%' }"></div></div>
                </div>
                <!-- done -->
                <div v-else-if="exports[c.id].status === 'done'" style="display:flex;gap:6px;">
                  <a :href="'/api/export/' + c.id + '/download'" class="btn btn-sm btn-success" style="font-size:12px;padding:5px 10px;">⬇ Скачать</a>
                  <button class="btn btn-sm" style="font-size:12px;padding:5px 8px;background:var(--card);color:var(--text);" @click="resetExport(c.id)">↺</button>
                </div>
                <!-- error -->
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
import { ref, computed, onMounted } from 'vue'
import { api } from '../api.js'

const chats = ref([])
const loading = ref(false)
const error = ref('')
const search = ref('')
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

const filtered = computed(() => {
  let list = chats.value
  if (activeFilter.value === 'archived') list = list.filter(c => c.archived)
  else if (activeFilter.value !== 'all') list = list.filter(c => c.type === activeFilter.value && !c.archived)
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(c => c.title.toLowerCase().includes(q))
  }
  return list
})

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

onMounted(loadChats)
</script>
