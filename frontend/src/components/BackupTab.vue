<template>
  <div class="tab-pane active" style="padding:28px 24px;">
    <div class="section-title">Резервная копия чатов</div>
    <div class="settings-card">
      <h3>Статус</h3>
      <div class="status-row"><span class="status-label">Последний запуск</span><span>{{ formatDate(status.last_run) }}</span></div>
      <div class="status-row"><span class="status-label">Следующий запуск</span><span>{{ formatDate(status.next_run) }}</span></div>
      <div class="status-row"><span class="status-label">Последний файл</span><span>{{ status.last_result?.file || '—' }}</span></div>
      <div class="status-row"><span class="status-label">Кол-во чатов</span><span>{{ status.last_result?.count ?? '—' }}</span></div>
      <div style="margin-top:16px;display:flex;gap:10px;">
        <button class="btn btn-primary btn-sm" :disabled="running" @click="backupNow">{{ running ? 'Сохранение…' : 'Создать сейчас' }}</button>
        <button class="btn btn-ghost btn-sm" @click="load">↻ Обновить статус</button>
      </div>
      <div class="alert" :class="ok ? 'alert-success show' : 'alert-error show'" v-if="msg" style="margin-top:12px;">{{ msg }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api, formatDate } from '../api.js'

const status = ref({})
const running = ref(false)
const msg = ref('')
const ok = ref(true)

async function load() { status.value = await api('/api/backup/status') }
async function backupNow() {
  running.value = true; msg.value = ''
  const res = await api('/api/backup/now', { method: 'POST' })
  running.value = false
  ok.value = res.success
  msg.value = res.success ? `✓ Сохранено ${res.count} чатов → ${res.file}` : (res.error || 'Ошибка')
  await load()
}
onMounted(load)
</script>
