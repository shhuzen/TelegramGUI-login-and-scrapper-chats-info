<template>
  <div class="tab-pane active" style="padding:28px 24px;">
    <div class="section-title">Заблокированные чаты</div>

    <!-- Scan card -->
    <div class="settings-card" style="max-width:600px;">
      <h3>Сканирование диалогов</h3>
      <p style="color:var(--subtext);font-size:14px;margin-bottom:16px;">
        Найдёт чаты, из которых вас кикнули, и каналы, заблокированные Telegram/РКН.
      </p>
      <button class="btn btn-primary" :disabled="scanning" @click="doScan">
        <span v-if="scanning" class="btn-spinner"></span>
        {{ scanning ? 'Сканирование…' : 'Сканировать' }}
      </button>
      <div v-if="scanned" style="margin-top:12px;display:flex;gap:16px;flex-wrap:wrap;">
        <span class="sched-badge" style="background:rgba(220,53,69,.15);color:#dc3545;">
          Кикнули: {{ forbidden.length }}
        </span>
        <span class="sched-badge" style="background:rgba(255,152,0,.15);color:#e65100;">
          Ограничены TG/РКН: {{ restricted.length }}
        </span>
      </div>
      <div class="alert alert-error show" v-if="scanError">{{ scanError }}</div>
    </div>

    <!-- Schedule card (shown after scan if results found) -->
    <div v-if="scanned && (forbidden.length || restricted.length)" class="settings-card" style="max-width:600px;">
      <h3>Режим отписки</h3>

      <div class="preset-row">
        <button v-for="p in presets" :key="p.id"
                class="preset-pill" :class="{ active: schedule.preset === p.id }"
                @click="applyPreset(p.id)">
          <span class="preset-icon">{{ p.icon }}</span>
          <span class="preset-name">{{ p.name }}</span>
        </button>
      </div>

      <div class="sched-grid">
        <div class="sched-field">
          <div class="sched-label">Пачка</div>
          <div class="sched-input-row">
            <input type="number" v-model.number="schedule.batchSize" min="0" max="500"
                   @input="schedule.preset = 'custom'" />
            <span class="sched-unit">чатов</span>
          </div>
          <div class="sched-hint">0 = без деления на пачки</div>
        </div>

        <div class="sched-field">
          <div class="sched-label">Пауза между отписками</div>
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
      </div>

      <button class="btn btn-primary" style="margin-top:8px;" @click="openModal">
        Выбрать и отписаться
      </button>
    </div>

    <!-- MODAL -->
    <Transition name="sub-fade">
      <div v-if="modalOpen" class="sub-modal-overlay" @click.self="closeModal">
        <div class="sub-modal" :class="{ 'modal-entered': modalEntered }">

          <!-- Header -->
          <div class="sub-modal-header">
            <div>
              <div class="sub-modal-title">Заблокированные чаты</div>
              <div class="sub-modal-meta">{{ countLabel }}</div>
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
                      <input type="checkbox" v-model="selectAll" @change="toggleAll" :disabled="running" />
                    </th>
                    <th>Название</th>
                    <th>Тип</th>
                    <th>Причина</th>
                    <th style="width:130px;">Статус</th>
                  </tr>
                </thead>
                <tbody>
                  <!-- Forbidden section -->
                  <tr v-if="forbidden.length" class="section-header forbidden-header">
                    <td colspan="5">Нет доступа — кикнули / забанили ({{ forbidden.length }})</td>
                  </tr>
                  <tr v-for="(e, i) in forbidden" :key="'f'+i"
                      :class="{ 'row-done': e.runStatus === 'left' }">
                    <td><input type="checkbox" v-model="e.checked" :disabled="running" /></td>
                    <td class="entry-title">{{ e.title }}</td>
                    <td>{{ e.type === 'channel' ? 'Канал' : 'Группа' }}</td>
                    <td style="font-size:12px;color:var(--subtext);">{{ e.reason }}</td>
                    <td class="entry-status"><StatusCell :e="e" /></td>
                  </tr>

                  <!-- Restricted section -->
                  <tr v-if="restricted.length" class="section-header restricted-header">
                    <td colspan="5">Ограничены Telegram/РКН ({{ restricted.length }})</td>
                  </tr>
                  <tr v-for="(e, i) in restricted" :key="'r'+i"
                      :class="{ 'row-done': e.runStatus === 'left' }">
                    <td><input type="checkbox" v-model="e.checked" :disabled="running" /></td>
                    <td class="entry-title">
                      <a v-if="e.url" :href="e.url" target="_blank" class="chat-link">{{ e.title }}</a>
                      <span v-else>{{ e.title }}</span>
                    </td>
                    <td>{{ e.type === 'channel' ? 'Канал' : 'Группа' }}</td>
                    <td style="font-size:12px;color:var(--subtext);">{{ e.reason }}</td>
                    <td class="entry-status"><StatusCell :e="e" /></td>
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
            </div>
            <div v-else class="sched-summary">
              <span class="sched-badge running-badge">● Выполняется</span>
            </div>
            <div style="display:flex;gap:8px;">
              <button class="btn btn-ghost btn-sm" @click="closeModal">Закрыть</button>
              <button class="btn btn-danger btn-sm" :disabled="running" @click="startUnsubscribe">
                {{ running ? 'Идёт отписка…' : 'Отписаться от выбранных' }}
              </button>
            </div>
          </div>

        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, defineComponent, h } from 'vue'
import { api } from '../api.js'

// Inline status cell component to avoid repetition
const StatusCell = defineComponent({
  props: ['e'],
  setup(props) {
    return () => {
      const e = props.e
      if (e.runStatus === 'left')  return h('span', { class: 'estatus estatus-ok' }, '✓ Отписан')
      if (e.runStatus === 'error') return h('span', { class: 'estatus estatus-err' }, e.runError || 'Ошибка')
      return h('span', { class: 'estatus estatus-muted' }, '—')
    }
  }
})

// ── Scan state ──────────────────────────────────────────────────────
const scanning  = ref(false)
const scanned   = ref(false)
const scanError = ref('')
const forbidden  = ref([])
const restricted = ref([])

// ── Modal ──────────────────────────────────────────────────────────
const modalOpen    = ref(false)
const modalEntered = ref(false)
const selectAll    = ref(true)

// ── Run state ──────────────────────────────────────────────────────
const running       = ref(false)
const subDone       = ref(0)
const subTotal      = ref(0)
const waitType      = ref('')
const waitRemaining = ref(0)
const waitTotal     = ref(0)
const nextBatchWait = ref(0)
let poller = null

// ── Schedule ───────────────────────────────────────────────────────
const schedule = reactive({
  preset: 'safe',
  batchSize:        30,
  subDelayMin:      3,   subDelaySec:    0,
  batchDelayMinHr:  1,   batchDelayMinMin: 0,
  batchDelayMaxHr:  2,   batchDelayMaxMin: 0,
})

const presets = [
  { id: 'fast',   icon: '⚡', name: 'Быстро',    cfg: { batchSize:0,  subDelayMin:0, subDelaySec:5, batchDelayMinHr:0, batchDelayMinMin:0, batchDelayMaxHr:0, batchDelayMaxMin:0 } },
  { id: 'safe',   icon: '🛡', name: 'Безопасно', cfg: { batchSize:30, subDelayMin:3, subDelaySec:0, batchDelayMinHr:1, batchDelayMinMin:0, batchDelayMaxHr:2, batchDelayMaxMin:0 } },
  { id: 'slow',   icon: '🐢', name: 'Медленно',  cfg: { batchSize:10, subDelayMin:10,subDelaySec:0, batchDelayMinHr:2, batchDelayMinMin:0, batchDelayMaxHr:4, batchDelayMaxMin:0 } },
  { id: 'custom', icon: '⚙️', name: 'Своё',      cfg: null },
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

const selectedCount = computed(() =>
  [...forbidden.value, ...restricted.value].filter(e => e.checked).length
)

const countLabel = computed(() => {
  const total = forbidden.value.length + restricted.value.length
  return `Всего: ${total} · Выбрано: ${selectedCount.value}`
})

const statusLabel = computed(() => {
  if (subDone.value >= subTotal.value && subTotal.value > 0) return '✓ Готово'
  if (waitRemaining.value > 0) return waitType.value === 'batch' ? 'Пауза между пачками' : 'Пауза'
  return 'Отписка идёт…'
})

const presetLabel = computed(() => {
  const p = presets.find(x => x.id === schedule.preset)
  return p ? `${p.icon} ${p.name}` : '⚙️ Своё'
})

// ── Helpers ────────────────────────────────────────────────────────
function fmtWait(secs) {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = secs % 60
  if (h > 0) return `${h}ч ${String(m).padStart(2,'0')}м ${String(s).padStart(2,'0')}с`
  if (m > 0) return `${m}м ${String(s).padStart(2,'0')}с`
  return `${s}с`
}

function toggleAll() {
  ;[...forbidden.value, ...restricted.value].forEach(e => { e.checked = selectAll.value })
}

// ── Scan ───────────────────────────────────────────────────────────
async function doScan() {
  scanning.value = true
  scanError.value = ''
  scanned.value = false
  const res = await api('/api/blocked/scan', { method: 'POST' })
  scanning.value = false
  if (res.error) { scanError.value = res.error; return }
  forbidden.value  = (res.forbidden  || []).map(e => ({ ...e, checked: true, runStatus: '', runError: '' }))
  restricted.value = (res.restricted || []).map(e => ({ ...e, checked: true, runStatus: '', runError: '' }))
  scanned.value = true
}

// ── Modal ──────────────────────────────────────────────────────────
function openModal() {
  modalOpen.value = true
  modalEntered.value = false
  nextTick(() => setTimeout(() => { modalEntered.value = true }, 10))
}

function closeModal() {
  if (running.value) {
    if (!confirm('Отписка идёт. Закрыть? Процесс продолжится на сервере.')) return
    if (poller) { clearInterval(poller); poller = null }
    running.value = false
  }
  modalOpen.value = false
}

function onEsc(e) { if (e.key === 'Escape') closeModal() }

// ── Unsubscribe ────────────────────────────────────────────────────
async function startUnsubscribe() {
  const selected = [...forbidden.value, ...restricted.value].filter(e => e.checked)
  if (!selected.length) return
  running.value = true; subDone.value = 0; subTotal.value = selected.length
  waitRemaining.value = 0; waitTotal.value = 0; waitType.value = ''

  await api('/api/blocked/unsubscribe/start', {
    method: 'POST',
    body: JSON.stringify({
      entries: selected,
      batch_size:               schedule.batchSize,
      sub_delay_seconds:        subDelaySecs.value,
      batch_delay_min_seconds:  batchDelayMinSecs.value,
      batch_delay_max_seconds:  batchDelayMaxSecs.value,
    }),
  })
  if (poller) clearInterval(poller)
  poller = setInterval(pollStatus, 800)
}

async function pollStatus() {
  const s = await api('/api/blocked/unsubscribe/status')
  subDone.value       = s.done  || 0
  subTotal.value      = s.total || 0
  waitType.value      = s.wait_type      || ''
  waitRemaining.value = s.wait_remaining || 0
  waitTotal.value     = s.wait_total     || 0
  nextBatchWait.value = s.next_batch_wait || 0
  ;(s.results || []).forEach(r => {
    const all = [...forbidden.value, ...restricted.value]
    const e = all.find(e => e.id === r.id)
    if (e) { e.runStatus = r.status; e.runError = r.error }
  })
  if (s.status === 'done') { clearInterval(poller); poller = null; running.value = false }
}

// ── Mount ──────────────────────────────────────────────────────────
onMounted(async () => {
  document.addEventListener('keydown', onEsc)
  const status = await api('/api/blocked/unsubscribe/status')
  const active = ['running', 'waiting_sub', 'waiting_batch', 'done']
  if (active.includes(status.status) && status.entries?.length) {
    const allEntries = status.entries
    forbidden.value  = allEntries.filter(e => e.is_forbidden).map(e => {
      const r = (status.results || []).find(r => r.id === e.id)
      return { ...e, checked: false, runStatus: r?.status || '', runError: r?.error || '' }
    })
    restricted.value = allEntries.filter(e => !e.is_forbidden).map(e => {
      const r = (status.results || []).find(r => r.id === e.id)
      return { ...e, checked: false, runStatus: r?.status || '', runError: r?.error || '' }
    })
    scanned.value  = true
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

<style scoped>
.section-header td {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
}
.forbidden-header td {
  background: rgba(220, 53, 69, .12);
  color: #dc3545;
}
.restricted-header td {
  background: rgba(255, 152, 0, .12);
  color: #e65100;
}
.btn-danger {
  background: #dc3545;
  color: #fff;
  border: none;
}
.btn-danger:hover:not(:disabled) {
  background: #c82333;
}
</style>
