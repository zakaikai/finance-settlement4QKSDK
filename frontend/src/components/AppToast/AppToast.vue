<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          :class="['toast-item', `toast--${t.type}`]"
          @click="remove(t.id)"
        >
          <span class="toast-icon">{{ icons[t.type] }}</span>
          <span class="toast-msg">{{ t.message }}</span>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { createToastProvider } from './useToast.js'

const icons = { success: '✓', error: '✕', warning: '!', info: 'i' }

const toasts = createToastProvider()

function remove(id) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}
</script>

<style scoped>
.toast-container {
  position: fixed;
  top: 72px;
  right: 24px;
  z-index: 300;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  pointer-events: none;
}

.toast-item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 10px 20px;
  border-radius: var(--radius-md);
  background: var(--bg-card);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  font-size: var(--text-base);
  color: var(--text-primary);
  cursor: pointer;
  pointer-events: auto;
  min-width: 200px;
  max-width: 420px;
  border-left: 4px solid var(--color-info);
}

.toast--success { border-left-color: var(--color-success); }
.toast--error   { border-left-color: var(--color-danger); }
.toast--warning { border-left-color: var(--color-warning); }

.toast-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: var(--weight-bold);
  color: var(--text-on-primary);
}

.toast--success .toast-icon { background: var(--color-success); }
.toast--error .toast-icon   { background: var(--color-danger); }
.toast--warning .toast-icon { background: var(--color-warning); }
.toast--info .toast-icon    { background: var(--color-info); }

.toast-msg { flex: 1; word-break: break-word; }

/* transitions */
.toast-enter-active { transition: all 0.25s ease-out; }
.toast-leave-active { transition: all 0.2s ease-in; }
.toast-enter-from   { opacity: 0; transform: translateX(40px); }
.toast-leave-to     { opacity: 0; transform: translateX(40px); }
</style>
