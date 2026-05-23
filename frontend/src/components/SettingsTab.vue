<template>
  <div class="tab-pane active" style="padding:28px 24px;">
    <div class="section-title">Настройки</div>

    <!-- Proxy -->
    <div class="settings-card">
      <h3>Прокси / VPN</h3>
      <div class="status-row" style="margin-bottom:12px;">
        <span id="proxy-detected" :style="{color: proxyFound ? 'var(--success)' : 'var(--subtext)'}">
          {{ proxyFound ? '✓ Системный прокси: ' + proxyInfo : 'Системный прокси не обнаружен.' }}
        </span>
      </div>
      <label>Прокси вручную</label>
      <input v-model="cfg.proxy" type="text" placeholder="socks5://127.0.0.1:1080" />
      <p class="hint">SOCKS5, SOCKS4, HTTP. Happp и другие VPN создают системный прокси автоматически.</p>
    </div>

    <!-- Folders -->
    <div class="settings-card">
      <h3>Папки сохранения</h3>
      <label>Папка для бэкапа</label>
      <input v-model="cfg.save_folder" type="text" placeholder="backups" />
      <label>Имя файла бэкапа</label>
      <input v-model="cfg.backup_filename" type="text" placeholder="telegram_chats.md" />
      <label>Папка для экспорта истории</label>
      <input v-model="cfg.export_folder" type="text" placeholder="exports" />
    </div>

    <!-- Schedule -->
    <div class="settings-card">
      <h3>Расписание автоматического бэкапа</h3>
      <label>Режим обновления</label>
      <div class="radio-group">
        <label class="radio-option">
          <input type="radio" v-model="cfg.update_mode" value="interval" /> Каждые N часов
        </label>
        <label class="radio-option">
          <input type="radio" v-model="cfg.update_mode" value="daily" /> Каждый день в заданное время
        </label>
      </div>
      <div v-if="cfg.update_mode !== 'daily'" style="margin-top:14px;">
        <label>Интервал (часов)</label>
        <input v-model.number="cfg.update_interval_hours" type="number" min="1" max="168" placeholder="24" />
      </div>
      <div v-else style="margin-top:14px;">
        <label>Время запуска (UTC)</label>
        <input v-model="cfg.update_daily_time" type="time" />
      </div>
    </div>

    <!-- System -->
    <div class="settings-card">
      <h3>Система</h3>
      <label class="toggle-row" @click="cfg.auto_backup_enabled = !cfg.auto_backup_enabled">
        <span>Авто-бэкап по расписанию</span>
        <div class="toggle" :class="{ on: cfg.auto_backup_enabled }"><div class="toggle-knob"></div></div>
      </label>
      <p class="hint" style="margin-top:4px;margin-bottom:14px;">Можно также управлять из трея.</p>
      <label class="toggle-row" @click="toggleAutostart">
        <span>Запускать вместе с Windows</span>
        <div class="toggle" :class="{ on: autostartEnabled }"><div class="toggle-knob"></div></div>
      </label>
      <p class="hint" style="margin-top:6px;">{{ autostartHint }}</p>

      <!-- PIN section -->
      <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border);">
        <label class="toggle-row" @click="togglePinEnabled">
          <span>Защита PIN-кодом</span>
          <div class="toggle" :class="{ on: pinEnabled }"><div class="toggle-knob"></div></div>
        </label>
        <p class="hint" style="margin-top:4px;margin-bottom:14px;">Запрашивается при каждом открытии браузера.</p>

        <!-- Set PIN form -->
        <div v-if="pinForm === 'set'">
          <div v-if="pinRequireCurrent">
            <label>Текущий PIN</label>
            <input v-model="pinCurrent" type="password" maxlength="8" placeholder="••••" inputmode="numeric" />
          </div>
          <label>Новый PIN (4–8 цифр)</label>
          <input v-model="pinNew" type="password" maxlength="8" placeholder="••••" inputmode="numeric" />
          <label>Повторите PIN</label>
          <input v-model="pinConfirm" type="password" maxlength="8" placeholder="••••" inputmode="numeric" />
          <div style="margin-top:12px;display:flex;gap:8px;">
            <button class="btn btn-primary btn-sm" @click="savePin">{{ pinRequireCurrent ? 'Сменить PIN' : 'Установить PIN' }}</button>
            <button class="btn btn-sm" style="background:var(--card);color:var(--text);" @click="pinForm = null; loadPinStatus()">Отмена</button>
          </div>
          <div class="alert" :class="pinAlertOk ? 'alert-success show' : 'alert-error show'" v-if="pinAlertMsg">{{ pinAlertMsg }}</div>
        </div>

        <!-- Disable form -->
        <div v-if="pinForm === 'disable'">
          <label>Текущий PIN для отключения</label>
          <input v-model="pinCurrent" type="password" maxlength="8" placeholder="••••" inputmode="numeric" />
          <div style="margin-top:12px;display:flex;gap:8px;">
            <button class="btn btn-sm" style="background:var(--danger);color:#fff;" @click="disablePin">Отключить PIN</button>
            <button class="btn btn-sm" style="background:var(--card);color:var(--text);" @click="pinForm = null; loadPinStatus()">Отмена</button>
          </div>
          <div class="alert" :class="pinAlertOk ? 'alert-success show' : 'alert-error show'" v-if="pinAlertMsg">{{ pinAlertMsg }}</div>
        </div>

        <div v-if="pinEnabled && !pinForm" style="margin-top:8px;">
          <button class="btn btn-sm" style="background:var(--card);color:var(--text);" @click="pinForm = 'set'; pinRequireCurrent = true">Сменить PIN</button>
        </div>
      </div>
    </div>

    <button class="btn btn-primary" :disabled="saving" @click="saveSettings">{{ saving ? '…' : 'Сохранить настройки' }}</button>
    <div class="alert" :class="saveOk ? 'alert-success show' : 'alert-error show'" v-if="saveMsg" style="margin-top:12px;max-width:560px;">{{ saveMsg }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api, setTabToken } from '../api.js'

const cfg = ref({ proxy: '', save_folder: 'backups', backup_filename: 'telegram_chats.md', export_folder: 'exports', update_mode: 'interval', update_interval_hours: 24, update_daily_time: '03:00', auto_backup_enabled: true })
const proxyFound = ref(false)
const proxyInfo = ref('')
const autostartEnabled = ref(false)
const autostartHint = ref('')
const saving = ref(false)
const saveMsg = ref('')
const saveOk = ref(true)

const pinEnabled = ref(false)
const pinForm = ref(null)  // null | 'set' | 'disable'
const pinRequireCurrent = ref(false)
const pinCurrent = ref('')
const pinNew = ref('')
const pinConfirm = ref('')
const pinAlertMsg = ref('')
const pinAlertOk = ref(false)

async function loadPinStatus() {
  const res = await api('/api/pin/status')
  pinEnabled.value = res.enabled
  pinForm.value = null
  pinCurrent.value = ''; pinNew.value = ''; pinConfirm.value = ''; pinAlertMsg.value = ''
}

function togglePinEnabled() {
  if (pinEnabled.value) { pinForm.value = 'disable'; pinCurrent.value = '' }
  else { pinForm.value = 'set'; pinRequireCurrent.value = false; pinNew.value = ''; pinConfirm.value = '' }
}

async function savePin() {
  if (!/^\d{4,8}$/.test(pinNew.value)) { pinAlertOk.value = false; pinAlertMsg.value = 'PIN: 4–8 цифр'; return }
  if (pinNew.value !== pinConfirm.value) { pinAlertOk.value = false; pinAlertMsg.value = 'PIN-коды не совпадают'; return }
  const res = await api('/api/pin/set', { method: 'POST', body: JSON.stringify({ current_pin: pinCurrent.value, new_pin: pinNew.value }) })
  pinAlertOk.value = res.success
  pinAlertMsg.value = res.success ? '✓ PIN установлен' : (res.error || 'Ошибка')
  if (res.success) { setTabToken(res.tab_token); setTimeout(loadPinStatus, 1000) }
}

async function disablePin() {
  const res = await api('/api/pin/disable', { method: 'POST', body: JSON.stringify({ current_pin: pinCurrent.value }) })
  pinAlertOk.value = res.success
  pinAlertMsg.value = res.success ? '✓ PIN отключён' : (res.error || 'Ошибка')
  if (res.success) setTimeout(loadPinStatus, 800)
}

async function toggleAutostart() {
  const next = !autostartEnabled.value
  const res = await api('/api/autostart', { method: 'POST', body: JSON.stringify({ enabled: next }) })
  if (res.success) {
    autostartEnabled.value = next
    autostartHint.value = next ? '✓ Приложение запустится автоматически при входе в Windows' : 'Автозапуск выключен'
  }
}

async function saveSettings() {
  saving.value = true; saveMsg.value = ''
  const res = await api('/api/settings', {
    method: 'POST',
    body: JSON.stringify({
      proxy: cfg.value.proxy,
      save_folder: cfg.value.save_folder || 'backups',
      backup_filename: cfg.value.backup_filename || 'telegram_chats.md',
      export_folder: cfg.value.export_folder || 'exports',
      update_mode: cfg.value.update_mode,
      update_interval_hours: cfg.value.update_interval_hours || 24,
      update_daily_time: cfg.value.update_daily_time || '03:00',
      auto_backup_enabled: cfg.value.auto_backup_enabled,
    }),
  })
  saving.value = false
  saveOk.value = res.success
  saveMsg.value = res.success ? 'Настройки сохранены' : (res.error || 'Ошибка')
  setTimeout(() => saveMsg.value = '', 3000)
}

onMounted(async () => {
  const [cfgRes, pd, as] = await Promise.all([api('/api/settings'), api('/api/proxy/detected'), api('/api/autostart')])
  Object.assign(cfg.value, cfgRes)
  proxyFound.value = pd.found; proxyInfo.value = pd.info || ''
  autostartEnabled.value = as.enabled
  autostartHint.value = as.enabled ? '✓ Приложение запустится автоматически при входе в Windows' : 'Автозапуск выключен'
  await loadPinStatus()
})
</script>
