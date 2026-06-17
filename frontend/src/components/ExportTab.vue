<template>
  <div class="tab-pane active" style="padding:28px 24px;">
    <div class="section-title">Экспорт истории чата</div>

    <div style="display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start;">

      <!-- ── Chat selection card ─────────────────────────────── -->
      <div class="settings-card" style="flex:1;min-width:300px;max-width:500px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
          <h3 style="margin:0;">Выбор чатов</h3>
          <button class="btn btn-ghost btn-sm" :disabled="loadingChats" @click="loadChats">
            <span v-if="loadingChats" class="btn-spinner"></span>
            ↻ Обновить
          </button>
        </div>

        <!-- search -->
        <div class="search-wrap" style="margin-bottom:10px;">
          <span class="search-icon">🔍</span>
          <input class="search-input" v-model="chatSearch"
                 placeholder="Поиск чатов…" style="padding-left:32px;" />
          <span v-if="chatSearch" class="search-clear" @click="chatSearch=''">✕</span>
        </div>

        <!-- filter tabs -->
        <div style="display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap;">
          <button v-for="f in chatFilters" :key="f.id"
                  class="filter-btn" :class="{active: chatFilter===f.id}"
                  @click="chatFilter=f.id">{{ f.label }}</button>
        </div>

        <!-- select all / none -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:13px;color:var(--subtext);">
          <span>{{ selectedChats.length }} выбрано</span>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-ghost btn-sm" style="font-size:11px;padding:2px 8px;" @click="selectAll">Все</button>
            <button class="btn btn-ghost btn-sm" style="font-size:11px;padding:2px 8px;" @click="selectNone">Снять</button>
          </div>
        </div>

        <!-- chat list -->
        <div class="chat-pick-list">
          <div v-if="loadingChats" class="loading-row" style="justify-content:center;padding:24px;">
            <div class="spinner"></div>
          </div>
          <div v-else-if="!filteredChats.length"
               style="text-align:center;padding:24px;color:var(--subtext);font-size:13px;">
            {{ chatSearch ? 'Ничего не найдено' : 'Нет чатов' }}
          </div>
          <label v-else v-for="c in filteredChats" :key="c.id"
                 class="chat-pick-row" :class="{selected: c.checked}">
            <input type="checkbox" v-model="c.checked" style="flex-shrink:0;margin-top:2px;" />
            <span class="chat-pick-icon">{{ c.type === 'channel' ? '📢' : '👥' }}</span>
            <span class="chat-pick-info">
              <span class="chat-pick-title">{{ c.title }}</span>
              <span class="chat-pick-meta">
                <span v-if="c.username" style="color:var(--accent);font-size:11px;">@{{ c.username }}</span>
                <span class="badge" style="font-size:10px;padding:1px 5px;"
                      :class="c.type==='channel' ? 'badge-channel' : 'badge-group'">
                  {{ c.type === 'channel' ? 'Канал' : 'Группа' }}
                </span>
                <span v-if="c.members_count" style="color:var(--subtext);font-size:11px;">
                  {{ c.members_count.toLocaleString() }} уч.
                </span>
              </span>
            </span>
          </label>
        </div>
      </div>

      <!-- ── Settings + results ──────────────────────────────── -->
      <div style="flex:1;min-width:260px;max-width:420px;display:flex;flex-direction:column;gap:16px;">

        <!-- settings card -->
        <div class="settings-card">
          <h3>Настройки экспорта</h3>

          <!-- MD folder -->
          <label>Папка для MD файлов</label>
          <div class="folder-row">
            <input v-model="settings.mdFolder" type="text" placeholder="exports" />
            <button class="btn btn-ghost btn-sm folder-pick-btn" @click="pickFolder('md')" title="Выбрать папку">
              📁
            </button>
          </div>
          <p class="hint">Если включены только MD — файл сохраняется прямо сюда. Если включён JSON/HTML — создаётся подпапка с названием чата.</p>

          <!-- Media folder -->
          <label style="margin-top:10px;">Папка для медиафайлов</label>
          <div class="folder-row">
            <input v-model="settings.mediaFolder" type="text" placeholder="exports" />
            <button class="btn btn-ghost btn-sm folder-pick-btn" @click="pickFolder('media')" title="Выбрать папку">
              📁
            </button>
          </div>
          <p class="hint">Сюда скачиваются фото, видео, документы и т.д.</p>

          <!-- Formats -->
          <label style="margin-top:12px;">Форматы экспорта</label>
          <div class="format-checks">
            <label class="format-check">
              <input type="checkbox" checked disabled />
              <span>Markdown (.md)</span>
              <span style="color:var(--subtext);font-size:11px;margin-left:4px;">всегда</span>
            </label>
            <label class="format-check">
              <input type="checkbox" v-model="settings.exportJson" />
              <span>JSON (.json)</span>
            </label>
            <label class="format-check">
              <input type="checkbox" v-model="settings.exportHtml" />
              <span>HTML (.html)</span>
            </label>
          </div>

          <!-- Range -->
          <label style="margin-top:12px;">Диапазон сообщений</label>
          <div class="range-options">
            <label class="range-option">
              <input type="radio" v-model="settings.rangeType" value="all" /> Весь чат
            </label>
            <label class="range-option">
              <input type="radio" v-model="settings.rangeType" value="date_range" /> За период
            </label>
            <div v-if="settings.rangeType==='date_range'" class="range-date-row">
              <input type="date" v-model="settings.dateFrom" style="flex:1;" />
              <span style="color:var(--subtext);padding:0 4px;">—</span>
              <input type="date" v-model="settings.dateTo" style="flex:1;" />
            </div>
            <label class="range-option">
              <input type="radio" v-model="settings.rangeType" value="last_n" />
              Последние&nbsp;
              <input type="number" v-model.number="settings.lastN" min="1"
                     style="width:80px;display:inline-block;margin:0 4px;"
                     :disabled="settings.rangeType!=='last_n'" />
              &nbsp;сообщений
            </label>
          </div>

          <div class="alert alert-error show" v-if="exportError" style="margin-top:12px;">{{ exportError }}</div>

          <button class="btn btn-primary" style="width:100%;margin-top:16px;"
                  :disabled="!selectedChats.length || running" @click="startExport">
            <span v-if="running" class="btn-spinner"></span>
            {{ running
               ? `Экспорт… (${exportStatus.chats_done}/${exportStatus.chats_total})`
               : `▶ Экспортировать (${selectedChats.length})` }}
          </button>

          <button v-if="running" class="btn btn-ghost" style="width:100%;margin-top:8px;"
                  @click="showProgress=true">
            Показать прогресс
          </button>
        </div>

        <!-- live results card -->
        <div v-if="exportStatus.results?.length" class="settings-card">
          <h3>Результаты</h3>
          <div v-for="r in exportStatus.results" :key="r.id" class="export-result-row"
               :class="r.status">
            <div style="display:flex;align-items:center;gap:8px;">
              <span v-if="r.status==='done'" style="color:var(--success);font-size:16px;">✓</span>
              <span v-else-if="r.status==='error'" style="color:var(--danger);font-size:16px;">✗</span>
              <span v-else class="btn-spinner" style="width:14px;height:14px;"></span>
              <span style="font-weight:500;">{{ r.title }}</span>
            </div>
            <div v-if="r.status==='done'" style="font-size:12px;color:var(--subtext);margin-top:4px;margin-left:24px;">
              {{ r.messages.toLocaleString() }} сообщений · {{ r.media_files }} медиафайлов
            </div>
            <div v-if="r.status==='error'" style="font-size:12px;color:var(--danger);margin-top:4px;margin-left:24px;">
              {{ r.error }}
            </div>
            <div v-if="r.status==='done'" style="margin-top:6px;margin-left:24px;display:flex;gap:6px;">
              <button class="btn btn-ghost btn-sm" style="font-size:11px;" @click="openFolder(r.folder)">
                📁 MD папка
              </button>
              <button v-if="r.media_folder && r.media_folder !== r.folder"
                      class="btn btn-ghost btn-sm" style="font-size:11px;" @click="openFolder(r.media_folder)">
                🖼 Медиа папка
              </button>
            </div>
          </div>
        </div>

        <!-- export history card -->
        <div v-if="exportHistory.length" class="settings-card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <h3 style="margin:0;">История выгрузок</h3>
            <button class="btn btn-ghost btn-sm" style="font-size:11px;color:var(--danger);"
                    @click="clearHistory">Очистить</button>
          </div>
          <div v-for="entry in exportHistory" :key="entry.id" class="history-entry">
            <div class="history-entry-header">
              <span class="history-date">{{ entry.timestamp }}</span>
              <div style="display:flex;gap:4px;">
                <button class="btn btn-ghost btn-sm" style="font-size:11px;"
                        @click="openFolder(entry.mdFolder)" title="Открыть папку MD">📁</button>
                <button class="btn btn-ghost btn-sm" style="font-size:11px;color:var(--accent);"
                        :disabled="running" @click="rerunExport(entry)" title="Повторить экспорт">↺</button>
              </div>
            </div>
            <div class="history-chats">
              <span v-for="(t,i) in entry.chatTitles" :key="i" class="history-chat-badge">{{ t }}</span>
            </div>
            <div style="font-size:11px;color:var(--subtext);margin-top:4px;">
              <span v-if="entry.formats.length">{{ entry.formats.join(' + ') }}</span>
              · {{ entry.mdFolder }}
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- ── Progress modal ──────────────────────────────────────── -->
    <Transition name="sub-fade">
      <div v-if="showProgress" class="sub-modal-overlay" @click.self="showProgress=false">
        <div class="sub-modal" :class="{'modal-entered': modalEntered}" style="max-width:560px;">

          <div class="sub-modal-header">
            <div>
              <div class="sub-modal-title">Экспорт истории</div>
              <div class="sub-modal-meta">
                Чатов: {{ exportStatus.chats_done }} / {{ exportStatus.chats_total }}
              </div>
            </div>
            <button class="sub-close-btn" @click="showProgress=false">✕</button>
          </div>

          <div class="sub-modal-body" style="padding:20px;">

            <!-- current chat progress -->
            <div v-if="running && exportStatus.current_chat_title">
              <div style="font-weight:600;font-size:15px;margin-bottom:10px;">
                {{ exportStatus.current_chat_title }}
              </div>
              <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--subtext);margin-bottom:4px;">
                <span>Сообщений обработано</span>
                <span>{{ exportStatus.current_msg.toLocaleString() }} / {{ exportStatus.current_total.toLocaleString() }}</span>
              </div>
              <div class="progress-bar-wrap" style="height:6px;margin-bottom:8px;">
                <div class="progress-bar"
                     :style="{width: exportStatus.current_total
                       ? (exportStatus.current_msg / exportStatus.current_total * 100) + '%'
                       : '0%'}"></div>
              </div>
              <div style="font-size:12px;color:var(--subtext);">
                Медиафайлов скачано: {{ exportStatus.current_media }}
              </div>
            </div>

            <!-- overall progress -->
            <div style="margin-top:16px;">
              <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--subtext);margin-bottom:4px;">
                <span>Общий прогресс</span>
                <span>{{ exportStatus.chats_done }} / {{ exportStatus.chats_total }} чатов</span>
              </div>
              <div class="progress-bar-wrap" style="height:8px;">
                <div class="progress-bar"
                     :style="{width: exportStatus.chats_total
                       ? (exportStatus.chats_done / exportStatus.chats_total * 100) + '%'
                       : '0%'}"></div>
              </div>
            </div>

            <!-- chat-by-chat status -->
            <div v-if="exportStatus.results?.length" style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px;">
              <div v-for="r in exportStatus.results" :key="r.id"
                   style="display:flex;align-items:center;gap:8px;padding:5px 0;font-size:13px;">
                <span v-if="r.status==='done'"    style="color:var(--success);">✓</span>
                <span v-else-if="r.status==='error'" style="color:var(--danger);">✗</span>
                <span v-else class="btn-spinner" style="width:12px;height:12px;margin:0;flex-shrink:0;"></span>
                <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ r.title }}</span>
                <span v-if="r.status==='done'" style="color:var(--subtext);font-size:11px;white-space:nowrap;">
                  {{ r.messages.toLocaleString() }} / {{ r.media_files }} медиа
                </span>
                <button v-if="r.status==='done'" class="btn btn-ghost btn-sm"
                        style="font-size:10px;padding:2px 6px;" @click="openFolder(r.folder)">
                  📁
                </button>
              </div>
            </div>
          </div>

          <div class="sub-modal-footer">
            <div class="sched-summary">
              <span v-if="running" class="sched-badge running-badge">● Экспортируется</span>
              <span v-else class="sched-badge">✓ Завершено</span>
            </div>
            <button class="btn btn-ghost btn-sm" @click="showProgress=false">
              {{ running ? 'Свернуть' : 'Закрыть' }}
            </button>
          </div>

        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { api } from '../api.js'

// ── Chat list ───────────────────────────────────────────────────────
const allChats    = ref([])
const loadingChats = ref(false)
const chatSearch  = ref('')
const chatFilter  = ref('all')

const chatFilters = [
  { id: 'all',      label: 'Все'    },
  { id: 'channel',  label: 'Каналы' },
  { id: 'group',    label: 'Группы' },
  { id: 'archived', label: 'Архив'  },
]

const filteredChats = computed(() => {
  let list = allChats.value
  if (chatFilter.value === 'archived') list = list.filter(c => c.archived)
  else if (chatFilter.value !== 'all') list = list.filter(c => c.type === chatFilter.value && !c.archived)
  const q = chatSearch.value.trim().toLowerCase()
  if (q) list = list.filter(c =>
    c.title.toLowerCase().includes(q) ||
    (c.username && c.username.toLowerCase().includes(q))
  )
  return list
})

const selectedChats = computed(() => allChats.value.filter(c => c.checked))

function selectAll()  { filteredChats.value.forEach(c => c.checked = true) }
function selectNone() { filteredChats.value.forEach(c => c.checked = false) }

async function loadChats() {
  loadingChats.value = true
  const res = await api('/api/chats')
  loadingChats.value = false
  if (!res.error) {
    allChats.value = (res.chats || []).map(c => ({ ...c, checked: false }))
  }
}

// ── Settings ────────────────────────────────────────────────────────
const settings = reactive({
  mdFolder:    'exports',
  mediaFolder: 'exports',
  exportJson:  false,
  exportHtml:  false,
  rangeType: 'all',
  dateFrom: '',
  dateTo: '',
  lastN: 10000,
})

async function pickFolder(target) {
  const res = await api('/api/utils/pick-folder', { method: 'POST', body: JSON.stringify({}) })
  if (res.folder) {
    if (target === 'md')    settings.mdFolder    = res.folder
    if (target === 'media') settings.mediaFolder = res.folder
    savePaths()
  }
}

function savePaths() {
  localStorage.setItem('export_md_folder',    settings.mdFolder)
  localStorage.setItem('export_media_folder', settings.mediaFolder)
}

// ── Export state ────────────────────────────────────────────────────
const running       = ref(false)
const exportError   = ref('')
const showProgress  = ref(false)
const modalEntered  = ref(false)
const exportStatus  = ref({
  status: 'idle',
  current_chat_title: '',
  current_chat_id: 0,
  current_msg: 0,
  current_total: 0,
  current_media: 0,
  chats_done: 0,
  chats_total: 0,
  results: [],
  error: '',
})
let poller = null

// ── Export history ──────────────────────────────────────────────────
const HISTORY_KEY = 'export_history_v2'
const exportHistory = ref([])

function loadHistory() {
  try {
    exportHistory.value = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]')
  } catch { exportHistory.value = [] }
}

function saveHistory() {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(exportHistory.value.slice(0, 50)))
}

function pushHistory(chats, status) {
  const formats = ['Markdown']
  if (settings.exportJson) formats.push('JSON')
  if (settings.exportHtml) formats.push('HTML')
  exportHistory.value.unshift({
    id: Date.now(),
    timestamp: new Date().toLocaleString('ru'),
    chatTitles: chats.map(c => c.title),
    chatConfigs: chats,
    mdFolder:    settings.mdFolder,
    mediaFolder: settings.mediaFolder,
    exportJson:  settings.exportJson,
    exportHtml:  settings.exportHtml,
    rangeType:   settings.rangeType,
    dateFrom:    settings.dateFrom,
    dateTo:      settings.dateTo,
    lastN:       settings.lastN,
    formats,
    results: status.results || [],
  })
  saveHistory()
}

function clearHistory() {
  if (!confirm('Очистить историю выгрузок?')) return
  exportHistory.value = []
  saveHistory()
}

async function rerunExport(entry) {
  if (running.value) return
  // restore settings from history
  settings.mdFolder    = entry.mdFolder
  settings.mediaFolder = entry.mediaFolder
  settings.exportJson  = entry.exportJson
  settings.exportHtml  = entry.exportHtml
  settings.rangeType   = entry.rangeType
  settings.dateFrom    = entry.dateFrom
  settings.dateTo      = entry.dateTo
  settings.lastN       = entry.lastN

  // re-check the same chats in allChats (by id)
  const ids = new Set(entry.chatConfigs.map(c => c.id))
  allChats.value.forEach(c => { c.checked = ids.has(c.id) })

  await doStartExport(entry.chatConfigs)
}

// ── Actions ─────────────────────────────────────────────────────────
async function startExport() {
  const sel = selectedChats.value
  if (!sel.length) return
  exportError.value = ''

  const chats = sel.map(c => ({
    id:         c.id,
    title:      c.title,
    username:   c.username || null,
    range_type: settings.rangeType,
    date_from:  settings.dateFrom || '',
    date_to:    settings.dateTo   || '',
    last_n:     settings.lastN,
  }))

  await doStartExport(chats)
}

async function doStartExport(chats) {
  savePaths()
  const res = await api('/api/export/full/start', {
    method: 'POST',
    body: JSON.stringify({
      chats,
      md_folder:    settings.mdFolder,
      media_folder: settings.mediaFolder,
      export_json:  settings.exportJson,
      export_html:  settings.exportHtml,
    }),
  })

  if (res.error) { exportError.value = res.error; return }

  running.value = true
  openProgressModal()
  startPoller(chats)
}

function openProgressModal() {
  showProgress.value = true
  modalEntered.value = false
  nextTick(() => setTimeout(() => { modalEntered.value = true }, 10))
}

function startPoller(chats) {
  if (poller) clearInterval(poller)
  poller = setInterval(async () => {
    const s = await api('/api/export/full/status')
    exportStatus.value = s
    if (s.status === 'done' || s.status === 'error') {
      clearInterval(poller); poller = null
      running.value = false
      if (s.status === 'done' && chats) pushHistory(chats, s)
    }
  }, 1000)
}

async function openFolder(folder) {
  await api('/api/export/full/open', { method: 'POST', body: JSON.stringify({ folder }) })
}

function onEsc(e) { if (e.key === 'Escape') showProgress.value = false }

// ── Mount ───────────────────────────────────────────────────────────
onMounted(async () => {
  document.addEventListener('keydown', onEsc)
  loadHistory()

  // restore folder paths from localStorage first
  const savedMd    = localStorage.getItem('export_md_folder')
  const savedMedia = localStorage.getItem('export_media_folder')

  const [cfg, status] = await Promise.all([api('/api/settings'), api('/api/export/full/status')])

  // config takes priority over localStorage for paths
  if (cfg.full_export_md_folder)    settings.mdFolder    = cfg.full_export_md_folder
  else if (savedMd)                  settings.mdFolder    = savedMd
  if (cfg.full_export_media_folder) settings.mediaFolder = cfg.full_export_media_folder
  else if (savedMedia)               settings.mediaFolder = savedMedia

  exportStatus.value = status

  if (status.status === 'running') {
    running.value = true
    openProgressModal()
    startPoller(null)
  }

  await loadChats()
})

onUnmounted(() => {
  document.removeEventListener('keydown', onEsc)
  if (poller) clearInterval(poller)
})
</script>

<style scoped>
.chat-pick-list {
  max-height: 380px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.chat-pick-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background .15s;
  border-bottom: 1px solid var(--border);
}
.chat-pick-row:last-child { border-bottom: none; }
.chat-pick-row:hover { background: var(--hover); }
.chat-pick-row.selected { background: rgba(82,136,193,.08); }
.chat-pick-icon { font-size: 18px; flex-shrink: 0; }
.chat-pick-info { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.chat-pick-title { font-weight: 500; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.chat-pick-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }

.folder-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
.folder-row input { flex: 1; }
.folder-pick-btn { flex-shrink: 0; padding: 6px 10px; font-size: 16px; }

.format-checks {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}
.format-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  cursor: pointer;
}
.format-check input[disabled] { cursor: default; opacity: .5; }

.range-options { display: flex; flex-direction: column; gap: 8px; margin-top: 6px; }
.range-option { display: flex; align-items: center; gap: 6px; font-size: 14px; cursor: pointer; }
.range-date-row { display: flex; align-items: center; gap: 6px; margin-left: 20px; }

.export-result-row {
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.export-result-row:last-child { border-bottom: none; }

/* History */
.history-entry {
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.history-entry:last-child { border-bottom: none; }
.history-entry-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 5px;
}
.history-date { font-size: 12px; color: var(--subtext); }
.history-chats { display: flex; flex-wrap: wrap; gap: 4px; }
.history-chat-badge {
  font-size: 11px;
  background: var(--hover);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 6px;
  color: var(--text);
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
