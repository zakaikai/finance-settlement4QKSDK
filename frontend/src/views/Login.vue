<template>
  <div class="login-page">
    <div class="login-card">
      <div class="accent-line"></div>
      <span class="brand-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 14c0 1.657 2.686 3 6 3s6 -1.343 6 -3s-2.686 -3 -6 -3s-6 1.343 -6 3" />
          <path d="M9 14v4c0 1.656 2.686 3 6 3s6 -1.344 6 -3v-4" />
          <path d="M3 6c0 1.072 1.144 2.062 3 2.598s4.144 .536 6 0c1.856 -.536 3 -1.526 3 -2.598c0 -1.072 -1.144 -2.062 -3 -2.598s-4.144 -.536 -6 0c-1.856 .536 -3 1.526 -3 2.598" />
          <path d="M3 6v10c0 .888 .772 1.45 2 2" />
          <path d="M3 11c0 .888 .772 1.45 2 2" />
        </svg>
      </span>
      <h1>财务结算系统</h1>
      <p class="subtitle" v-if="!isSetup">请输入密码登录</p>
      <p class="subtitle" v-else>首次使用，请设置登录密码</p>

      <div v-if="error" class="error-msg">{{ error }}</div>

      <div class="form-group">
        <input
          v-model="password"
          type="password"
          :placeholder="isSetup ? '设置密码（至少4位）' : '输入密码'"
          @keyup.enter="submit"
          autofocus
        />
      </div>

      <div v-if="isSetup" class="form-group">
        <input
          v-model="passwordConfirm"
          type="password"
          placeholder="确认密码"
          @keyup.enter="submit"
        />
      </div>

      <AppButton variant="primary" size="lg" @click="submit" :disabled="loading" :loading="loading">
        {{ isSetup ? '设置密码' : '登录' }}
      </AppButton>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const password = ref('')
const passwordConfirm = ref('')
const isSetup = ref(false)
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    const r = await api.getAuthStatus()
    isSetup.value = !r.data.password_set
  } catch {
    isSetup.value = false
  }
})

async function submit() {
  error.value = ''
  loading.value = true
  try {
    if (isSetup.value) {
      if (password.value.length < 4) {
        error.value = '密码长度不能少于4位'
        loading.value = false
        return
      }
      if (password.value !== passwordConfirm.value) {
        error.value = '两次密码输入不一致'
        loading.value = false
        return
      }
      const r = await api.setupPassword(password.value)
      api.setToken(r.data.token)
      router.push('/')
    } else {
      const r = await api.login(password.value)
      api.setToken(r.data.token)
      router.push('/')
    }
  } catch (e) {
    error.value = e.response?.data?.detail || '操作失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary);
}
.login-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 40px;
  width: 380px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  text-align: center;
  position: relative;
  overflow: hidden;
}
.accent-line {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 4px;
  background: linear-gradient(90deg, var(--color-accent), var(--color-primary));
}
.brand-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  margin-bottom: 8px;
  color: var(--color-primary);
}
.brand-icon svg {
  width: 100%;
  height: 100%;
}
.login-card h1 {
  font-size: 22px;
  color: var(--color-primary);
  margin-bottom: 4px;
}
.subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 24px;
}
.form-group {
  margin-bottom: 16px;
}
input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 15px;
  box-sizing: border-box;
  outline: none;
  transition: border-color 0.2s;
}
input:focus {
  border-color: var(--color-primary-dark);
  box-shadow: 0 0 0 3px rgba(22,33,62,0.1);
}
.btn-login {
  width: 100%;
  padding: 10px;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
  color: var(--bg-card);
  border: none;
  border-radius: 6px;
  font-size: 15px;
  cursor: pointer;
  margin-top: 8px;
  transition: opacity 0.15s;
}
.btn-login:hover {
  opacity: 0.9;
}
.btn-login:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.error-msg {
  background: var(--bg-badge-error);
  color: var(--color-danger);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  margin-bottom: 16px;
}
</style>
