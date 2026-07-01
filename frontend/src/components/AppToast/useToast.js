import { ref } from 'vue'

let _id = 0
const toasts = ref([])

function add(message, type = 'info', duration = 3000) {
  const id = ++_id
  toasts.value.push({ id, message, type })
  if (duration > 0) {
    setTimeout(() => remove(id), duration)
  }
}

function remove(id) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

export function createToastProvider() {
  return toasts
}

export function useToast() {
  return {
    success: (msg, dur) => add(msg, 'success', dur),
    error: (msg, dur) => add(msg, 'error', dur),
    warning: (msg, dur) => add(msg, 'warning', dur),
    info: (msg, dur) => add(msg, 'info', dur),
    remove,
  }
}
