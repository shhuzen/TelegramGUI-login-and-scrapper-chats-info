<template>
  <div class="tab-pane active" style="padding:28px 24px;">
    <div class="section-title">Подписаться из MD файла</div>

    <div class="settings-card" style="max-width:660px;">
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
            {{ previewing ? '…' : 'Загрузить' }}
          </button>
        </div>
      </div>

      <p class="hint" style="margin-top:8px;">Формат: строки вида <code>- [Название](https://t.me/...)</code></p>

      <!-- Batch mode -->
      <div style="margin-top:12px;">
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;margin:0;">
          <input type="checkbox" v-model="batchMode" />
          Режим постепенной подписки
        </label>
      </div>
      <div v-if="batchMode" style="display:flex;gap:16px;margin-top:12px;flex-wrap:wrap;">
        <div>
          <label style="font-size:12px;color:var(--subtext);">Групп за раз</label>
          <input type="number" v-model.number="batchSize" min="1" max="20" style="width:70px;margin-top:4px;" />
        </div>
        <div>
          <label style="font-size:12px;color:var(--subtext);">Пауза (мин)</label>
          <input type="number" v-model.number="batchDelay" min="1" max="1440" style="width:80px;margin-top:4px;" />
        </div>
      </div>

      <div class="alert" :class="alertType === 'error' ? 'alert-error show' : 'alert-success show'" v-if="alertMsg">{{ alertMsg }}</div>
    </div>

    <!-- Preview table -->
    <div v-if="entries.length" style="max-width:760px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
        <span style="font-size:14px;color:var(--subtext);">{{ countLabel }}</span>
        <div style="display:flex;gap:8px;align-items:center;">
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--subtext);cursor:pointer;margin:0;">
            <input type="checkbox" v-model="selectAll" @change="toggleAll" /> Выбрать все
          </label>
          <button class="btn btn-primary btn-sm" :disabled="running" @click="startSubscribe">
            {{ running ? 'Идёт подписка…' : '▶ Подписаться' }}
          </button>
        </div>
      </div>

      <div class="chat-table-wrapper">
        <table>
          <thead><tr><th style="width:32px;"></th><th>Название</th><th>Ссылка</th><th>Статус</th></tr></thead>
          <tbody>
            <tr v-for="(e, i) in entries" :key="i" :style="e.subscribed === true ? 'opacity:.55' : ''">
              <td><input type="checkbox" v-model="e.checked" /></td>
              <td>{{ e.title }}</td>
              <td><a :href="e.url" target="_blank" class="chat-link">{{ e.url }}</a></td>
              <td>
                <span v-if="e.subscribed === true" style="color:var(--success);font-weight:600">✓ Уже подписан</span>
                <span v-else-if="e.runStatus === 'joined'" style="color:var(--success)">✓ Подписан</span>
                <span v-else-if="e.runStatus === 'already'" style="color:var(--subtext)">Уже подписан</span>
                <span v-else-if="e.runStatus === 'error'" style="color:var(--danger)">{{ e.runError }}</span>
                <span v-else-if="e.subscribed === null" style="color:var(--subtext);font-size:12px">приватная</span>
                <span v-else style="color:var(--subtext);font-size:12px">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Progress -->
      <div v-if="running || subDone > 0" style="margin-top:16px;">
        <div style="display:flex;justify-content:space-between;font-size:13px;color:var(--subtext);margin-bottom:6px;">
          <span>{{ progressLabel }}</span>
          <span>{{ subDone }} / {{ subTotal }}</span>
        </div>
        <div class="progress-bar-wrap" style="height:8px;">
          <div class="progress-bar" :style="{ width: subTotal ? (subDone / subTotal * 100) + '%' : '0%' }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
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
const alertType = ref('error')
let poller = null

const countLabel = computed(() => {
  const already = entries.value.filter(e => e.subscribed === true).length
  const newCount = entries.value.length - already
  return `Найдено: ${entries.value.length}  •  Уже подписан: ${already}  •  Новых: ${newCount}`
})

const progressLabel = computed(() => {
  if (subDone.value >= subTotal.value && subTotal.value > 0) return 'Готово'
  return 'Подписка…'
})

function toggleAll() {
  entries.value.forEach(e => { if (e.subscribed !== true) e.checked = selectAll.value })
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
  if (!filePath.value) { alertType.value = 'error'; alertMsg.value = 'Укажите путь к файлу'; return }
  previewing.value = true; alertMsg.value = ''
  const res = await api('/api/subscribe/preview', { method: 'POST', body: JSON.stringify({ path: filePath.value }) })
  previewing.value = false
  if (res.error) { alertType.value = 'error'; alertMsg.value = res.error; return }
  await populateEntries(res.entries || [])
}

async function previewContent(text) {
  previewing.value = true; alertMsg.value = ''
  const res = await api('/api/subscribe/preview-content', { method: 'POST', body: JSON.stringify({ content: text }) })
  previewing.value = false
  if (res.error) { alertType.value = 'error'; alertMsg.value = res.error; return }
  await populateEntries(res.entries || [])
}

async function populateEntries(raw) {
  entries.value = raw.map(e => ({ ...e, checked: true, subscribed: null, runStatus: '', runError: '' }))
  // Check subscribed
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
  if (!selected.length) { alertType.value = 'error'; alertMsg.value = 'Выберите хотя бы один канал'; return }
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
  const cfg = await api('/api/settings')
  if (cfg.subscribe_md_path) filePath.value = cfg.subscribe_md_path
})
</script>
