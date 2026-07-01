<template>
  <div v-if="isLoginPage" class="login-wrapper">
    <router-view />
  </div>
  <div v-else :class="['app-container', { expanded }]">
    <header class="app-header">
      <div class="header-brand">
        <span class="brand-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 14c0 1.657 2.686 3 6 3s6 -1.343 6 -3s-2.686 -3 -6 -3s-6 1.343 -6 3" />
            <path d="M9 14v4c0 1.656 2.686 3 6 3s6 -1.344 6 -3v-4" />
            <path d="M3 6c0 1.072 1.144 2.062 3 2.598s4.144 .536 6 0c1.856 -.536 3 -1.526 3 -2.598c0 -1.072 -1.144 -2.062 -3 -2.598s-4.144 -.536 -6 0c-1.856 .536 -3 1.526 -3 2.598" />
            <path d="M3 6v10c0 .888 .772 1.45 2 2" />
            <path d="M3 11c0 .888 .772 1.45 2 2" />
          </svg>
        </span>
        <h1>财务结算系统</h1>
      </div>
      <nav>
        <router-link to="/"><span class="nav-icon">⌂</span> 首页</router-link>
        <router-link to="/basic-data"><span class="nav-icon">⊞</span> 基础数据</router-link>
        <router-link to="/import"><span class="nav-icon">⇧</span> 数据导入</router-link>
        <router-link to="/settlement"><span class="nav-icon">∑</span> 结算查询</router-link>
        <router-link to="/arap"><span class="nav-icon">¤</span> 应收应付</router-link>
        <router-link to="/profit"><span class="nav-icon">P</span> 利润表</router-link>
        <router-link to="/flex-import"><span class="nav-icon">📊</span> 弹性导入</router-link>
        <router-link to="/ocr"><span class="nav-icon">📷</span> OCR 识别</router-link>
        <router-link to="/memos"><span class="nav-icon">📋</span> 备忘录</router-link>
      </nav>
      <div class="header-right">
        <button class="btn-header btn-expand" @click="expanded = !expanded" title="展开/收起">
          {{ expanded ? '⊟' : '⊞' }}
        </button>
        <button class="btn-header btn-theme" @click="darkMode = !darkMode" :title="darkMode ? '亮色模式' : '暗色模式'">
          {{ darkMode ? '☀' : '☾' }}
        </button>
        <router-link to="/system" class="btn-header">
          <span class="nav-icon">⚙</span> 设置
        </router-link>
        <button v-if="isLoggedIn" class="btn-header btn-logout" @click="doLogout">
          退出
        </button>
      </div>
    </header>
    <div v-if="readOnly" class="readonly-banner">
      🔒 只读模式 — 当前为局域网访问，仅可查看数据
    </div>
    <main class="app-main">
      <router-view />
    </main>
    <AppToast />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { getToken, clearToken } from './api'
import AppToast from './components/AppToast/AppToast.vue'
import { useToast } from './components/AppToast/useToast'

const route = useRoute()
const router = useRouter()

const isLoginPage = computed(() => route.path === '/login')
const isLoggedIn = ref(!!getToken())
watch(() => route.path, () => { isLoggedIn.value = !!getToken() }, { immediate: true })

// Persist expand state across sessions
const expanded = ref(localStorage.getItem('finance_expanded') === 'true')
watch(expanded, (v) => localStorage.setItem('finance_expanded', v))

// Dark mode toggle
const darkMode = ref(localStorage.getItem('finance_dark') === 'true')
watch(darkMode, (v) => {
  localStorage.setItem('finance_dark', v)
  document.documentElement.classList.toggle('dark', v)
}, { immediate: true })

// Read-only detection for LAN sharing
const readOnly = ref(false)
const toast = useToast()

onMounted(async () => {
  try {
    const r = await fetch('/api/health')
    if (r.headers.get('X-Read-Only') === '1') readOnly.value = true
  } catch { /* ignore */ }

  window.addEventListener('readonly-forbidden', _onReadonlyForbidden)
})

onUnmounted(() => {
  window.removeEventListener('readonly-forbidden', _onReadonlyForbidden)
})

function _onReadonlyForbidden(e) {
  // Debounce: multiple 403s in quick succession only show one toast
  if (window._readonlyToastTimer) return
  window._readonlyToastTimer = setTimeout(() => { window._readonlyToastTimer = null }, 2000)
  toast.warning('🔒 ' + (e.detail || '只读模式：当前为局域网访问，仅可查看数据'))
}

// Global Alt+wheel horizontal scroll for AG Grids
function onGlobalWheel(e) {
  if (!e.altKey) return
  const target = e.target.closest('.ag-body-viewport, .ag-center-cols-viewport')
  if (!target) return
  e.preventDefault()
  target.scrollLeft += e.deltaY
}
onMounted(() => document.addEventListener('wheel', onGlobalWheel, { passive: false }))
onUnmounted(() => document.removeEventListener('wheel', onGlobalWheel))

async function doLogout() {
  try {
    await api.logout()
  } catch { /* ignore */ }
  clearToken()
  router.push('/login')
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background: var(--bg-page, #f0f2f5);
  color: var(--text-primary, #1a1a2e);
}
.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.app-header {
  background: linear-gradient(135deg, var(--bg-header-start, #1a1a2e) 0%, var(--bg-header-end, #16213e) 100%);
  color: var(--text-on-primary, #fff);
  padding: 0 28px;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 32px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  position: sticky;
  top: 0;
  z-index: 100;
}
.header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: var(--color-accent, #64ffda);
}
.brand-icon svg {
  width: 100%;
  height: 100%;
}
.app-header h1 {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.app-header nav {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 100%;
}
.app-header nav a {
  color: var(--text-nav, #a0a0b8);
  text-decoration: none;
  font-size: 13.5px;
  padding: 0 14px;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  border-bottom: 3px solid transparent;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.app-header nav a:hover {
  color: var(--text-nav-hover, #e0e0f0);
  background: rgba(255,255,255,0.05);
  border-bottom-color: rgba(100,255,218,0.4);
}
.app-header nav a.router-link-active {
  color: var(--text-on-primary, #fff);
  border-bottom-color: var(--color-accent, #64ffda);
}
.nav-icon {
  font-size: 15px;
  line-height: 1;
}
.header-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 100%;
}
.btn-header {
  color: var(--text-nav, #a0a0b8);
  text-decoration: none;
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid var(--text-nav, #a0a0b8);
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.btn-header:hover {
  color: var(--text-on-primary, #fff);
  border-color: var(--text-on-primary, #fff);
  background: rgba(255,255,255,0.08);
}
.btn-logout:hover {
  color: #f87171;
  border-color: #f87171;
}
.btn-expand {
  font-size: 15px !important;
  padding: 4px 10px !important;
}
.app-main {
  padding: 28px;
  flex: 1;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  transition: max-width 0.2s;
}
.expanded .app-main {
  max-width: 100%;
}

/* Shared card panel */
.card-panel {
  background: var(--bg-card, #fff);
  border-radius: 10px;
  padding: 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
h2.page-title {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 20px;
  color: var(--text-primary, #1a1a2e);
}
.login-wrapper {
  min-height: 100vh;
}
.readonly-banner {
  background: #fff3cd;
  color: #856404;
  text-align: center;
  font-size: 13px;
  padding: 6px;
  border-bottom: 1px solid #ffc107;
}
</style>
