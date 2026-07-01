<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="close">
      <div class="modal-panel" :style="{ width: width }">
        <div class="modal-header">
          <h3 class="modal-title">{{ title }}</h3>
          <button v-if="closable" class="modal-close" @click="close" title="关闭(ESC)">&times;</button>
        </div>
        <div class="modal-body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="modal-footer">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  width: { type: String, default: '400px' },
  closable: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue', 'close'])

const visible = computed(() => props.modelValue)

function close() {
  if (!props.closable) return
  emit('update:modelValue', false)
  emit('close')
}

function onKeydown(e) {
  if (e.key === 'Escape' && props.modelValue) close()
}

watch(visible, (v) => {
  if (v) {
    document.addEventListener('keydown', onKeydown)
    document.body.style.overflow = 'hidden'
  } else {
    document.removeEventListener('keydown', onKeydown)
    document.body.style.overflow = ''
  }
}, { immediate: true })

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-modal-overlay);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-panel {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-elevated);
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  max-width: 90vw;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-lg) var(--space-xl);
  border-bottom: 1px solid var(--border-light);
}

.modal-title {
  font-size: var(--text-lg);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
}

.modal-close {
  width: 28px;
  height: 28px;
  border: none;
  background: none;
  font-size: 20px;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: all var(--transition-fast);
}

.modal-close:hover {
  background: var(--palette-gray-150);
  color: var(--text-primary);
}

.modal-body {
  padding: var(--space-xl);
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  padding: var(--space-lg) var(--space-xl);
  border-top: 1px solid var(--border-light);
}
</style>
