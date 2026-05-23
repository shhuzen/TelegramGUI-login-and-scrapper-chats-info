<template>
  <div class="app-header">
    <span class="logo">✈ Telegram Manager</span>

    <div class="user-info" v-if="user">
      <div class="user-avatar" :style="{ background: avatarColor }">{{ avatarLetter }}</div>
      <div class="user-details">
        <span class="user-name">
          {{ fullName }}
          <span v-if="user.is_premium" class="premium-badge">⭐</span>
        </span>
        <span class="user-sub">{{ user.username ? '@' + user.username : user.phone }}</span>
      </div>
    </div>

    <button class="theme-btn" @click="emit('toggle-theme')" :title="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'">
      {{ theme === 'dark' ? '☀️' : '🌙' }}
    </button>
    <button class="btn btn-ghost btn-sm" @click="emit('logout')">Выйти</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ user: Object, theme: String })
const emit = defineEmits(['toggle-theme', 'logout'])

const fullName = computed(() => [props.user?.first_name, props.user?.last_name].filter(Boolean).join(' ') || 'Пользователь')
const avatarLetter = computed(() => (props.user?.first_name || '?')[0].toUpperCase())
const avatarColor = computed(() => {
  const id = props.user?.id || 0
  return `hsl(${id % 360}, 50%, 45%)`
})
</script>
