<template>
  <button
    :class="classes"
    :disabled="disabled || loading"
    :type="type"
    @click="$emit('click', $event)"
  >
    <span v-if="loading" class="btn-loading-spinner"></span>
    <slot />
  </button>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  variant: {
    type: String,
    default: 'default',
    validator: (v) => ['primary', 'success', 'danger', 'warning', 'info', 'default'].includes(v),
  },
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md', 'lg'].includes(v),
  },
  disabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  type: { type: String, default: 'button' },
})

defineEmits(['click'])

const classes = computed(() => [
  'app-btn',
  `app-btn--${props.variant}`,
  `app-btn--${props.size}`,
  { 'app-btn--loading': props.loading },
])
</script>

<style scoped>
/* ── Base ─────────────────────────────────────── */
.app-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  font-family: inherit;
  font-weight: var(--weight-medium);
  white-space: nowrap;
  user-select: none;
  transition: all var(--transition-fast);
  line-height: var(--leading-tight);
}

.app-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Sizes ────────────────────────────────────── */
.app-btn--sm  { padding: 4px 10px; font-size: var(--text-sm); border-radius: var(--radius-sm); }
.app-btn--md  { padding: 6px 14px; font-size: var(--text-base); border-radius: var(--radius-md); }
.app-btn--lg  { padding: 8px 20px; font-size: var(--text-md); border-radius: var(--radius-md); }

/* ── Variant: primary ─────────────────────────── */
.app-btn--primary {
  background: var(--color-primary);
  color: var(--text-on-primary);
}
.app-btn--primary:hover:not(:disabled) {
  background: var(--color-primary-dark);
}

/* ── Variant: success ─────────────────────────── */
.app-btn--success {
  background: var(--color-success);
  color: var(--text-on-primary);
}
.app-btn--success:hover:not(:disabled) {
  filter: brightness(1.1);
}

/* ── Variant: danger ──────────────────────────── */
.app-btn--danger {
  background: var(--color-danger);
  color: var(--text-on-primary);
}
.app-btn--danger:hover:not(:disabled) {
  filter: brightness(1.1);
}

/* ── Variant: warning ─────────────────────────── */
.app-btn--warning {
  color: var(--color-warning);
  border-color: var(--color-warning);
  background: transparent;
}
.app-btn--warning:hover:not(:disabled) {
  background: var(--color-warning);
  color: var(--text-on-primary);
}

/* ── Variant: info ────────────────────────────── */
.app-btn--info {
  color: var(--color-info);
  border-color: var(--color-info);
  background: transparent;
}
.app-btn--info:hover:not(:disabled) {
  background: var(--color-info);
  color: var(--text-on-primary);
}

/* ── Variant: default ─────────────────────────── */
.app-btn--default {
  color: var(--text-primary);
  border-color: var(--border-default);
  background: var(--bg-card);
}
.app-btn--default:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

/* ── Loading spinner ──────────────────────────── */
.btn-loading-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: app-btn-spin 0.6s linear infinite;
}

@keyframes app-btn-spin {
  to { transform: rotate(360deg); }
}
</style>
