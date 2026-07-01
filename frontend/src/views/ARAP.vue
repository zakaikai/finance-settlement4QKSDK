<template>
  <div class="arap">
    <h2>应收应付</h2>

    <div class="tabs">
      <button :class="{ active: entityType === 'channel' }" @click="switchMode('channel')">应收</button>
      <button :class="{ active: entityType === 'publisher' }" @click="switchMode('publisher')">应付</button>
    </div>

    <div class="search-panel">
      <label for="arap-month-from">收款月份:</label>
      <input id="arap-month-from" v-model="monthFrom" placeholder="YYYY-MM" class="input-sm" />
      <span class="search-sep">→</span>
      <input id="arap-month-to" v-model="monthTo" placeholder="YYYY-MM" class="input-sm" />
      <button class="btn-search" @click="loadPivot">查询</button>
      <button class="btn-export" :disabled="!gridReady" @click="exportCSV">导出 CSV</button>
      <button class="btn-search" @click="doSnapshot">生成快照</button>
      <button class="btn-warn" @click="doMonthlyClose">月结 {{ workingMonth }}</button>
    </div>

    <div class="pending-hint" v-if="pendingItems.length">
      未锁定提醒：
      <span v-for="p in pendingItems" :key="p.month" class="pending-tag">
        {{ p.month }}：渠道 {{ p.channel_pending }} 条 / 研发商 {{ p.publisher_pending }} 条
      </span>
    </div>

    <div class="closed-hint" v-if="closedMonths.length">
      已关闭月份：
      <span v-for="m in closedMonths" :key="m" class="closed-tag">
        {{ m }}<button class="btn-reopen" @click="doReopenMonth(m)" title="反月结">×</button>
      </span>
    </div>

    <div ref="gridContainer" class="grid-container">
      <ag-grid-vue
        :rowData="pivotRows"
        :columnDefs="pivotCols"
        class="ag-theme-quartz grid"
        :defaultColDef="defaultColDef"
        domLayout="autoHeight"
        :animateRows="true"
        :enableCellTextSelection="true"
        :ensureDomOrder="true"
        :headerHeight="32"
        :rowHeight="30"
        @grid-ready="onGridReady"
      />
    </div>

    <div v-if="pivotRows.length > 0" class="summary-bar">
      共 {{ pivotRows.length }} 条记录
    </div>

    <!-- Breakdown Modal (click 余额) -->
    <div v-if="showBreakdownModal" class="modal-overlay" @click.self="closeBreakdownModal">
      <div class="modal-dialog" style="width: 600px; max-height: 85vh; overflow-y: auto;">
        <h3>{{ breakdownRow?.entity_name }} × {{ breakdownRow?.company_name }} — 收付明细</h3>

        <!-- Summary cards — labels adapt to entity_type (AR: 借方=应收/贷方=已收, AP: 借方=已付/贷方=应付) -->
        <div class="summary-cards">
          <div class="summary-card">
            <div class="summary-card-label">{{ isAR ? '借方' : '借方' }}</div>
            <div class="summary-card-value">{{ formatMoney(isAR ? breakdownRow?.debit_total : breakdownRow?.credit_total) }}</div>
            <div class="summary-card-sub">{{ isAR ? '应收总额' : '已付总额' }}</div>
          </div>
          <div class="summary-card">
            <div class="summary-card-label">{{ isAR ? '贷方' : '贷方' }}</div>
            <div class="summary-card-value">{{ formatMoney(isAR ? breakdownRow?.credit_total : breakdownRow?.debit_total) }}</div>
            <div class="summary-card-sub">{{ isAR ? '已收总额' : '应付总额' }}</div>
          </div>
          <div class="summary-card" :class="{ 'credit-balance': breakdownBalance > 0.005 }">
            <div class="summary-card-label">余额</div>
            <div class="summary-card-value">{{ formatMoney(breakdownBalance) }}</div>
            <div class="summary-card-sub">{{ isAR ? '应收 − 已收' : '应付 − 已付' }}</div>
          </div>
        </div>

        <!-- Debit breakdown -->
        <div class="section-title">快照构成（按付款月）</div>
        <table class="preview-table" v-if="debitItems.length">
          <thead>
            <tr><th>付款月</th><th>金额</th></tr>
          </thead>
          <tbody>
            <tr v-for="d in debitItems" :key="d.confirmed_month">
              <td>{{ d.confirmed_month }}</td>
              <td class="num">{{ formatMoney(d.amount) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="hint-text">暂无快照数据</div>

        <!-- Payment records -->
        <div class="section-title" style="display: flex; justify-content: space-between; align-items: center;">
          <span>收付记录</span>
          <button class="btn-search" style="padding: 3px 12px; font-size: 12px;" @click="breakdownFormVisible = !breakdownFormVisible">
            {{ breakdownFormVisible ? '− 收起' : '+ 登记收付款' }}
          </button>
        </div>

        <!-- Inline registration form -->
        <div v-if="breakdownFormVisible" class="payment-inline-form">
          <div class="form-row">
            <label>收款月：</label>
            <input v-model="breakdownFormMonth" class="input-md" placeholder="YYYY-MM" style="width: 120px;" />
          </div>
          <div class="form-row">
            <label>金额：</label>
            <input v-model="breakdownFormAmount" class="input-md" type="number" step="0.01" min="0.01" placeholder="输入收款/付款金额" />
          </div>
          <div class="form-row">
            <label>备注：</label>
            <input v-model="breakdownFormNote" class="input-md" placeholder="可选" />
          </div>

          <div v-if="breakdownFifoPreview.length > 0" class="payment-preview">
            <div class="preview-title">冲销预览（FIFO）</div>
            <table class="preview-table">
              <thead>
                <tr><th>游戏</th><th>月份</th><th>未结余额</th><th>本次冲销</th></tr>
              </thead>
              <tbody>
                <tr v-for="(p, i) in breakdownFifoPreview" :key="i">
                  <td>{{ p.game_id }}</td>
                  <td>{{ p.month }}</td>
                  <td class="num">{{ formatMoney(p.open_balance) }}</td>
                  <td class="num">{{ formatMoney(p.allocated) }}</td>
                </tr>
              </tbody>
            </table>
            <div v-if="breakdownFifoRemaining > 0.005" class="preview-warn">
              剩余未分配：{{ formatMoney(breakdownFifoRemaining) }}
            </div>
          </div>

          <div v-if="breakdownFormError" class="form-error">{{ breakdownFormError }}</div>

          <div class="modal-actions" style="margin-top: 12px;">
            <button class="btn-search" @click="submitBreakdownPayment" :disabled="!breakdownCanSubmit || breakdownSubmitting">
              {{ breakdownSubmitting ? '提交中...' : '确认登记' }}
            </button>
          </div>
        </div>

        <!-- Payment history -->
        <table class="preview-table" v-if="paymentItems.length">
          <thead>
            <tr><th>收款月</th><th>凭证号</th><th>金额</th><th>备注</th><th>登记时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in paymentItems" :key="p.id">
              <td>{{ p.collection_month }}</td>
              <td>{{ p.transaction_no }}</td>
              <td class="num">{{ formatMoney(p.amount) }}</td>
              <td>{{ p.note || '' }}</td>
              <td>{{ p.created_at?.slice(0, 10) }}</td>
              <td>
                <button class="btn-reopen" style="font-size: 12px; padding: 1px 6px;" @click="doDeletePayment(p.id)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!paymentItems.length && !breakdownFormVisible" class="hint-text">暂无收付记录</div>

        <div class="modal-actions">
          <button class="btn-export" @click="closeBreakdownModal">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import api, { logError } from '../api'

const entityType = ref('channel')
const monthFrom = ref(_prevMonths(5))
const monthTo = ref(_currentMonth())
const pivotRows = ref([])
const pivotColumns = ref([])
const closedMonths = ref([])
const workingMonth = ref('')
const pendingItems = ref([])
const gridApi = ref(null)
const gridReady = ref(false)
const companies = ref([])

async function loadCompanies() {
  try {
    const r = await api.getCompanies()
    companies.value = r.data.data || []
  } catch (e) { /* ignore */ }
}

async function handleCompanyOverride(row, newCompanyName) {
  if (!newCompanyName || entityType.value !== 'publisher') return
  const company = companies.value.find(c => c.company_name === newCompanyName)
  if (!company) return

  const entityId = row.entity_id
  const origCompanyId = row.company_id

  if (!entityId || origCompanyId == null) return

  try {
    await api.arapCompanyOverride({
      entity_id: entityId,
      original_company_id: origCompanyId,
      override_company_id: company.company_id,
    })
    // Refresh to update display and styling
    await loadPivot()
  } catch (e) {
    alert('覆盖失败: ' + (e.response?.data?.detail || e.message))
  }
}

function _currentMonth() {
  const d = new Date()
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
}

function _prevMonths(n) {
  const d = new Date()
  d.setMonth(d.getMonth() - n)
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
}

const formatMoney = (v) => {
  if (v == null || isNaN(v)) return '¥0.00'
  return '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const defaultColDef = {
  sortable: true,
  filter: true,
  resizable: true,
  minWidth: 100,
}

const fixedCols = computed(() => [
  { field: 'rowNo', headerName: '#', width: 50, pinned: 'left', sortable: false, filter: false,
    valueFormatter: p => (p.node?.rowIndex ?? 0) + 1,
    cellStyle: { color: 'var(--text-light)', backgroundColor: 'var(--palette-gray-50)' } },
  { field: 'entity_id', hide: true },
  { field: 'company_id', hide: true },
  { field: 'entity_name', headerName: entityType.value === 'channel' ? '渠道' : '研发商',
    width: 140, pinned: 'left' },
  { field: 'company_name', headerName: '我方主体', width: 160, pinned: 'left',
    editable: p => entityType.value === 'publisher',
    cellEditor: entityType.value === 'publisher' ? 'agSelectCellEditor' : undefined,
    cellEditorParams: {
      values: companies.value.map(c => c.company_name),
    },
    cellStyle: p => {
      if (p.data?.is_overridden) {
        return { fontWeight: 700, color: 'var(--color-primary)', fontStyle: 'italic' }
      }
      return {}
    },
    onCellValueChanged: p => {
      if (!p.data || entityType.value !== 'publisher') return
      const newName = p.newValue
      const oldName = p.oldValue
      if (newName === oldName) return
      handleCompanyOverride(p.data, newName)
    },
  },
])

const pivotCols = computed(() => {
  const wm = workingMonth.value
  const monthCols = pivotColumns.value.map(m => ({
    field: 'cell_' + m,
    headerName: m,
    width: 120,
    cellStyle: p => {
      const style = {
        textAlign: 'right',
        fontWeight: p.value > 0 ? 700 : 400,
        backgroundColor: closedMonths.value.includes(m) ? 'var(--palette-gray-100)' : 'inherit',
      }
      if (m === wm) {
        style.borderLeft = '3px solid var(--color-success)'
        style.backgroundColor = 'rgba(34,197,94,0.06)'
      }
      return style
    },
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '-',
  }))
  return [...fixedCols.value, ...monthCols, {
    field: 'total',
    headerName: '总计',
    width: 120,
    pinned: 'right',
    cellStyle: { textAlign: 'right', fontWeight: 700, backgroundColor: 'var(--palette-gray-50)' },
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '-',
  }, {
    field: 'balance',
    headerName: '余额',
    width: 130,
    pinned: 'right',
    cellStyle: p => {
      return {
        textAlign: 'right',
        fontWeight: 700,
        cursor: 'pointer',
        color: 'var(--color-primary)',
        backgroundColor: 'rgba(99,102,241,0.08)',
      }
    },
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '-',
    onCellClicked: p => {
      if (p.data) openBreakdownModal(p.data)
    },
  }]
})

function onGridReady(params) {
  gridApi.value = params.api
  gridReady.value = true
}

async function loadPivot() {
  try {
    const r = await api.getARAPPivot({
      entity_type: entityType.value,
      month_from: monthFrom.value,
      month_to: monthTo.value,
    })
    pivotColumns.value = r.data.columns
    const cols = r.data.columns
    pivotRows.value = (r.data.rows || []).map(row => {
      const balance = (row.debit_total || 0) - (row.credit_total || 0)
      const flat = {
        entity_id: row.entity_id,
        company_id: row.company_id,
        entity_name: row.entity_name,
        company_name: row.company_name,
        is_overridden: row.is_overridden,
        debit_total: row.debit_total != null ? row.debit_total : 0,
        credit_total: row.credit_total != null ? row.credit_total : 0,
        balance: Math.round(balance * 100) / 100,
      }
      for (const m of cols) {
        flat['cell_' + m] = row.cells[m] != null ? row.cells[m] : null
      }
      flat['total'] = row.total != null ? row.total : null
      return flat
    })
    gridApi.value?.refreshCells()
  } catch (e) {
    logError('loadPivot', e)
    pivotRows.value = []
    pivotColumns.value = []
  }
}

async function loadClosedMonths() {
  try {
    const r = await api.getMonthlyCloses()
    closedMonths.value = r.data.closed_months || []
  } catch (e) { logError('loadClosedMonths', e) }
}

function switchMode(mode) {
  entityType.value = mode
  loadPivot()
}

async function doSnapshot() {
  const m = prompt('请输入确认月（YYYY-MM）：', _currentMonth())
  if (!m || !/^\d{4}-\d{2}$/.test(m)) { alert('请输入有效月份，如 2026-06'); return }
  if (!confirm(`将从 channel_locks + publisher_locks 增量快照到 ${m}。\n已快照过的锁会跳过。确认？`)) return
  try {
    const r = await api.arapSnapshot(m)
    const d = r.data
    alert(`快照完成：${d.inserted} 条（渠道 ${d.channel_locks_processed} + 研发商 ${d.publisher_locks_processed}）`)
    await loadPivot()
  } catch (e) { alert('快照失败: ' + (e.response?.data?.detail || e.message)) }
}

async function doMonthlyClose() {
  const m = workingMonth.value
  if (!m) { alert('无法确定当前工作月'); return }
  if (!confirm(`确认关闭 ${m} 月份？关闭后该月新锁定将路由到当前工作月。`)) return
  try {
    await api.monthlyClose({ month: m })
    await loadClosedMonths()
    await loadWorkingMonth()
    await loadPivot()
  } catch (e) {
    const detail = e.response?.data?.detail
    alert('月结失败: ' + (detail || e.message))
  }
}

async function doReopenMonth(m) {
  if (!confirm(`确认反月结 ${m}？\n该月将恢复为可锁定状态，已有快照数据不受影响。`)) return
  try {
    await api.deleteMonthlyClose(m)
    await loadClosedMonths()
    await loadWorkingMonth()
    await loadPivot()
  } catch (e) {
    const detail = e.response?.data?.detail
    alert('反月结失败: ' + (detail || e.message))
  }
}

async function loadWorkingMonth() {
  try {
    const r = await api.getWorkingMonth()
    workingMonth.value = r.data.working_month || ''
  } catch (e) { logError('loadWorkingMonth', e) }
}

async function loadPendingCount() {
  try {
    const r = await api.getPendingCount()
    pendingItems.value = r.data.pending || []
  } catch (e) { logError('loadPendingCount', e) }
}

function exportCSV() {
  if (!gridApi.value || gridApi.value.isDestroyed()) return
  const rows = []
  gridApi.value.forEachNodeAfterFilterAndSort(n => rows.push(n.data))
  if (!rows.length) { alert('当前无数据'); return }

  const cols = pivotColumns.value
  const header = ['行号', entityType.value === 'channel' ? '渠道' : '研发商',
    '我方主体', ...cols, '总计', '余额'].join(',')
  const lines = [header]
  rows.forEach((r, i) => {
    const vals = [i + 1, csvEscape(r.entity_name), csvEscape(r.company_name)]
    for (const m of cols) {
      const v = r['cell_' + m]
      vals.push(v != null ? v.toFixed(2) : '')
    }
    vals.push(r.total != null ? r.total.toFixed(2) : '')
    vals.push(r.balance != null ? r.balance.toFixed(2) : '')
    lines.push(vals.join(','))
  })

  const bom = '﻿'
  const blob = new Blob([bom + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `${entityType.value}_arap.csv`
  a.click(); URL.revokeObjectURL(url)
}

function csvEscape(v) {
  if (!v) return ''
  const s = String(v)
  return s.includes(',') || s.includes('"') || s.includes('\n')
    ? '"' + s.replace(/"/g, '""') + '"' : s
}

// ── Breakdown Modal ──
const showBreakdownModal = ref(false)
const breakdownRow = ref(null)
const debitItems = ref([])
const paymentItems = ref([])
const breakdownFormVisible = ref(false)
const breakdownFormMonth = ref(_currentMonth())
const breakdownFormAmount = ref('')
const breakdownFormNote = ref('')
const breakdownSubmitting = ref(false)
const breakdownFormError = ref('')
const breakdownOpenItems = ref([])

const isAR = computed(() => entityType.value === 'channel')
const breakdownBalance = computed(() => {
  const d = breakdownRow.value?.debit_total || 0
  const c = breakdownRow.value?.credit_total || 0
  return Math.round((d - c) * 100) / 100
})

const breakdownCanSubmit = computed(() => {
  const amount = parseFloat(breakdownFormAmount.value)
  return amount > 0 && breakdownRow.value
    && breakdownFormMonth.value && /^\d{4}-\d{2}$/.test(breakdownFormMonth.value)
    && breakdownFifoPreview.value.length > 0
    && Math.abs(breakdownFifoRemaining.value) < 0.005
    && !breakdownSubmitting.value
})

const breakdownFifoPreview = computed(() => {
  const amount = parseFloat(breakdownFormAmount.value)
  if (!amount || amount <= 0 || !breakdownRow.value) return []
  const row = breakdownRow.value
  const items = breakdownOpenItems.value
    .filter(i => i.entity_type === entityType.value
      && i.entity_id === row.entity_id
      && i.company_id === row.company_id)
    .sort((a, b) => a.month.localeCompare(b.month))
  let remaining = amount
  const preview = []
  for (const item of items) {
    if (remaining <= 0.005) break
    const alloc = Math.min(remaining, item.open_balance)
    preview.push({ ...item, allocated: Math.round(alloc * 100) / 100 })
    remaining -= alloc
  }
  return preview
})

const breakdownFifoRemaining = computed(() => {
  const amount = parseFloat(breakdownFormAmount.value) || 0
  const allocated = breakdownFifoPreview.value.reduce((s, p) => s + p.allocated, 0)
  return Math.round((amount - allocated) * 100) / 100
})

async function openBreakdownModal(row) {
  breakdownRow.value = row
  breakdownFormVisible.value = false
  breakdownFormMonth.value = _currentMonth()
  breakdownFormAmount.value = ''
  breakdownFormNote.value = ''
  breakdownFormError.value = ''
  breakdownSubmitting.value = false
  showBreakdownModal.value = true
  try {
    const [bdResp, oiResp] = await Promise.all([
      api.getBreakdown({
        entity_type: entityType.value,
        entity_id: row.entity_id,
        company_id: row.company_id,
      }),
      api.getOpenItems({ entity_type: entityType.value }),
    ])
    debitItems.value = bdResp.data.debit_items || []
    paymentItems.value = bdResp.data.payment_items || []
    breakdownOpenItems.value = oiResp.data.data || []
  } catch (e) {
    logError('breakdown', e)
    debitItems.value = []
    paymentItems.value = []
    breakdownOpenItems.value = []
  }
}

function closeBreakdownModal() {
  showBreakdownModal.value = false
  breakdownRow.value = null
  debitItems.value = []
  paymentItems.value = []
  breakdownOpenItems.value = []
}

async function submitBreakdownPayment() {
  if (!breakdownCanSubmit.value || !breakdownRow.value) return
  breakdownSubmitting.value = true
  breakdownFormError.value = ''
  try {
    await api.registerPayment({
      entity_type: entityType.value,
      entity_id: breakdownRow.value.entity_id,
      company_id: breakdownRow.value.company_id,
      amount: parseFloat(breakdownFormAmount.value),
      note: breakdownFormNote.value || null,
    }, breakdownFormMonth.value)
    // Refresh
    breakdownFormVisible.value = false
    breakdownFormAmount.value = ''
    breakdownFormNote.value = ''
    await Promise.all([loadPivot(), refreshBreakdownData()])
  } catch (e) {
    const detail = e.response?.data?.detail
    breakdownFormError.value = detail ? (typeof detail === 'string' ? detail : JSON.stringify(detail)) : e.message
  } finally {
    breakdownSubmitting.value = false
  }
}

async function refreshBreakdownData() {
  if (!breakdownRow.value) return
  try {
    const [bdResp, oiResp] = await Promise.all([
      api.getBreakdown({
        entity_type: entityType.value,
        entity_id: breakdownRow.value.entity_id,
        company_id: breakdownRow.value.company_id,
      }),
      api.getOpenItems({ entity_type: entityType.value }),
    ])
    debitItems.value = bdResp.data.debit_items || []
    paymentItems.value = bdResp.data.payment_items || []
    breakdownOpenItems.value = oiResp.data.data || []
  } catch (e) { logError('breakdown refresh', e) }
}

async function doDeletePayment(paymentId) {
  if (!confirm('确认删除该付款记录？将恢复对应的未结余额。')) return
  try {
    await api.deletePayment(paymentId)
    await Promise.all([loadPivot(), refreshBreakdownData()])
  } catch (e) {
    alert('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

// ── Lifecycle ──
onMounted(() => { loadCompanies(); loadPivot(); loadClosedMonths(); loadWorkingMonth(); loadPendingCount() })
</script>

<style scoped>
h2 { margin-bottom: 16px; font-size: 20px; }
.tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tabs button {
  padding: 6px 16px; border: 1px solid var(--border-default); border-radius: 6px;
  background: var(--bg-card); cursor: pointer; font-size: 13px; color: var(--text-secondary);
}
.tabs button.active { background: var(--color-primary); color: var(--text-on-primary); border-color: var(--color-primary); }
.search-panel {
  display: flex; align-items: center; gap: 12px;
  background: var(--bg-card); padding: 12px 16px; border-radius: 8px;
  box-shadow: var(--shadow-card); margin-bottom: 12px; flex-wrap: wrap;
}
.search-panel label { font-size: 13px; color: var(--text-secondary); }
.input-sm { padding: 5px 8px; border: 1px solid var(--border-default); border-radius: 4px; font-size: 13px; width: 100px; background: var(--bg-card); color: var(--text-primary); }
.search-sep { color: var(--text-muted); font-size: 13px; }
.btn-search { padding: 6px 16px; background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-export { padding: 6px 14px; background: var(--palette-gray-80); border: 1px solid var(--border-default); border-radius: 6px; cursor: pointer; font-size: 13px; color: var(--text-secondary); }
.btn-bill { padding: 6px 14px; background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-bill:disabled { background: var(--text-light); cursor: not-allowed; }
.btn-warn { padding: 6px 14px; background: var(--color-warning, #f0ad4e); color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; margin-left: auto; }
.closed-hint { font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }
.closed-tag { display: inline-block; background: var(--palette-gray-100); padding: 2px 8px; border-radius: 4px; margin-right: 4px; font-size: 12px; }
.btn-reopen {
  margin-left: 4px; border: none; background: none; color: var(--color-danger);
  font-weight: 700; font-size: 14px; cursor: pointer; line-height: 1; padding: 0 2px;
}
.btn-reopen:hover { opacity: 0.7; }
.pending-hint { font-size: 13px; color: var(--color-warning, #f0ad4e); margin-bottom: 12px; }
.pending-tag { display: inline-block; background: rgba(240,173,78,0.12); padding: 2px 8px; border-radius: 4px; margin-right: 6px; font-size: 12px; }
.grid-container { background: var(--bg-card); border-radius: 8px; box-shadow: var(--shadow-card); padding: 8px; margin-bottom: 12px; }
.grid { width: 100%; }
.summary-bar { font-size: 13px; color: var(--text-secondary); padding: 8px 12px; background: var(--bg-card); border-radius: 8px; box-shadow: var(--shadow-card); }

/* Payment modal */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center;
  z-index: 10000;
}
.modal-dialog {
  background: #fff; border-radius: 12px; padding: 28px 32px;
  width: 480px; max-width: 90vw; box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}
.modal-dialog h3 { font-size: 18px; margin-bottom: 8px; }
.form-row { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.form-row label { font-size: 14px; color: #444; min-width: 80px; text-align: right; }
.input-md { padding: 6px 10px; border: 1px solid #d0d5dd; border-radius: 4px; font-size: 13px; width: 280px; }
.modal-actions { display: flex; gap: 12px; justify-content: center; margin-top: 24px; }
.payment-preview { background: var(--palette-gray-50); border-radius: 6px; padding: 12px; margin-bottom: 12px; max-height: 200px; overflow-y: auto; }
.preview-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--text-secondary); }
.preview-table { width: 100%; font-size: 13px; border-collapse: collapse; }
.preview-table th { text-align: left; padding: 4px 6px; border-bottom: 2px solid var(--border-default); font-weight: 600; color: var(--text-secondary); }
.preview-table td { padding: 4px 6px; border-bottom: 1px solid var(--border-light); }
.preview-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.preview-warn { font-size: 12px; color: var(--color-danger); margin-top: 6px; }
.payment-result { font-size: 14px; color: var(--color-success); padding: 8px 0; }
.form-error { font-size: 13px; color: var(--color-danger); padding: 6px 0; }

/* Summary cards */
.summary-cards { display: flex; gap: 12px; margin-bottom: 20px; }
.summary-card { flex: 1; text-align: center; padding: 12px 8px; border-radius: 8px; background: var(--palette-gray-50); border: 1px solid var(--border-default); }
.summary-card-label { font-size: 12px; color: var(--text-muted); margin-bottom: 2px; }
.summary-card-value { font-size: 20px; font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; }
.summary-card-sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.summary-card.credit-balance .summary-card-value { color: var(--color-primary); }

/* Section titles */
.section-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; margin-top: 16px; }

/* Inline payment form */
.payment-inline-form { background: var(--palette-gray-50); border-radius: 6px; padding: 12px; margin-bottom: 12px; }

/* Hint text */
.hint-text { font-size: 13px; color: var(--text-muted); padding: 8px 0; }
</style>
