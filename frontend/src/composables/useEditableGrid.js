import { ref, reactive, computed, onMounted } from 'vue'

/**
 * Shared change-tracking composable for AG Grid inline editing.
 *
 * @param {Function} opts.load       - async () => rows[]   fetch fresh data
 * @param {Function} opts.save       - async (items) => void  persist all changes
 * @param {Function} opts.createEmpty - () => ({}), default values for new rows
 * @param {Function} [opts.rowKey]   - (row) => string, defaults to row.id ?? row._tempId
 * @param {Function} [opts.afterSave] - async () => void, called after successful save
 */
export function useEditableGrid({ load, save, createEmpty, rowKey, afterSave }) {
  const data = ref([])
  const changes = reactive({})
  const dirty = computed(() => Object.keys(changes).length > 0)
  const changeCount = computed(() => Object.keys(changes).length)
  let _counter = 0

  function _key(row) {
    if (rowKey) return rowKey(row)
    return String(row.id || row._tempId || '')
  }

  async function reload() {
    const rows = await load()
    data.value = rows || []
    Object.keys(changes).forEach(k => delete changes[k])
  }

  function addRow(overrides) {
    const tempId = `_new_${++_counter}`
    const base = createEmpty ? createEmpty() : {}
    const row = { _isNew: true, _tempId: tempId, ...base, ...overrides }
    data.value = [...data.value, row]
    changes[_key(row)] = { action: 'create', data: { ...row } }
    return row
  }

  /** Insert a copy of *row* right after it in the grid. */
  function copyRow(row, overrides) {
    const idx = data.value.findIndex(r => _key(r) === _key(row))
    if (idx === -1) return null
    const tempId = `_new_${++_counter}`
    const copy = { _isNew: true, _tempId: tempId, ...row, ...overrides }
    // strip identity fields from source
    delete copy.id; delete copy._tempId; copy._isNew = true; copy._tempId = tempId
    const arr = [...data.value]
    arr.splice(idx + 1, 0, copy)
    data.value = arr
    changes[tempId] = { action: 'create', data: { ...copy } }
    return { copy, idx }
  }

  function onCellChanged(event, onFieldChange) {
    const row = event.data
    const id = _key(row)
    if (onFieldChange) onFieldChange(row, event.colDef.field, event.newValue)
    if (row._isNew || !changes[id] || changes[id].action === 'create') {
      changes[id] = { action: row._isNew ? 'create' : 'update', data: { ...row } }
    } else {
      changes[id].data = { ...row }
    }
  }

  function removeRow(row) {
    const id = _key(row)
    if (row._isNew) {
      delete changes[id]
      data.value = data.value.filter(r => _key(r) !== id)
    } else {
      changes[id] = { action: 'delete', data: { ...row } }
      data.value = data.value.filter(r => _key(r) !== id)
    }
  }

  async function saveAll() {
    const items = Object.entries(changes).map(([k, v]) => ({ _key: k, ...v }))
    if (!items.length) return
    await save(items)
    Object.keys(changes).forEach(k => delete changes[k])
    if (afterSave) await afterSave()
    else await reload()
  }

  function discard() {
    Object.keys(changes).forEach(k => delete changes[k])
    reload()
  }

  onMounted(() => reload())

  return reactive({
    data, changes, dirty, changeCount,
    reload, addRow, copyRow, onCellChanged, removeRow, saveAll, discard,
  })
}
