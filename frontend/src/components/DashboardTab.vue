<template>
  <div class="tab-pane active" style="padding:28px 24px;">
    <div class="section-title">Главная</div>

    <div class="dash-grid">
      <!-- Connection -->
      <div class="dash-card">
        <div class="dash-label">Подключение</div>
        <div class="dash-value" style="font-size:16px;display:flex;align-items:center;gap:8px;margin-bottom:12px;">
          <span class="status-dot" :class="data.connected ? 'connected' : 'disconnected'"></span>
          {{ data.connected ? 'Подключён' : 'Нет связи' }}
        </div>
        <button class="btn btn-sm" style="background:var(--surface2, var(--card));color:var(--text);" :disabled="reconnecting" @click="reconnect">
          {{ reconnecting ? '…' : '↺ Переподключить' }}
        </button>
        <div v-if="reconnectMsg" style="font-size:12px;margin-top:6px;" :style="{color: reconnectOk ? 'var(--success)' : 'var(--danger)'}">{{ reconnectMsg }}</div>
      </div>

      <!-- Chats -->
      <div class="dash-card">
        <div class="dash-label">Чатов в бэкапе</div>
        <div class="dash-value">{{ chatsCount }}</div>
        <div class="dash-sub">{{ lastBackupTime }}</div>
      </div>

      <!-- Next backup -->
      <div class="dash-card">
        <div class="dash-label">Следующий бэкап</div>
        <div class="dash-value" style="font-size:15px;">{{ nextRun }}</div>
        <div class="dash-sub">{{ autoEnabled ? 'Авто-бэкап включён' : 'Авто-бэкап выключен' }}</div>
      </div>

      <!-- Subscribe -->
      <div class="dash-card">
        <div class="dash-label">Подписки (последний запуск)</div>
        <div class="dash-value">{{ subDone }}</div>
        <div class="dash-sub">{{ subStatus }}</div>
      </div>
    </div>

    <!-- Quick actions -->
    <div style="display:flex;gap:10px;flex-wrap:wrap;">
      <button class="btn btn-primary btn-sm" :disabled="backingUp" @click="backupNow">
        {{ backingUp ? 'Сохранение…' : '💾 Бэкап сейчас' }}
      </button>
      <button class="btn btn-sm" style="background:var(--card);color:var(--text);" @click="store.activeTab='chats'">
        📋 Чаты
      </button>
      <button class="btn btn-sm" style="background:var(--card);color:var(--text);" @click="store.activeTab='settings'">
        ⚙ Настройки
      </button>
    </div>
    <div v-if="backupMsg" class="alert" :class="backupOk ? 'alert-success show' : 'alert-error show'" style="margin-top:12px;max-width:500px;">{{ backupMsg }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { store } from '../store.js'
import { api, formatDate } from '../api.js'

const data = ref({ connected: false, backup: {}, subscribe: {} })
const reconnecting = ref(false)
const reconnectMsg = ref('')
const reconnectOk = ref(false)
const backingUp = ref(false)
const backupMsg = ref('')
const backupOk = ref(false)

const chatsCount = computed(() => data.value.backup?.last_result?.count ?? '—')
const lastBackupTime = computed(() => {
  const t = data.value.backup?.last_run
  return t ? 'Обновлено: ' + formatDate(t) : 'Бэкап ещё не делался'
})
const nextRun = computed(() => formatDate(data.value.backup?.next_run))
const autoEnabled = computed(() => data.value.backup?.running)
const subDone = computed(() => {
  const s = data.value.subscribe
  if (!s?.total) return '—'
  return `${s.done} / ${s.total}`
})
const subStatus = computed(() => {
  const status = data.value.subscribe?.status
  const map = { idle: 'Ожидание', running: 'Выполняется…', done: 'Завершено', waiting_batch: 'Пауза между пакетами' }
  return map[status] || '—'
})

async function load() {
  const res = await api('/api/dashboard')
  if (!res.error) data.value = res
}

async function reconnect() {
  reconnecting.value = true
  reconnectMsg.value = ''
  const res = await api('/api/auth/reconnect', { method: 'POST' })
  reconnecting.value = false
  reconnectOk.value = res.success
  reconnectMsg.value = res.success ? '✓ Переподключено' : (res.error || 'Ошибка')
  await load()
}

async function backupNow() {
  backingUp.value = true
  backupMsg.value = ''
  const res = await api('/api/backup/now', { method: 'POST' })
  backingUp.value = false
  backupOk.value = res.success
  backupMsg.value = res.success ? `✓ Сохранено ${res.count} чатов → ${res.file}` : (res.error || 'Ошибка')
  await load()
}

onMounted(load)
</script>
