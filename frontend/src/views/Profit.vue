<template>
  <div class="profit">
    <h2>利润表</h2>

    <div class="search-panel">
      <label>我方主体：</label>
      <select v-model="companyId" class="input-md" @change="loadTable">
        <option :value="null">全部</option>
        <option v-for="c in companies" :key="c.company_id" :value="c.company_id">
          {{ c.company_name }}
        </option>
      </select>
      <label>收款月份:</label>
      <input id="profit-month-from" v-model="monthFrom" placeholder="YYYY-MM" class="input-sm" />
      <span class="search-sep">→</span>
      <input id="profit-month-to" v-model="monthTo" placeholder="YYYY-MM" class="input-sm" />
      <button class="btn-search" @click="loadTable">查询</button>
      <button class="btn-export" :disabled="!gridReady" @click="exportCSV">导出 CSV</button>
    </div>

    <div ref="gridContainer" class="grid-container">
      <ag-grid-vue
        :rowData="rows"
        :columnDefs="colDefs"
        class="ag-theme-quartz grid"
        :defaultColDef="defaultColDef"
        domLayout="autoHeight"
        :animateRows="true"
        :enableCellTextSelection="true"
        :ensureDomOrder="true"
        :headerHeight="32"
        :rowHeight="30"
        @grid-ready="onGridReady"
        @cell-value-changed="onCellChanged"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import api, { logError } from '../api'
import { useToast } from '../components/AppToast/useToast'

const toast = useToast()

const companyId = ref(null)
const companies = ref([])
const monthFrom = ref(_prevMonths(5))
const monthTo = ref(_currentMonth())
const rows = ref([])
const gridApi = ref(null)
const gridReady = ref(false)

function _currentMonth() {
  const d = new Date()
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
}
function _prevMonths(n) {
  const d = new Date()
  d.setMonth(d.getMonth() - n)
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
}

const defaultColDef = { sortable: true, filter: false, resizable: true, minWidth: 100 }

const colDefs = [
  { field: 'month', headerName: '收款月份', width: 130, pinned: 'left', editable: false,
    cellStyle: p => p.value === '合计' ? { fontWeight: 700 } : {} },
  { field: 'revenue', headerName: '主营业务收入', width: 140, editable: false,
    cellStyle: { textAlign: 'right' },
    valueFormatter: p => p.value != null ? p.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '-' },
  { field: 'cost', headerName: '主营业务成本', width: 140, editable: false,
    cellStyle: { textAlign: 'right' },
    valueFormatter: p => p.value != null ? p.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '-' },
  { field: 'gross_profit', headerName: '营业毛利', width: 130, editable: false,
    cellStyle: { textAlign: 'right', fontWeight: 700 },
    valueFormatter: p => p.value != null ? p.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '-' },
  { field: 'other_income', headerName: '其他业务收入', width: 140, editable: true,
    cellStyle: { textAlign: 'right' },
    cellEditor: 'agNumberCellEditor',
    cellEditorParams: { precision: 2 },
    valueFormatter: p => p.value != null ? p.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '0.00' },
  { field: 'expense', headerName: '期间费用', width: 130, editable: true,
    cellStyle: { textAlign: 'right' },
    cellEditor: 'agNumberCellEditor',
    cellEditorParams: { precision: 2, min: 0 },
    valueFormatter: p => p.value != null ? p.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '0.00' },
  { field: 'net_profit', headerName: '营业利润', width: 130, editable: false,
    cellStyle: p => ({ textAlign: 'right', fontWeight: 700,
      color: p.value > 0 ? 'var(--color-danger)' : p.value < 0 ? 'var(--color-success)' : 'inherit' }),
    valueFormatter: p => p.value != null ? p.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '-' },
]

function onGridReady(params) { gridApi.value = params.api; gridReady.value = true }

async function loadTable() {
  try {
    const r = await api.getProfitTable({
      company_id: companyId.value,
      month_from: monthFrom.value,
      month_to: monthTo.value,
    })
    const data = r.data
    // Single aggregate row + totals row (same data, different label)
    rows.value = [data.rows[0], data.totals]
  } catch (e) { logError('loadProfitTable', e); rows.value = [] }
}

async function onCellChanged(e) {
  const field = e.colDef.field
  if (field !== 'expense' && field !== 'other_income') return
  const row = e.data
  if (!monthFrom.value || !monthTo.value) return
  try {
    await api.saveExpense({
      month_from: monthFrom.value,
      month_to: monthTo.value,
      company_id: companyId.value,
      expense_amount: field === 'expense' ? (e.newValue || 0) : (row.expense || 0),
      other_income: field === 'other_income' ? (e.newValue || 0) : (row.other_income || 0),
    })
    loadTable()
  } catch (e2) { logError('saveExpense', e2); toast.error('保存失败: ' + (e2.response?.data?.detail || e2.message)) }
}

async function loadCompanies() {
  try {
    const r = await api.getCompanies()
    companies.value = r.data.data || []
  } catch (e) { logError('loadCompanies', e) }
}

function exportCSV() {
  if (!gridApi.value || gridApi.value.isDestroyed()) return
  const r = []
  gridApi.value.forEachNodeAfterFilterAndSort(n => r.push(n.data))
  if (!r.length) { alert('当前无数据'); return }
  const header = ['月份', '主营业务收入', '主营业务成本', '营业毛利', '其他业务收入', '期间费用', '营业利润']
  const lines = [header.join(',')]
  r.forEach(row => {
    lines.push([row.month, row.revenue, row.cost, row.gross_profit, row.other_income, row.expense, row.net_profit].join(','))
  })
  const bom = '﻿'
  const blob = new Blob([bom + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'profit.csv'
  a.click(); URL.revokeObjectURL(url)
}

onMounted(() => { loadTable(); loadCompanies() })
</script>

<style scoped>
h2 { margin-bottom: 16px; font-size: 20px; }
.search-panel {
  display: flex; align-items: center; gap: 12px;
  background: var(--bg-card); padding: 12px 16px; border-radius: 8px;
  box-shadow: var(--shadow-card); margin-bottom: 16px; flex-wrap: wrap;
}
.search-panel label { font-size: 13px; color: var(--text-secondary); }
.input-sm { padding: 5px 8px; border: 1px solid var(--border-default); border-radius: 4px; font-size: 13px; width: 100px; background: var(--bg-card); color: var(--text-primary); }
.input-md { padding: 5px 10px; border: 1px solid var(--border-default); border-radius: 4px; font-size: 13px; background: var(--bg-card); color: var(--text-primary); }
.search-sep { color: var(--text-muted); font-size: 13px; }
.btn-search { padding: 6px 16px; background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-export { padding: 6px 14px; background: var(--palette-gray-80); border: 1px solid var(--border-default); border-radius: 6px; cursor: pointer; font-size: 13px; color: var(--text-secondary); }
.grid-container { background: var(--bg-card); border-radius: 8px; box-shadow: var(--shadow-card); padding: 8px; }
.grid { width: 100%; }
</style>
