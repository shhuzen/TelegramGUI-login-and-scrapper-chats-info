<template>
  <div class="tab-pane active" style="padding:28px 24px;">
    <div class="section-title">Подписаться из MD файла</div>

    <!-- File loader -->
    <div class="settings-card" style="max-width:600px;">
      <h3>Файл со списком каналов</h3>
      <div class="drop-zone" :class="{ dragging }"
           @dragover.prevent="dragging = true"
           @dragleave.prevent="dragging = false"
           @drop.prevent="onDrop">
        <div class="drop-icon">📄</div>
        <p v-if="!filePath">Перетащите MD файл сюда</p>
        <p v-else style="color:var(--text);font-weight:500;">{{ filePath }}</p>
        <p style="color:var(--subtext);font-size:12px;margin-bottom:12px;">или введите путь вручную</p>
        <div style="display:flex;gap:8px;">
          <input type="text" v-model="filePath" placeholder="C:\backups\telegram_chats.md" style="flex:1;" />
          <button class="btn btn-primary btn-sm" :disabled="loading" @click="loadPreview">
            <span v-if="loading" class="btn-spinner"></span>
            {{ loading ? 'Загрузка…' : 'Загрузить' }}
          </button>
        </div>
      </div>
      <p class="hint" style="margin-top:8px;">Формат: <code>- [Название](https://t.me/...)</code></p>
      <div class="alert alert-error show" v-if="alertMsg">{{ alertMsg }}</div>
    </div>

    <!-- Schedule card -->
    <div class="settings-card" style="max-width:600px;">
      <h3>Режим подписки</h3>

      <!-- Preset pills -->
      <div class="preset-row">
        <button v-for="p in presets" :key="p.id"
                class="preset-pill" :class="{ active: schedule.preset === p.id }"
                @click="applyPreset(p.id)">
          <span class="preset-icon">{{ p.icon }}</span>
          <span class="preset-name">{{ p.name }}</span>
        </button>
      </div>

      <!-- Custom fields (always visible, editable) -->
      <div class="sched-grid">
        <div class="sched-field">
          <div class="sched-label">Пачка</div>
          <div class="sched-input-row">
            <input type="number" v-model.number="schedule.batchSize" min="0" max="500"
                   @input="schedule.preset = 'custom'" />
            <span class="sched-unit">каналов</span>
          </div>
          <div class="sched-hint">0 = без деления на пачки</div>
        </div>

        <div class="sched-field">
          <div class="sched-label">Пауза между подписками</div>
          <div class="sched-input-row">
            <input type="number" v-model.number="schedule.subDelayMin" min="0" max="60"
                   @input="schedule.preset = 'custom'" style="width:62px;" />
            <span class="sched-unit">мин</span>
            <input type="number" v-model.number="schedule.subDelaySec" min="0" max="59"
                   @input="schedule.preset = 'custom'" style="width:62px;" />
            <span class="sched-unit">сек</span>
          </div>
        </div>

        <div class="sched-field" style="grid-column: span 2;">
          <div class="sched-label">Пауза между пачками <span style="color:var(--accent);font-size:11px;">динамическая</span></div>
          <div class="sched-range-row">
            <span class="sched-unit" style="min-width:24px;">от</span>
            <input type="number" v-model.number="schedule.batchDelayMinHr" min="0" max="24"
                   @input="schedule.preset = 'custom'" style="width:58px;" />
            <span class="sched-unit">ч</span>
            <input type="number" v-model.number="schedule.batchDelayMinMin" min="0" max="59"
                   @input="schedule.preset = 'custom'" style="width:58px;" />
            <span class="sched-unit">мин</span>
            <span class="sched-range-sep">до</span>
            <input type="number" v-model.number="schedule.batchDelayMaxHr" min="0" max="24"
                   @input="schedule.preset = 'custom'" style="width:58px;" />
            <span class="sched-unit">ч</span>
            <input type="number" v-model.number="schedule.batchDelayMaxMin" min="0" max="59"
                   @input="schedule.preset = 'custom'" style="width:58px;" />
            <span class="sched-unit">мин</span>
          </div>
          <div class="sched-hint">Каждая пауза — случайное значение в этом диапазоне</div>
        </div>

        <div class="sched-field">
          <div class="sched-label">Таймаут на попытку</div>
          <div class="sched-input-row">
            <input type="number" v-model.number="schedule.timeoutMin" min="0" max="30"
                   @input="schedule.preset = 'custom'" style="width:62px;" />
            <span class="sched-unit">мин</span>
            <input type="number" v-model.number="schedule.timeoutSec" min="0" max="59"
                   @input="schedule.preset = 'custom'" style="width:62px;" />
            <span class="sched-unit">сек</span>
          </div>
        </div>
      </div>

      <!-- Estimate -->
      <div class="sched-estimate" v-if="estimateText">
        <span class="sched-est-icon">🕐</span> {{ estimateText }}
      </div>
    </div>

    <!-- MODAL -->
    <Transition name="sub-fade">
      <div v-if="modalOpen" class="sub-modal-overlay" @click.self="closeModal">
        <div class="sub-modal" :class="{ 'modal-entered': modalEntered }">

          <!-- Header -->
          <div class="sub-modal-header">
            <div>
              <div class="sub-modal-title">Список каналов</div>
              <div class="sub-modal-meta">
                <span v-if="checking" style="display:inline-flex;align-items:center;gap:6px;">
                  <span class="btn-spinner" style="border-color:rgba(125,153,181,.35);border-top-color:var(--subtext);"></span>
                  Проверяем подписки…
                </span>
                <span v-else>{{ countLabel }}</span>
              </div>
            </div>
            <button class="sub-close-btn" @click="closeModal">✕</button>
          </div>

          <!-- Table -->
          <div class="sub-modal-body">
            <div class="sub-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style="width:36px;">
                      <input type="checkbox" v-model="selectAll" @change="toggleAll" :disabled="checking || running" />
                    </th>
                    <th>Название</th>
                    <th>Ссылка</th>
                    <th style="width:150px;">Статус</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(e, i) in entries" :key="i"
                      :class="{ 'row-done': e.subscribed === true || e.runStatus === 'joined' || e.runStatus === 'already' }">
                    <td><input type="checkbox" v-model="e.checked" :disabled="e.subscribed === true || checking || running" /></td>
                    <td class="entry-title">{{ e.title }}</td>
                    <td><a :href="e.url" target="_blank" class="chat-link">{{ shortUrl(e.url) }}</a></td>
                    <td class="entry-status">
                      <span v-if="checking && e.subscribed === null"  class="estatus estatus-muted">…</span>
                      <span v-else-if="e.subscribed === true"         class="estatus estatus-ok">✓ Уже подписан</span>
                      <span v-else-if="e.runStatus === 'joined'"      class="estatus estatus-ok">✓ Подписан</span>
                      <span v-else-if="e.runStatus === 'already'"     class="estatus estatus-muted">Уже был</span>
                      <span v-else-if="e.runStatus === 'error'"       class="estatus estatus-err">{{ e.runError || 'Ошибка' }}</span>
                      <span v-else-if="e.subscribed === null"         class="estatus estatus-muted">приватная</span>
                      <span v-else                                     class="estatus estatus-muted">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Progress + countdown -->
          <div v-if="running || subDone > 0" class="sub-progress">
            <div class="sub-progress-row">
              <span>{{ statusLabel }}</span>
              <span>{{ subDone }} / {{ subTotal }}</span>
            </div>
            <div class="progress-bar-wrap" style="height:6px;border-radius:3px;">
              <div class="progress-bar" :style="{ width: subTotal ? (subDone / subTotal * 100) + '%' : '0%' }"></div>
            </div>
            <!-- Countdown -->
            <div v-if="waitRemaining > 0" class="sub-countdown">
              <div class="sub-countdown-bar"
                   :style="{ width: waitTotal ? ((waitTotal - waitRemaining) / waitTotal * 100) + '%' : '0%' }"></div>
              <span class="sub-countdown-label">
                {{ waitType === 'batch' ? '⏸ Пауза между пачками' : '⏱ Пауза' }}
                — {{ fmtWait(waitRemaining) }}
                <span v-if="waitType === 'batch' && nextBatchWait > 0" style="opacity:.7;">
                  · следующая ~{{ fmtWait(nextBatchWait) }}
                </span>
              </span>
            </div>
          </div>

          <!-- Footer -->
          <div class="sub-modal-footer">
            <div class="sched-summary" v-if="!running">
              <span class="sched-badge">{{ presetLabel }}</span>
              <span v-if="estimateText" style="font-size:12px;color:var(--subtext);">{{ estimateText }}</span>
            </div>
            <div v-else class="sched-summary">
              <span class="sched-badge running-badge">● Выполняется</span>
            </div>
            <div style="display:flex;gap:8px;">
              <button class="btn btn-ghost btn-sm" @click="closeModal">Закрыть</button>
              <button class="btn btn-primary btn-sm" :disabled="running || checking" @click="startSubscribe">
                {{ running ? 'Идёт подписка…' : '▶ Подписаться' }}
              </button>
            </div>
          </div>

        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { api } from '../api.js'

// ── File / drag state ──────────────────────────────────────────────
const filePath = ref('')
const dragging  = ref(false)
const loading   = ref(false)
const checking  = ref(false)
const alertMsg  = ref('')

// ── Entries / modal ────────────────────────────────────────────────
const entries    = ref([])
const selectAll  = ref(true)
const modalOpen    = ref(false)
const modalEntered = ref(false)

// ── Run state ──────────────────────────────────────────────────────
const running      = ref(false)
const subDone      = ref(0)
const subTotal     = ref(0)
const waitType      = ref('')      // 'sub' | 'batch'
const waitRemaining = ref(0)
const waitTotal     = ref(0)
const nextBatchWait = ref(0)      // секунд следующей паузы (показывается в статусе)
let poller = null

// ── Schedule ───────────────────────────────────────────────────────
const schedule = reactive({
  preset: 'safe',
  batchSize:        30,
  subDelayMin:      3,   subDelaySec:    0,
  batchDelayMinHr:  2,   batchDelayMinMin: 0,
  batchDelayMaxHr:  4,   batchDelayMaxMin: 0,
  timeoutMin:       1,   timeoutSec:     0,
})

const presets = [
  { id: 'fast', icon: '⚡', name: 'Быстро',    cfg: { batchSize:0,  subDelayMin:0, subDelaySec:5, batchDelayMinHr:0, batchDelayMinMin:0, batchDelayMaxHr:0, batchDelayMaxMin:0, timeoutMin:0, timeoutSec:30 } },
  { id: 'safe', icon: '🛡', name: 'Безопасно', cfg: { batchSize:30, subDelayMin:3, subDelaySec:0, batchDelayMinHr:2, batchDelayMinMin:0, batchDelayMaxHr:4, batchDelayMaxMin:0, timeoutMin:1, timeoutSec:0  } },
  { id: 'slow', icon: '🐢', name: 'Медленно',  cfg: { batchSize:10, subDelayMin:10,subDelaySec:0, batchDelayMinHr:3, batchDelayMinMin:0, batchDelayMaxHr:6, batchDelayMaxMin:0, timeoutMin:2, timeoutSec:0  } },
  { id: 'custom', icon: '⚙️', name: 'Своё',    cfg: null },
]

function applyPreset(id) {
  const p = presets.find(x => x.id === id)
  if (!p || !p.cfg) { schedule.preset = 'custom'; return }
  schedule.preset = id
  Object.assign(schedule, p.cfg)
}

const subDelaySecs      = computed(() => schedule.subDelayMin * 60 + schedule.subDelaySec)
const batchDelayMinSecs = computed(() => schedule.batchDelayMinHr * 3600 + schedule.batchDelayMinMin * 60)
const batchDelayMaxSecs = computed(() => schedule.batchDelayMaxHr * 3600 + schedule.batchDelayMaxMin * 60)
const timeoutSecs       = computed(() => Math.max(10, schedule.timeoutMin * 60 + schedule.timeoutSec))

const selectedCount = computed(() => entries.value.filter(e => e.checked).length)

const estimateText = computed(() => {
  const n = selectedCount.value || entries.value.filter(e => e.subscribed !== true).length
  if (!n) return ''
  const bs = schedule.batchSize > 0 ? schedule.batchSize : n
  const batches = Math.ceil(n / bs)
  const avgBatchDelay = (batchDelayMinSecs.value + batchDelayMaxSecs.value) / 2
  const minSec = (n - 1) * subDelaySecs.value + (batches - 1) * batchDelayMinSecs.value
  const maxSec = (n - 1) * subDelaySecs.value + (batches - 1) * batchDelayMaxSecs.value
  if (maxSec < 5) return `~мгновенно для ${n} каналов`
  if (batchDelayMinSecs.value !== batchDelayMaxSecs.value && batches > 1) {
    return `~${fmtDuration(minSec)}–${fmtDuration(maxSec)} для ${n} каналов`
  }
  return `~${fmtDuration(minSec)} для ${n} каналов`
})

const presetLabel = computed(() => {
  const p = presets.find(x => x.id === schedule.preset)
  return p ? `${p.icon} ${p.name}` : '⚙️ Своё'
})

const countLabel = computed(() => {
  const already  = entries.value.filter(e => e.subscribed === true).length
  const newCount = entries.value.length - already
  return `Найдено: ${entries.value.length} · Уже подписан: ${already} · Новых: ${newCount}`
})

const statusLabel = computed(() => {
  if (subDone.value >= subTotal.value && subTotal.value > 0) return '✓ Готово'
  if (waitRemaining.value > 0) return waitType.value === 'batch' ? 'Пауза между пачками' : 'Пауза между подписками'
  return 'Подписка идёт…'
})

// ── Helpers ────────────────────────────────────────────────────────
function shortUrl(url) {
  return url.replace('https://t.me/', '@').replace('https://telegram.me/', '@')
}

function fmtWait(secs) {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = secs % 60
  if (h > 0) return `${h}ч ${String(m).padStart(2,'0')}м ${String(s).padStart(2,'0')}с`
  if (m > 0) return `${m}м ${String(s).padStart(2,'0')}с`
  return `${s}с`
}

function fmtDuration(secs) {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (h > 0 && m > 0) return `${h}ч ${m}м`
  if (h > 0) return `${h}ч`
  if (m > 0) return `${m}м`
  return `${secs}с`
}

function toggleAll() {
  entries.value.forEach(e => { if (e.subscribed !== true) e.checked = selectAll.value })
}

// ── Modal ──────────────────────────────────────────────────────────
function openModal() {
  modalOpen.value = true
  modalEntered.value = false
  nextTick(() => setTimeout(() => { modalEntered.value = true }, 10))
}

function closeModal() {
  if (running.value) {
    if (!confirm('Подписка идёт. Закрыть? Процесс продолжится на сервере.')) return
    if (poller) { clearInterval(poller); poller = null }
    running.value = false
  }
  modalOpen.value = false
}

function onEsc(e) { if (e.key === 'Escape') closeModal() }

// ── File loading ───────────────────────────────────────────────────
async function onDrop(e) {
  dragging.value = false
  const file = e.dataTransfer.files[0]
  if (!file) return
  filePath.value = file.name
  await loadContent(await file.text())
}

async function loadPreview() {
  if (!filePath.value) { alertMsg.value = 'Укажите путь к файлу'; return }
  loading.value = true; alertMsg.value = ''
  const res = await api('/api/subscribe/preview', { method: 'POST', body: JSON.stringify({ path: filePath.value }) })
  if (res.error) { alertMsg.value = res.error; loading.value = false; return }
  await populateEntries(res.entries || [])
  loading.value = false
}

async function loadContent(text) {
  loading.value = true; alertMsg.value = ''
  const res = await api('/api/subscribe/preview-content', { method: 'POST', body: JSON.stringify({ content: text }) })
  if (res.error) { alertMsg.value = res.error; loading.value = false; return }
  await populateEntries(res.entries || [])
  loading.value = false
}

async function populateEntries(raw) {
  if (!raw.length) { alertMsg.value = 'Каналы не найдены в файле'; return }
  subDone.value = 0; subTotal.value = 0
  entries.value = raw.map(e => ({ ...e, checked: true, subscribed: null, runStatus: '', runError: '' }))
  openModal()
  checking.value = true
  const chk = await api('/api/subscribe/check', { method: 'POST', body: JSON.stringify({ entries: raw }) })
  checking.value = false
  if (!chk.error) {
    chk.entries.forEach((e, i) => {
      entries.value[i].subscribed = e.subscribed
      if (e.subscribed === true) entries.value[i].checked = false
    })
  }
}

// ── Subscribe ──────────────────────────────────────────────────────
async function startSubscribe() {
  const selected = entries.value.filter(e => e.checked)
  if (!selected.length) return
  running.value = true; subDone.value = 0; subTotal.value = selected.length
  waitRemaining.value = 0; waitTotal.value = 0; waitType.value = ''

  await api('/api/subscribe/start', {
    method: 'POST',
    body: JSON.stringify({
      entries: selected,
      batch_size:               schedule.batchSize,
      sub_delay_seconds:        subDelaySecs.value,
      batch_delay_min_seconds:  batchDelayMinSecs.value,
      batch_delay_max_seconds:  batchDelayMaxSecs.value,
      timeout_seconds:          timeoutSecs.value,
    }),
  })
  if (poller) clearInterval(poller)
  poller = setInterval(pollStatus, 800)
}

async function pollStatus() {
  const s = await api('/api/subscribe/status')
  subDone.value      = s.done  || 0
  subTotal.value     = s.total || 0
  waitType.value      = s.wait_type      || ''
  waitRemaining.value = s.wait_remaining || 0
  waitTotal.value     = s.wait_total     || 0
  nextBatchWait.value = s.next_batch_wait || 0
  ;(s.results || []).forEach(r => {
    const e = entries.value.find(e => e.url === r.url)
    if (e) { e.runStatus = r.status; e.runError = r.error }
  })
  if (s.status === 'done') { clearInterval(poller); poller = null; running.value = false }
}

// ── Mount ──────────────────────────────────────────────────────────
onMounted(async () => {
  document.addEventListener('keydown', onEsc)
  const [cfg, status] = await Promise.all([api('/api/settings'), api('/api/subscribe/status')])
  if (cfg.subscribe_md_path) filePath.value = cfg.subscribe_md_path

  const active = ['running', 'waiting_sub', 'waiting_batch', 'done']
  if (active.includes(status.status) && status.entries?.length) {
    entries.value = status.entries.map(e => {
      const r = (status.results || []).find(r => r.url === e.url)
      return { ...e, checked: !r, subscribed: null, runStatus: r?.status || '', runError: r?.error || '' }
    })
    subDone.value  = status.done  || 0
    subTotal.value = status.total || 0
    openModal()
    if (status.status !== 'done') {
      running.value       = true
      waitType.value      = status.wait_type      || ''
      waitRemaining.value = status.wait_remaining || 0
      waitTotal.value     = status.wait_total     || 0
      poller = setInterval(pollStatus, 800)
    }
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', onEsc)
  if (poller) clearInterval(poller)
})
</script>
