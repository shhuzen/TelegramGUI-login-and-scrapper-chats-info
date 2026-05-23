import { reactive } from 'vue'
export const store = reactive({
  user: null,
  theme: 'dark',
  chats: [],
  activeTab: 'dashboard',
  backupStatus: null,
})
