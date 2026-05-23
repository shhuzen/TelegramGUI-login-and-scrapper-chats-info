<template>
  <div id="pin-overlay" class="visible">
    <div class="pin-card">
      <h2>🔒 Telegram Manager</h2>
      <p class="subtitle">Введите PIN-код для доступа</p>
      <div class="pin-dots">
        <div v-for="i in 8" :key="i" class="pin-dot"
             :class="{ filled: !errorMode && pinBuffer.length >= i, error: errorMode && i <= 4 }"></div>
      </div>
      <div class="pin-grid">
        <button class="pin-btn" v-for="n in [1,2,3,4,5,6,7,8,9]" :key="n" @click="pinKey(String(n))">{{ n }}</button>
        <button class="pin-btn" @click="pinKey('')">⌫</button>
        <button class="pin-btn" @click="pinKey('0')">0</button>
        <button class="pin-btn" @click="pinSubmit()">✓</button>
      </div>
      <div class="pin-error">{{ errorMsg }}</div>
      <div v-if="lockoutMsg" class="pin-lockout">{{ lockoutMsg }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
const emit = defineEmits(['verified'])

const pinBuffer = ref('')
const errorMode = ref(false)
const errorMsg = ref('')
const lockoutMsg = ref('')
let lockoutTimer = null

function pinKey(k) {
  if (lockoutMsg.value) return
  if (k === '') pinBuffer.value = pinBuffer.value.slice(0, -1)
  else if (pinBuffer.value.length < 8) {
    pinBuffer.value += k
  }
}

async function pinSubmit() {
  if (!pinBuffer.value) return
  const pin = pinBuffer.value
  pinBuffer.value = ''
  errorMode.value = false

  const res = await fetch('/api/pin/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin }),
  }).then(r => r.json()).catch(() => ({ success: false, error: 'Ошибка сети' }))

  if (res.success) {
    emit('verified')
  } else {
    errorMode.value = true
    if (res.error && res.error.includes('сек')) {
      startLockout(res.error)
    } else {
      errorMsg.value = res.error || 'Неверный PIN'
      setTimeout(() => { errorMode.value = false; errorMsg.value = '' }, 1200)
    }
  }
}

function startLockout(msg) {
  lockoutMsg.value = msg
  const m = msg.match(/(\d+)\s*сек/)
  let secs = m ? parseInt(m[1]) : 60
  lockoutTimer = setInterval(() => {
    secs--
    if (secs <= 0) { clearInterval(lockoutTimer); lockoutMsg.value = ''; errorMode.value = false }
    else lockoutMsg.value = `Подождите ${secs} сек. перед следующей попыткой`
  }, 1000)
}

function onKey(e) {
  if (e.key >= '0' && e.key <= '9') pinKey(e.key)
  else if (e.key === 'Backspace') pinKey('')
  else if (e.key === 'Enter') pinSubmit()
}

onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => { document.removeEventListener('keydown', onKey); clearInterval(lockoutTimer) })
</script>
