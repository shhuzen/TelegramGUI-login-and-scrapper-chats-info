<template>
  <div id="login-screen" style="display:flex">
    <div class="login-card">
      <h1>✈ Telegram Manager</h1>
      <p class="subtitle">Войдите через номер телефона</p>

      <!-- Step 1 -->
      <div v-if="step === 'credentials'" class="step active">
        <label>API ID <span style="color:var(--subtext);font-size:11px;">(необязательно)</span></label>
        <input v-model="form.apiId" type="text" placeholder="2040" />
        <label>API Hash <span style="color:var(--subtext);font-size:11px;">(необязательно)</span></label>
        <input v-model="form.apiHash" type="text" placeholder="Встроенный" />
        <label>Номер телефона</label>
        <input v-model="form.phone" type="tel" placeholder="+7..." @keydown.enter="sendCode" />
        <p class="hint">API ID и Hash необязательны — используются встроенные credentials.<br>Своё приложение: <a href="https://my.telegram.org" target="_blank">my.telegram.org</a></p>
        <div class="alert alert-error" :class="{show: !!error1}">{{ error1 }}</div>
        <button class="btn btn-primary" style="width:100%;margin-top:20px;" :disabled="loading" @click="sendCode">
          {{ loading ? 'Отправка…' : 'Получить код' }}
        </button>
      </div>

      <!-- Step 2 -->
      <div v-if="step === 'code'" class="step active">
        <p style="color:var(--subtext);font-size:14px;margin-bottom:16px;">Код отправлен на <strong>{{ form.phone }}</strong></p>
        <label>Код из Telegram</label>
        <input v-model="form.code" type="text" placeholder="12345" maxlength="10" autofocus @keydown.enter="verifyCode" />
        <div class="alert alert-error" :class="{show: !!error2}">{{ error2 }}</div>
        <button class="btn btn-primary" style="width:100%;margin-top:20px;" :disabled="loading" @click="verifyCode">
          {{ loading ? 'Проверка…' : 'Подтвердить' }}
        </button>
        <button class="btn btn-ghost" style="width:100%;margin-top:8px;" @click="step='credentials'">← Назад</button>
      </div>

      <!-- Step 3 -->
      <div v-if="step === '2fa'" class="step active">
        <p style="color:var(--subtext);font-size:14px;margin-bottom:16px;">Включена двухфакторная аутентификация</p>
        <label>Пароль 2FA</label>
        <input v-model="form.password" type="password" placeholder="Пароль" autofocus @keydown.enter="verify2fa" />
        <div class="alert alert-error" :class="{show: !!error3}">{{ error3 }}</div>
        <button class="btn btn-primary" style="width:100%;margin-top:20px;" :disabled="loading" @click="verify2fa">
          {{ loading ? 'Проверка…' : 'Войти' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'
const emit = defineEmits(['logged-in'])

const step = ref('credentials')
const loading = ref(false)
const error1 = ref(''); const error2 = ref(''); const error3 = ref('')
const form = ref({ apiId: '', apiHash: '', phone: '', code: '', password: '' })

onMounted(() => {
  try {
    const s = JSON.parse(localStorage.getItem('tg_credentials') || '{}')
    if (s.apiId) form.value.apiId = s.apiId
    if (s.apiHash) form.value.apiHash = s.apiHash
    if (s.phone) form.value.phone = s.phone
  } catch {}
})

function saveCredentials() {
  localStorage.setItem('tg_credentials', JSON.stringify({ apiId: form.value.apiId, apiHash: form.value.apiHash, phone: form.value.phone }))
}

async function sendCode() {
  error1.value = ''
  loading.value = true
  saveCredentials()
  const res = await api('/api/auth/send-code', { method: 'POST', body: JSON.stringify({ phone: form.value.phone, api_id: form.value.apiId, api_hash: form.value.apiHash }) })
  loading.value = false
  if (res.success) step.value = 'code'
  else error1.value = res.error || 'Ошибка'
}

async function verifyCode() {
  error2.value = ''
  loading.value = true
  const res = await api('/api/auth/verify-code', { method: 'POST', body: JSON.stringify({ code: form.value.code }) })
  loading.value = false
  if (res.success) {
    if (res.need_2fa) step.value = '2fa'
    else await finishLogin()
  } else error2.value = res.error || 'Неверный код'
}

async function verify2fa() {
  error3.value = ''
  loading.value = true
  const res = await api('/api/auth/verify-2fa', { method: 'POST', body: JSON.stringify({ password: form.value.password }) })
  loading.value = false
  if (res.success) await finishLogin()
  else error3.value = res.error || 'Неверный пароль'
}

async function finishLogin() {
  const status = await api('/api/auth/status')
  emit('logged-in', status.user)
}
</script>
