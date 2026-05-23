<template>
  <div class="tab-pane active" style="padding:28px 24px;">
    <div class="section-title">Подписаться из MD файла</div>

    <div class="settings-card" style="max-width:600px;">
      <h3>Файл со списком каналов</h3>

      <!-- Drop zone -->
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
          <button class="btn btn-primary btn-sm" :disabled="previewing" @click="loadPreview">
            <span v-if="previewing" class="btn-spinner"></span>
            {{ previewing ? 'Загрузка…' : 'Загрузить' }}
          </button>
        </div>
      </div>

      <p class="hint" style="margin-top:8px;">Формат: <code>- [Название](https://t.me/...)</code></p>
      <div class="alert alert-error show" v-if="alertMsg">{{ alertMsg }}</div>
    </div>

    <!-- MODAL -->
    <Transition name="sub-fade">
      <div v-if="modalOpen" class="sub-modal-overlay" @click.self="closeModal">
        <div class="sub-modal" :class="{ 'modal-entered': modalEntered }">

          <!-- Header -->
          <div class="sub-modal-header">
            <div>
              <div class="sub-modal-title">Список каналов</div>
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
                      <input type="checkbox" v-model="selectAll" @change="toggleAll" />
                    </th>
                    <th>Название</th>
                    <th>Ссылка</th>
                    <th style="width:140px;">Статус</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(e, i) in entries" :key="i"
                      :class="{ 'row-done': e.subscribed === true || e.runStatus === 'joined' || e.runStatus === 'already' }">
                    <td><input type="checkbox" v-model="e.checked" :disabled="e.subscribed === true" /></td>
                    <td class="entry-title">{{ e.title }}</td>
                    <td><a :href="e.url" target="_blank" class="chat-link">{{ shortUrl(e.url) }}</a></td>
                    <td class="entry-status">
                      <span v-if="e.subscribed === true"   class="estatus estatus-ok">✓ Уже подписан</span>
                      <span v-else-if="e.runStatus === 'joined'"  class="estatus estatus-ok">✓ Подписан</span>
                      <span v-else-if="e.runStatus === 'already'" class="estatus estatus-muted">Уже был</span>
                      <span v-else-if="e.runStatus === 'error'"   class="estatus estatus-err">{{ e.runError || 'Ошибка' }}</span>
                      <span v-else-if="e.subscribed === null"      class="estatus estatus-muted">приватная</span>
                      <span v-else class="estatus estatus-muted">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Progress bar -->
          <div v-if="running || subDone > 0" class="sub-progress">
            <div class="sub-progress-row">
              <span>{{ progressLabel }}</span>
              <span>{{ subDone }} / {{ subTotal }}</span>
            </div>
            <div class="progress-bar-wrap" style="height:6px;border-radius:3px;">
              <div class="progress-bar" :style="{ width: subTotal ? (subDone / subTotal * 100) + '%' : '0%' }"></div>
            </div>
          </div>

          <!-- Footer -->
          <div class="sub-modal-footer">
            <div class="sub-batch-row">
              <label class="sub-check-label">
                <input type="checkbox" v-model="batchMode" />
                Постепенная подписка
              </label>
              <template v-if="batchMode">
                <div class="sub-batch-field">
                  <span>Групп за раз</span>
                  <input type="number" v-model.number="batchSize" min="1" max="20" />
                </div>
                <div class="sub-batch-field">
                  <span>Пауза (мин)</span>
                  <input type="number" v-model.number="batchDelay" min="1" max="1440" />
                </div>
              </template>
            </div>
            <div style="display:flex;gap:8px;">
              <button class="btn btn-ghost btn-sm" @click="closeModal">Закрыть</button>
              <button class="btn btn-primary btn-sm" :disabled="running" @click="startSubscribe">
                {{ running ? 'Подписка…' : '▶ Подписаться' }}
              </button>
            </div>
          </div>

        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { api } from '../api.js'

const filePath = ref('')
const dragging = ref(false)
const previewing = ref(false)
const entries = ref([])
const selectAll = ref(true)
const batchMode = ref(false)
const batchSize = ref(3)
const batchDelay = ref(30)
const running = ref(false)
const subDone = ref(0)
const subTotal = ref(0)
const alertMsg = ref('')
const modalOpen = ref(false)
const modalEntered = ref(false)
let poller = null

const countLabel = computed(() => {
  const already = entries.value.filter(e => e.subscribed === true).length
  const newCount = entries.value.length - already
  return `Найдено: ${entries.value.length} · Уже подписан: ${already} · Новых: ${newCount}`
})

const progressLabel = computed(() => {
  if (subDone.value >= subTotal.value && subTotal.value > 0) return '✓ Готово'
  if (running.value) return 'Подписка идёт…'
  return ''
})

function shortUrl(url) {
  return url.replace('https://t.me/', '@').replace('https://telegram.me/', '@')
}

function toggleAll() {
  entries.value.forEach(e => { if (e.subscribed !== true) e.checked = selectAll.value })
}

function openModal() {
  modalOpen.value = true
  modalEntered.value = false
  nextTick(() => { setTimeout(() => { modalEntered.value = true }, 10) })
}

function closeModal() {
  if (running.value) return
  modalOpen.value = false
}

async function onDrop(e) {
  dragging.value = false
  const file = e.dataTransfer.files[0]
  if (!file) return
  const text = await file.text()
  filePath.value = file.name
  await previewContent(text)
}

async function loadPreview() {
  if (!filePath.value) { alertMsg.value = 'Укажите путь к файлу'; return }
  previewing.value = true; alertMsg.value = ''
  const res = await api('/api/subscribe/preview', { method: 'POST', body: JSON.stringify({ path: filePath.value }) })
  previewing.value = false
  if (res.error) { alertMsg.value = res.error; return }
  await populateEntries(res.entries || [])
}

async function previewContent(text) {
  previewing.value = true; alertMsg.value = ''
  const res = await api('/api/subscribe/preview-content', { method: 'POST', body: JSON.stringify({ content: text }) })
  previewing.value = false
  if (res.error) { alertMsg.value = res.error; return }
  await populateEntries(res.entries || [])
}

async function populateEntries(raw) {
  if (!raw.length) { alertMsg.value = 'Каналы не найдены в файле'; return }
  entries.value = raw.map(e => ({ ...e, checked: true, subscribed: null, runStatus: '', runError: '' }))
  openModal()
  const chk = await api('/api/subscribe/check', { method: 'POST', body: JSON.stringify({ entries: raw }) })
  if (!chk.error) {
    chk.entries.forEach((e, i) => {
      entries.value[i].subscribed = e.subscribed
      if (e.subscribed === true) entries.value[i].checked = false
    })
  }
}

async function startSubscribe() {
  const selected = entries.value.filter(e => e.checked)
  if (!selected.length) return
  running.value = true; subDone.value = 0; subTotal.value = selected.length
  await api('/api/subscribe/start', {
    method: 'POST',
    body: JSON.stringify({ entries: selected, batch_mode: batchMode.value, batch_size: batchSize.value, batch_delay_minutes: batchDelay.value }),
  })
  if (poller) clearInterval(poller)
  poller = setInterval(pollStatus, 1500)
}

async function pollStatus() {
  const s = await api('/api/subscribe/status')
  subDone.value = s.done || 0
  subTotal.value = s.total || 0
  ;(s.results || []).forEach(r => {
    const e = entries.value.find(e => e.url === r.url)
    if (e) { e.runStatus = r.status; e.runError = r.error }
  })
  if (s.status === 'done') { clearInterval(poller); running.value = false }
}

onMounted(async () => {
  const [cfg, status] = await Promise.all([api('/api/settings'), api('/api/subscribe/status')])
  if (cfg.subscribe_md_path) filePath.value = cfg.subscribe_md_path

  // Restore state if subscription was running before page reload
  const activeStatuses = ['running', 'waiting_batch', 'done']
  if (activeStatuses.includes(status.status) && status.entries?.length) {
    entries.value = status.entries.map(e => {
      const r = (status.results || []).find(r => r.url === e.url)
      return { ...e, checked: !r, subscribed: null, runStatus: r?.status || '', runError: r?.error || '' }
    })
    subDone.value = status.done || 0
    subTotal.value = status.total || 0
    openModal()
    if (status.status === 'running' || status.status === 'waiting_batch') {
      running.value = true
      poller = setInterval(pollStatus, 1500)
    }
  }
})
</script>
