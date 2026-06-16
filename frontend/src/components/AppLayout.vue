<template>
  <div class="app-shell">
    <AppHeader :user="store.user" :theme="store.theme" @toggle-theme="toggleTheme" @logout="doLogout" />
    <div class="nav-tabs">
      <div v-for="tab in tabs" :key="tab.id"
           class="nav-tab" :class="{ active: store.activeTab === tab.id }"
           @click="store.activeTab = tab.id">{{ tab.label }}</div>
    </div>
    <div class="tab-content">
      <DashboardTab v-if="store.activeTab === 'dashboard'" />
      <ChatsTab v-else-if="store.activeTab === 'chats'" />
      <SubscribeTab v-else-if="store.activeTab === 'subscribe'" />
      <BlockedTab v-else-if="store.activeTab === 'blocked'" />
      <BackupTab v-else-if="store.activeTab === 'backup'" />
      <ExportTab v-else-if="store.activeTab === 'export'" />
      <SettingsTab v-else-if="store.activeTab === 'settings'" />
    </div>
  </div>
</template>

<script setup>
import { store } from '../store.js'
import { api } from '../api.js'
import AppHeader from './AppHeader.vue'
import DashboardTab from './DashboardTab.vue'
import ChatsTab from './ChatsTab.vue'
import SubscribeTab from './SubscribeTab.vue'
import BlockedTab from './BlockedTab.vue'
import BackupTab from './BackupTab.vue'
import SettingsTab from './SettingsTab.vue'
import ExportTab from './ExportTab.vue'

const tabs = [
  { id: 'dashboard', label: 'Главная' },
  { id: 'chats', label: 'Чаты' },
  { id: 'subscribe', label: 'Подписки' },
  { id: 'blocked', label: 'Заблокированные' },
  { id: 'backup', label: 'Резервная копия' },
  { id: 'export', label: 'История чатов' },
  { id: 'settings', label: 'Настройки' },
]

function toggleTheme() {
  store.theme = store.theme === 'dark' ? 'light' : 'dark'
  document.body.dataset.theme = store.theme
  localStorage.setItem('theme', store.theme)
}

async function doLogout() {
  if (!confirm('Выйти из аккаунта?')) return
  await api('/api/auth/logout', { method: 'POST' })
  store.user = null
}
</script>
