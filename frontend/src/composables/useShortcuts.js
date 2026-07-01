import { onMounted, onUnmounted } from 'vue'

// Global Alt+wheel handler for AG Grid horizontal scrolling
function onAltWheel(e) {
  if (!e.altKey) return
  const target = e.target.closest('.ag-body-viewport, .ag-center-cols-viewport')
  if (!target) return
  e.preventDefault()
  target.scrollLeft += e.deltaY
}

let _saveCallback = null
let _wheelInstalled = false

function installWheel() {
  if (_wheelInstalled) return
  document.addEventListener('wheel', onAltWheel, { passive: false })
  _wheelInstalled = true
}

function uninstallWheel() {
  if (!_wheelInstalled) return
  document.removeEventListener('wheel', onAltWheel)
  _wheelInstalled = false
}

function onKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    if (_saveCallback) _saveCallback()
  }
}

export function useShortcuts({ onSave } = {}) {
  _saveCallback = onSave || null

  onMounted(() => {
    installWheel()
    document.addEventListener('keydown', onKeydown)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', onKeydown)
  })
}

// Also export standalone wheel install for App.vue one-time setup
export function installGlobalShortcuts() {
  installWheel()
}
