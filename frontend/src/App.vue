<template>
  <div>
    <!-- Boot loader -->
    <div v-if="booting" id="boot-screen">
      <div class="boot-spinner"></div>
      <p>Загрузка…</p>
    </div>

    <!-- PIN overlay -->
    <PinOverlay v-else-if="needPin" @verified="onPinVerified" />

    <!-- Login -->
    <LoginScreen v-else-if="!store.user" @logged-in="onLoggedIn" />

    <!-- Main app -->
    <AppLayout v-else />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { store } from './store.js'
import { api } from './api.js'
import PinOverlay from './components/PinOverlay.vue'
import LoginScreen from './components/LoginScreen.vue'
import AppLayout from './components/AppLayout.vue'

const booting = ref(true)
const needPin = ref(false)

onMounted(async () => {
  // Apply saved theme
  const saved = localStorage.getItem('theme') || 'dark'
  store.theme = saved
  document.body.dataset.theme = saved

  // Check PIN — include tab_token if already verified in this tab
  const token = sessionStorage.getItem('tab_token')
  const pinStatus = await fetch('/api/pin/status', {
    headers: token ? { 'X-Tab-Token': token } : {},
  }).then(r => r.json()).catch(() => ({ enabled: false }))
  if (pinStatus.enabled && !pinStatus.verified) {
    booting.value = false
    needPin.value = true
    return
  }

  await checkAuth()
  booting.value = false
})

async function checkAuth() {
  const res = await api('/api/auth/status')
  if (res.logged_in) store.user = res.user
}

function onPinVerified() {
  needPin.value = false
  checkAuth()
}

function onLoggedIn(user) {
  store.user = user
}
</script>
