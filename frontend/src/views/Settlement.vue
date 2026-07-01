<template>
  <div class="settlement">
    <div v-show="!isFullscreen" class="page-header">
      <h2>结算查询</h2>
      <div class="tabs">
        <button :class="{ active: mode === 'income' }" @click="mode = 'income'; search()">收入结算</button>
        <button :class="{ active: mode === 'payment' }" @click="mode = 'payment'; search()">付款结算</button>
      </div>
    </div>

    <div v-show="!isFullscreen" class="search-panel">
      <label for="start-month">开始月份:</label>
      <input id="start-month" v-model="filters.start_month" placeholder="YYYY-MM" class="input-sm" />

      <label for="end-month">结束月份:</label>
      <input id="end-month" v-model="filters.end_month" placeholder="YYYY-MM" class="input-sm" />

      <button class="btn-search" @click="search">查询</button>
      <button class="btn-export" :disabled="!gridReady" @click="exportCSV">导出 CSV</button>
      <button class="btn-export" :disabled="!gridReady" @click="exportFull">全量导出</button>
      <button class="btn-bill" :disabled="!gridReady" @click="showBillDialog = true">导出对账单</button>
    </div>

    <div class="deduction-toolbar">
      <button class="btn-save" @click="saveAll" :disabled="!dedDirty && !splitDirty">保存修改</button>
      <span v-if="dedDirty" class="change-badge">扣除 {{ dedCount }} 处</span>
      <span v-if="splitDirty" class="change-badge">分成 {{ splitCount }} 处</span>
      <span class="toolbar-sep"></span>
      <label class="toggle-label">
        <input type="checkbox" v-model="showDetailCols" />
        显示明细列
      </label>
      <label class="toggle-label" style="margin-left:4px">
        <input type="checkbox" v-model="showLockedOnly" />
        仅锁定
      </label>
      <label class="toggle-label" style="margin-left:4px">
        <input type="checkbox" v-model="showUnlockedOnly" />
        仅无锁定
      </label>
      <span class="toolbar-sep"></span>
      <input v-model="quickFilterText" class="input-sm quick-filter" placeholder="全局筛选..." style="width:160px" />
      <span class="toolbar-hint">双击可编辑单元格 · Alt+滑轮横向滚动</span>
      <button class="btn-fullscreen" @click="toggleFullscreen" :title="isFullscreen ? '退出全屏' : '全屏'">
        {{ isFullscreen ? '✕ 退出' : '⛶ 全屏' }}
      </button>
    </div>
    <div v-if="saveMsg" :class="['save-toast', saveMsgType === 'error' ? 'toast-error' : 'toast-success']">{{ saveMsg }}</div>

    <div ref="gridContainer" :class="['grid-container', { fullscreen: isFullscreen }]">
      <!-- 全屏浮动工具栏 -->
      <div v-if="isFullscreen" class="fs-toolbar">
        <span class="fs-title">{{ mode === 'income' ? '收入结算' : '付款结算' }}</span>
        <input v-model="quickFilterText" class="input-sm" placeholder="全局筛选..." style="width:200px" />
        <span class="fs-count" v-if="summary.count">共 {{ summary.count }} 条</span>
        <button class="btn-save" @click="saveAll" :disabled="!dedDirty && !splitDirty">保存修改</button>
        <span v-if="dedDirty" class="change-badge">扣除 {{ dedCount }}</span>
        <span v-if="splitDirty" class="change-badge">分成 {{ splitCount }}</span>
        <label class="toggle-label">
          <input type="checkbox" v-model="showDetailCols" />
          明细列
        </label>
        <label class="toggle-label" style="margin-left:4px">
          <input type="checkbox" v-model="showLockedOnly" />
          仅锁定
        </label>
        <label class="toggle-label" style="margin-left:4px">
          <input type="checkbox" v-model="showUnlockedOnly" />
          仅无锁定
        </label>
        <button class="btn-fullscreen" @click="toggleFullscreen">✕ 退出全屏 (ESC)</button>
      </div>
      <ag-grid-vue
        v-if="mode === 'income'"
        :rowData="incomeData"
        :columnDefs="incomeCols"
        class="ag-theme-quartz grid"
        :defaultColDef="defaultColDef"
        :enableCellTextSelection="true"
        :headerHeight="32"
        :rowHeight="30"
        :quickFilterText="quickFilterText"
        @grid-ready="onIncomeGridReady"
        @cell-value-changed="onCellChanged"
        @cell-editing-stopped="onCellEditingStopped"
      />
      <ag-grid-vue
        v-if="mode === 'payment'"
        :rowData="paymentData"
        :columnDefs="paymentCols"
        class="ag-theme-quartz grid"
        :defaultColDef="defaultColDef"
        :enableCellTextSelection="true"
        :headerHeight="32"
        :rowHeight="30"
        :quickFilterText="quickFilterText"
        @grid-ready="onPaymentGridReady"
        @cell-value-changed="onCellChanged"
        @cell-editing-stopped="onCellEditingStopped"
      />
      <!-- 全屏浮动汇总 -->
      <div v-if="isFullscreen && summary.count > 0" class="fs-summary">
        <div class="summary-cards">
          <div class="s-card">
            <span class="s-label">真实流水</span>
            <span class="s-value">{{ formatMoney(summary.real_revenue) }}</span>
          </div>
          <div class="s-card">
            <span class="s-label">扣除合计</span>
            <span class="s-value s-value-red">{{ formatMoney(summary.deductions) }}</span>
          </div>
          <div class="s-card s-card-total">
            <span class="s-label">结算金额合计</span>
            <span class="s-value s-value-green">{{ formatMoney(summary.settlement_amount) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="summary.count > 0 && !isFullscreen" class="summary-bar">
      <div class="summary-cards">
        <div class="s-card">
          <span class="s-label">真实流水</span>
          <span class="s-value">{{ formatMoney(summary.real_revenue) }}</span>
        </div>
        <div class="s-card">
          <span class="s-label">扣除合计</span>
          <span class="s-value s-value-red">{{ formatMoney(summary.deductions) }}</span>
        </div>
        <div class="s-card s-card-total">
          <span class="s-label">结算金额合计</span>
          <span class="s-value s-value-green">{{ formatMoney(summary.settlement_amount) }}</span>
        </div>
      </div>
      <span class="summary-count">共 {{ summary.count }} 条记录</span>
    </div>

    <!-- Bill Export Dialog -->
    <div v-if="showBillDialog" class="modal-overlay" @click.self="showBillDialog = false">
      <div class="modal-dialog">
        <h3>导出对账单</h3>
        <p class="modal-hint">选择结算双方的主体信息，将根据当前查询结果生成对账单。</p>
        <div class="form-row autocomplete-row">
          <label for="bill-party-a">甲方主体：</label>
          <div class="autocomplete-wrapper">
            <input
              id="bill-party-a"
              v-model="billPartyAName"
              class="input-md"
              placeholder="输入名称搜索匹配..."
              autocomplete="off"
              @input="partyAShowDropdown = true"
              @focus="partyAShowDropdown = true"
              @blur="onPartyABlur"
              @keydown.down.prevent="aHighlight('down')"
              @keydown.up.prevent="aHighlight('up')"
              @keydown.enter.prevent="aSelectHighlighted"
            />
            <ul v-if="partyAShowDropdown && filteredPartyA.length" class="autocomplete-dropdown">
              <li
                v-for="(p, i) in filteredPartyA"
                :key="p.id"
                :class="{ highlighted: i === aHighlightIdx }"
                @mousedown="aSelect(p)"
              >
                {{ p.name }}
                <span class="party-type-tag">{{ PARTY_TYPE_LABEL[p.party_type] || p.party_type }}</span>
              </li>
            </ul>
          </div>
          <span v-if="billPartyA" class="selected-badge">✔ 已选</span>
        </div>
        <div class="form-row autocomplete-row">
          <label for="bill-party-b">乙方主体：</label>
          <div class="autocomplete-wrapper">
            <input
              id="bill-party-b"
              v-model="billPartyBName"
              class="input-md"
              placeholder="输入名称搜索匹配..."
              autocomplete="off"
              @input="partyBShowDropdown = true"
              @focus="partyBShowDropdown = true"
              @blur="onPartyBBlur"
              @keydown.down.prevent="bHighlight('down')"
              @keydown.up.prevent="bHighlight('up')"
              @keydown.enter.prevent="bSelectHighlighted"
            />
            <ul v-if="partyBShowDropdown && filteredPartyB.length" class="autocomplete-dropdown">
              <li
                v-for="(p, i) in filteredPartyB"
                :key="p.id"
                :class="{ highlighted: i === bHighlightIdx }"
                @mousedown="bSelect(p)"
              >
                {{ p.name }}
                <span class="party-type-tag">{{ PARTY_TYPE_LABEL[p.party_type] || p.party_type }}</span>
              </li>
            </ul>
          </div>
          <span v-if="billPartyB" class="selected-badge">✔ 已选</span>
        </div>
        <div class="form-row">
          <label for="bill-template">对账模板：</label>
          <select id="bill-template" v-model="selectedTemplateId" class="input-md">
            <option :value="null">默认模板（系统生成）</option>
            <option v-for="t in billTemplates" :key="t.id" :value="t.id">
              {{ t.name }}{{ t.is_default ? ' (默认)' : '' }}
            </option>
          </select>
          <span v-if="!billTemplates.length" class="tpl-hint">暂无自定义模板，可前往"基础数据 → 对账模板"上传</span>
        </div>
        <div class="modal-actions">
          <button class="btn-search" @click="doExportBill" :disabled="!billPartyA || !billPartyB">确认导出</button>
          <button class="btn-export" @click="showBillDialog = false">取消</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import api, { logError } from '../api'
import { useGames } from '../composables/useSharedData.js'
const { gamesMap, load: loadGamesMap } = useGames()
const mode = ref('income')
const showDetailCols = ref(true)
const showLockedOnly = ref(false)
const showUnlockedOnly = ref(false)
const saveMsg = ref('')
const saveMsgType = ref('success') // 'success' | 'error'
const deductionChanges = reactive({})
const dedDirty = computed(() => Object.keys(deductionChanges).length > 0)
const dedCount = computed(() => Object.keys(deductionChanges).length)
const splitChanges = reactive({})
const splitDirty = computed(() => Object.keys(splitChanges).length > 0)
const splitCount = computed(() => Object.keys(splitChanges).length)
const incomeData = ref([])
const incomeDataFull = ref([])   // unfiltered data (preserved for locked filter toggle)
const paymentData = ref([])
const paymentDataFull = ref([])  // unfiltered data (preserved for locked filter toggle)
const totalCount = ref(null)

// Apply locked/unlocked filter on top of fetched data
function _filterLocked(data) {
  if (!data) return data
  if (showLockedOnly.value) return data.filter(r => r.locked_settlement_amount != null || r.locked_real_revenue != null)
  if (showUnlockedOnly.value) return data.filter(r => r.locked_settlement_amount == null && r.locked_real_revenue == null)
  return data
}

watch(showLockedOnly, (v) => {
  if (v) showUnlockedOnly.value = false
  incomeData.value = _filterLocked(incomeDataFull.value)
  paymentData.value = _filterLocked(paymentDataFull.value)
  nextTick(() => updateSummary())
})

watch(showUnlockedOnly, (v) => {
  if (v) showLockedOnly.value = false
  incomeData.value = _filterLocked(incomeDataFull.value)
  paymentData.value = _filterLocked(paymentDataFull.value)
  nextTick(() => updateSummary())
})

// 汇总信息
const summary = reactive({ real_revenue: 0, deductions: 0, settlement_amount: 0, count: 0 })
const formatMoney = (v) => {
  if (v == null || isNaN(v)) return '¥0.00'
  return '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function debounce(fn, delay) {
  let timer = null
  return function (...args) { clearTimeout(timer); timer = setTimeout(() => fn.apply(this, args), delay) }
}
const debouncedUpdateSummary = debounce(() => updateSummary(), 100)

function updateSummary() {
  const api = mode.value === 'income' ? incomeGridApi.value : paymentGridApi.value
  if (!api || api.isDestroyed()) return
  let real = 0, ded = 0, stl = 0, cnt = 0
  api.forEachNodeAfterFilterAndSort(node => {
    real += Number(node.data.real_revenue || 0)
    ded += Number(node.data.total_deductions || 0)
    stl += Number(node.data.settlement_amount || 0)
    cnt++
  })
  summary.real_revenue = real
  summary.deductions = ded
  summary.settlement_amount = stl
  summary.count = cnt
  totalCount.value = cnt
}

// Bill export dialog
const showBillDialog = ref(false)
const billPartyA = ref('')
const billPartyB = ref('')
const billPartyAName = ref('')
const billPartyBName = ref('')
const partyAShowDropdown = ref(false)
const partyBShowDropdown = ref(false)
const aHighlightIdx = ref(-1)
const bHighlightIdx = ref(-1)
const partyInfoList = ref([])
const billTemplates = ref([])
const selectedTemplateId = ref(null)
const PARTY_TYPE_LABEL = { our_company: '我方公司', channel: '渠道', publisher: '研发' }

// ── Party autocomplete ──

const filteredPartyA = computed(() => {
  const q = (billPartyAName.value || '').toLowerCase().trim()
  if (!q) return partyInfoList.value
  return partyInfoList.value.filter(p => p.name.toLowerCase().includes(q))
})
const filteredPartyB = computed(() => {
  const q = (billPartyBName.value || '').toLowerCase().trim()
  if (!q) return partyInfoList.value
  return partyInfoList.value.filter(p => p.name.toLowerCase().includes(q))
})
function aSelect(p) {
  billPartyA.value = p.id
  billPartyAName.value = p.name
  partyAShowDropdown.value = false
  aHighlightIdx.value = -1
}
function bSelect(p) {
  billPartyB.value = p.id
  billPartyBName.value = p.name
  partyBShowDropdown.value = false
  bHighlightIdx.value = -1
}
function aHighlight(dir) {
  const max = filteredPartyA.value.length - 1
  if (max < 0) return
  aHighlightIdx.value = dir === 'down'
    ? (aHighlightIdx.value < max ? aHighlightIdx.value + 1 : 0)
    : (aHighlightIdx.value > 0 ? aHighlightIdx.value - 1 : max)
}
function bHighlight(dir) {
  const max = filteredPartyB.value.length - 1
  if (max < 0) return
  bHighlightIdx.value = dir === 'down'
    ? (bHighlightIdx.value < max ? bHighlightIdx.value + 1 : 0)
    : (bHighlightIdx.value > 0 ? bHighlightIdx.value - 1 : max)
}
function aSelectHighlighted() {
  const idx = aHighlightIdx.value
  if (idx >= 0 && idx < filteredPartyA.value.length) aSelect(filteredPartyA.value[idx])
}
function bSelectHighlighted() {
  const idx = bHighlightIdx.value
  if (idx >= 0 && idx < filteredPartyB.value.length) bSelect(filteredPartyB.value[idx])
}
let aBlurTimer = null
let bBlurTimer = null
function onPartyABlur() {
  clearTimeout(aBlurTimer)
  aBlurTimer = setTimeout(() => { partyAShowDropdown.value = false }, 200)
}
function onPartyBBlur() {
  clearTimeout(bBlurTimer)
  bBlurTimer = setTimeout(() => { partyBShowDropdown.value = false }, 200)
}

const incomeGridApi = ref(null)
const paymentGridApi = ref(null)
const gridContainer = ref(null)
const gridReady = ref(false)
const isFullscreen = ref(false)
const quickFilterText = ref('')

function onIncomeGridReady(params) {
  incomeGridApi.value = params.api
  params.api.addEventListener('modelUpdated', debouncedUpdateSummary)
  gridReady.value = true
  updateSummary()
}
function onPaymentGridReady(params) {
  paymentGridApi.value = params.api
  params.api.addEventListener('modelUpdated', debouncedUpdateSummary)
  gridReady.value = true
  updateSummary()
}

watch(mode, () => {
  gridReady.value = false
  summary.count = 0
  summary.real_revenue = 0
  summary.deductions = 0
  summary.settlement_amount = 0
})

function _prevMonth() {
  const d = new Date()
  const m = new Date(d.getFullYear(), d.getMonth() - 1, 1)
  return m.getFullYear() + '-' + String(m.getMonth() + 1).padStart(2, '0')
}
const filters = ref({ start_month: _prevMonth(), end_month: _prevMonth() })

const defaultColDef = {
  sortable: true,
  filter: false,
  resizable: true,
  minWidth: 90,
}

const _detailFields = ['vouchers', 'test', 'welfare', 'bad_debt', 'split_rate', 'channel_fee_rate', 'tax_rate']
function _hideDetail(cols) {
  const show = showDetailCols.value
  return cols.map(c => ({ ...c, hide: c.field && _detailFields.includes(c.field) ? !show : c.hide }))
}

const _incomeCols = [
  { field: 'rowNo', headerName: '#', width: 50, pinned: 'left', sortable: false, filter: false,
    valueFormatter: p => (p.node?.rowIndex ?? 0) + 1,
    cellStyle: { color: 'var(--text-light)', backgroundColor: 'var(--palette-gray-50)' } },
  { field: 'channel_name', headerName: '收入方名称', width: 130, pinned: 'left', filter: true },
  { field: 'project_code', headerName: '项目编号', width: 120, filter: true },
  { field: 'project_name', headerName: '项目名称', width: 150, filter: true },
  { field: 'company_name', headerName: '我方公司', width: 140, filter: true },
  { field: 'game_id', headerName: '游戏编号', width: 100, pinned: 'left', filter: true },
  { field: 'game_name', headerName: '游戏名称', width: 140, editable: false, filter: true },
  { field: 'month', headerName: '月份', width: 90, filter: true },
  { field: 'raw_revenue', headerName: '原始流水', width: 130, filter: true,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '-',
    cellStyle: { textAlign: 'right' } },
  { field: 'real_revenue', headerName: '真实流水', width: 130, editable: true, filter: true,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '-',
    cellStyle: { textAlign: 'right' },
    cellClassRules: { 'cell-locked': p => p.data && p.data.locked_real_revenue != null },
    valueParser: p => { if (!p.newValue || !String(p.newValue).trim()) return null; const n = parseFloat(String(p.newValue).replace(/,/g, '')); return isNaN(n) ? null : n } },
  { field: 'vouchers', headerName: '代金券', width: 100, editable: true,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '0',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); return isNaN(v) ? 0 : v } },
  { field: 'test', headerName: '测试', width: 90, editable: true,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '0',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); return isNaN(v) ? 0 : v } },
  { field: 'welfare', headerName: '福利币', width: 90, editable: true,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '0',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); return isNaN(v) ? 0 : v } },
  { field: 'bad_debt', headerName: '坏账', width: 90, editable: true,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '0',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); return isNaN(v) ? 0 : v } },
  { field: 'total_deductions', headerName: '扣除合计', width: 110, editable: false,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '-',
    cellStyle: p => ({ textAlign: 'right', color: p.value > 0 ? '#c00' : '#999' }) },
  { field: 'split_rate', headerName: '分成比例', width: 100, editable: true,
    valueFormatter: p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '-',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); if (isNaN(v)) return 0; if (p.oldValue != null && Math.abs(v - p.oldValue) < 0.00001) return p.oldValue; return v / 100 } },
  { field: 'channel_fee_rate', headerName: '通道费率', width: 100, editable: true,
    valueFormatter: p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '-',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); if (isNaN(v)) return 0; if (p.oldValue != null && Math.abs(v - p.oldValue) < 0.00001) return p.oldValue; return v / 100 } },
  { field: 'tax_rate', headerName: '税率', width: 90, editable: true,
    valueFormatter: p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '-',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); if (isNaN(v)) return 0; if (p.oldValue != null && Math.abs(v - p.oldValue) < 0.00001) return p.oldValue; return v / 100 } },
  { headerName: '分成总比', width: 100,
    valueGetter: p => { const d = p.data; if (!d) return 0; return (Number(d.split_rate||0)) * (1 - Number(d.channel_fee_rate||0)) * (1 - Number(d.tax_rate||0)) },
    valueFormatter: p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '-',
    cellStyle: { textAlign: 'right' },
    editable: false },
  { field: 'settlement_amount', headerName: '结算金额', width: 130, editable: true, filter: true,
    cellStyle: p => p.value > 0 ? { fontWeight: 700, color: '#27ae60', textAlign: 'right' } : { textAlign: 'right' },
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '-',
    cellClassRules: { 'cell-locked': p => p.data && p.data.locked_settlement_amount != null },
    valueParser: p => { if (!p.newValue || !String(p.newValue).trim()) return null; const n = parseFloat(String(p.newValue).replace(/,/g, '')); return isNaN(n) ? null : n } },
]

const incomeCols = computed(() => _hideDetail(_incomeCols))

const _paymentCols = [
  { field: 'rowNo', headerName: '#', width: 50, pinned: 'left', sortable: false, filter: false,
    valueFormatter: p => (p.node?.rowIndex ?? 0) + 1,
    cellStyle: { color: 'var(--text-light)', backgroundColor: 'var(--palette-gray-50)' } },
  { field: 'publisher_name', headerName: '付款方名称', width: 160, pinned: 'left', filter: true },
  { field: 'project_code', headerName: '项目编号', width: 120, filter: true },
  { field: 'project_name', headerName: '项目名称', width: 150, filter: true },
  { field: 'company_name', headerName: '我方公司', width: 140, filter: true },
  { field: 'game_id', headerName: '游戏编号', width: 100, pinned: 'left', filter: true },
  { field: 'game_name', headerName: '游戏名称', width: 140, editable: false, filter: true },
  { field: 'month', headerName: '月份', width: 90, filter: true },
  { field: 'raw_revenue', headerName: '原始流水', width: 130, filter: true,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '-',
    cellStyle: { textAlign: 'right' } },
  { field: 'real_revenue', headerName: '真实流水', width: 130, editable: true, filter: true,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '-',
    cellStyle: { textAlign: 'right' },
    cellClassRules: { 'cell-locked': p => p.data && p.data.locked_real_revenue != null },
    valueParser: p => { if (!p.newValue || !String(p.newValue).trim()) return null; const n = parseFloat(String(p.newValue).replace(/,/g, '')); return isNaN(n) ? null : n } },
  { field: 'vouchers', headerName: '代金券', width: 100,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '0',
    cellStyle: { textAlign: 'right' }, editable: false },
  { field: 'test', headerName: '测试', width: 90,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '0',
    cellStyle: { textAlign: 'right' }, editable: false },
  { field: 'welfare', headerName: '福利币', width: 90,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '0',
    cellStyle: { textAlign: 'right' }, editable: false },
  { field: 'bad_debt', headerName: '坏账', width: 90,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '0',
    cellStyle: { textAlign: 'right' }, editable: false },
  { field: 'total_deductions', headerName: '扣除合计', width: 110, editable: false,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '-',
    cellStyle: p => ({ textAlign: 'right', color: p.value > 0 ? '#c00' : '#999' }) },
  { field: 'split_rate', headerName: '分成比例', width: 100, editable: true,
    valueFormatter: p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '-',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); if (isNaN(v)) return 0; if (p.oldValue != null && Math.abs(v - p.oldValue) < 0.00001) return p.oldValue; return v / 100 } },
  { field: 'channel_fee_rate', headerName: '渠道费率', width: 100, editable: true,
    valueFormatter: p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '-',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); if (isNaN(v)) return 0; if (p.oldValue != null && Math.abs(v - p.oldValue) < 0.00001) return p.oldValue; return v / 100 } },
  { field: 'tax_rate', headerName: '税率', width: 90, editable: true,
    valueFormatter: p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '-',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); if (isNaN(v)) return 0; if (p.oldValue != null && Math.abs(v - p.oldValue) < 0.00001) return p.oldValue; return v / 100 } },
  { headerName: '分成总比', width: 100,
    valueGetter: p => { const d = p.data; if (!d) return 0; return (Number(d.split_rate||0)) * (1 - Number(d.channel_fee_rate||0)) * (1 - Number(d.tax_rate||0)) },
    valueFormatter: p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '-',
    cellStyle: { textAlign: 'right' },
    editable: false },
  { field: 'fixed_fee', headerName: '固定费用', width: 110, editable: true,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '0',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); return isNaN(v) ? 0 : v } },
  { field: 'settlement_amount', headerName: '结算金额', width: 130, editable: true, filter: true,
    cellStyle: p => p.value > 0 ? { fontWeight: 700, color: '#27ae60', textAlign: 'right' } : { textAlign: 'right' },
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '-',
    cellClassRules: { 'cell-locked': p => p.data && p.data.locked_settlement_amount != null },
    valueParser: p => { if (!p.newValue || !String(p.newValue).trim()) return null; const n = parseFloat(String(p.newValue).replace(/,/g, '')); return isNaN(n) ? null : n } },
]

const paymentCols = computed(() => _hideDetail(_paymentCols))

async function search() {
  const currentApi = mode.value === 'income' ? incomeGridApi.value : paymentGridApi.value
  const savedModel = (currentApi && !currentApi.isDestroyed()) ? currentApi.getFilterModel() : null

  const params = {}
  if (filters.value.start_month) params.start_month = filters.value.start_month
  if (filters.value.end_month) params.end_month = filters.value.end_month

  if (mode.value === 'income') {
    const r = await api.getIncomeSettlement(params)
    incomeDataFull.value = r.data.data
    incomeData.value = _filterLocked(r.data.data)
  } else {
    const r = await api.getPaymentSettlement(params)
    paymentDataFull.value = r.data.data
    paymentData.value = _filterLocked(r.data.data)
  }

  nextTick(() => {
    const api = mode.value === 'income' ? incomeGridApi.value : paymentGridApi.value
    if (savedModel && Object.keys(savedModel).length > 0 && api && !api.isDestroyed()) {
      // Strip month filter — date range inputs already control month filtering
      const clean = { ...savedModel }
      delete clean.month
      if (Object.keys(clean).length > 0) api.setFilterModel(clean)
    }
    updateSummary()
  })
}

function _pct(v) { if (v == null) return ''; return (Number(v) * 100).toFixed(2) + '%' }
function _num(v) { if (v == null) return ''; return Number(v).toFixed(2) }

function exportCSV() {
  const api_ = mode.value === 'income' ? incomeGridApi.value : paymentGridApi.value
  if (!api_ || api_.isDestroyed()) return
  const rows = []
  api_.forEachNodeAfterFilterAndSort(n => rows.push(n.data))
  if (!rows.length) { alert('当前筛选条件下无数据可导出'); return }

  const lines = []
  if (mode.value === 'income') {
    lines.push(['收入方名称', '项目编号', '项目名称', '我方公司', '游戏编号', '游戏名称',
      '月份', '原始流水', '真实流水', '代金券', '测试', '福利币', '坏账',
      '扣除合计', '分成比例', '通道费率', '税率', '结算金额'].join(','))
    for (const r of rows) {
      lines.push([r.channel_name, csv_escape(r.project_code), csv_escape(r.project_name), csv_escape(r.company_name),
        r.game_id, csv_escape(r.game_name), r.month,
        _num(r.raw_revenue), _num(r.real_revenue), _num(r.vouchers), _num(r.test), _num(r.welfare), _num(r.bad_debt),
        _num(r.total_deductions), _pct(r.split_rate), _pct(r.channel_fee_rate), _pct(r.tax_rate),
        _num(r.settlement_amount)].join(','))
    }
  } else {
    lines.push(['付款方名称', '项目编号', '项目名称', '我方公司', '游戏编号', '游戏名称',
      '月份', '原始流水', '真实流水', '代金券', '测试', '福利币', '坏账',
      '扣除合计', '固定费用', '分成比例', '通道费率', '税率', '结算金额'].join(','))
    for (const r of rows) {
      lines.push([r.publisher_name, csv_escape(r.project_code), csv_escape(r.project_name), csv_escape(r.company_name),
        r.game_id, csv_escape(r.game_name), r.month,
        _num(r.raw_revenue), _num(r.real_revenue), _num(r.vouchers), _num(r.test), _num(r.welfare), _num(r.bad_debt),
        _num(r.total_deductions), _num(r.fixed_fee), _pct(r.split_rate), _pct(r.channel_fee_rate), _pct(r.tax_rate),
        _num(r.settlement_amount)].join(','))
    }
  }

  const bom = '﻿'
  const blob = new Blob([bom + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = `${mode.value}_settlement.csv`
  a.click(); URL.revokeObjectURL(url)
}

function csv_escape(v) { if (!v) return ''; const s = String(v); return s.includes(',') || s.includes('"') || s.includes('\n') ? '"' + s.replace(/"/g, '""') + '"' : s }

async function exportFull() {
  const params = { mode: mode.value }
  if (filters.value.start_month) params.start_month = filters.value.start_month
  if (filters.value.end_month) params.end_month = filters.value.end_month

  try {
    const r = await api.exportFullCsv(params)
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a')
    const sm = filters.value.start_month || 'all'
    const em = filters.value.end_month || 'all'
    a.href = url
    a.download = `全量导出_${mode.value}_${sm}_${em}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('全量导出失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function doExportBill() {
  // Validate that parties are selected from autocomplete
  if (!billPartyA.value || !billPartyAName.value.trim()) {
    alert('请选择一个有效的甲方主体 — 在输入框内搜索并从匹配列表中选择')
    return
  }
  if (!billPartyB.value || !billPartyBName.value.trim()) {
    alert('请选择一个有效的乙方主体 — 在输入框内搜索并从匹配列表中选择')
    return
  }
  // Extra safety: verify the selected ID actually exists
  const aValid = partyInfoList.value.some(p => p.id === billPartyA.value)
  const bValid = partyInfoList.value.some(p => p.id === billPartyB.value)
  if (!aValid || !bValid) {
    alert('主体选择无效，请从匹配列表中选择已有的主体信息')
    return
  }

  try {
    // Collect grid-filtered rows so export respects AG Grid filters
    const api_ = mode.value === 'income' ? incomeGridApi.value : paymentGridApi.value
    const rows = []
    if (api_ && !api_.isDestroyed()) {
      api_.forEachNodeAfterFilterAndSort(n => rows.push(n.data))
    }
    const sm = filters.value.start_month
    const em = filters.value.end_month
    const period = sm && em && sm !== em ? `${sm} ~ ${em}` : (sm || em || '全部')

    const r = await api.exportBill({
      mode: mode.value,
      party_id_a: billPartyA.value,
      party_id_b: billPartyB.value,
      start_month: filters.value.start_month || undefined,
      end_month: filters.value.end_month || undefined,
      rows,
      template_id: selectedTemplateId.value || undefined,
    })
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `${mode.value === 'income' ? '收入' : '付款'}结算对账单_${period}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    showBillDialog.value = false
  } catch (e) {
    alert('导出对账单失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function loadPartyInfo() {
  try {
    const r = await api.getPartyInfo()
    partyInfoList.value = r.data.data
  } catch (e) { logError('loadPartyInfo', e) }
}

async function loadBillTemplates() {
  try {
    const r = await api.getBillTemplates({ bill_type: mode.value })
    billTemplates.value = r.data.data || []
  } catch (e) { logError('loadBillTemplates', e) }
}

// Load templates when bill dialog opens
watch(showBillDialog, (v) => {
  if (v) {
    selectedTemplateId.value = null
    billPartyA.value = ''
    billPartyB.value = ''
    billPartyAName.value = ''
    billPartyBName.value = ''
    partyAShowDropdown.value = false
    partyBShowDropdown.value = false
    aHighlightIdx.value = -1
    bHighlightIdx.value = -1
    loadBillTemplates()
  }
})

// When user manually edits party name (not via dropdown selection), clear the stored ID
watch(billPartyAName, () => {
  if (!billPartyAName.value) billPartyA.value = ''
})
watch(billPartyBName, () => {
  if (!billPartyBName.value) billPartyB.value = ''
})

async function onCellChanged(event) {
  const row = event.data
  const field = event.colDef.field
  // Auto-fill game_name when game_id changes
  if (field === 'game_id' && row.game_id) {
    if (gamesMap.value[row.game_id]) {
      row.game_name = gamesMap.value[row.game_id]
      event.api.refreshCells({ rowNodes: [event.node], columns: ['game_name'] })
    }
  }

  if (['vouchers', 'test', 'welfare', 'bad_debt'].includes(field)) {
    const key = `${row.channel_name}|${row.game_id}|${row.month}`
    deductionChanges[key] = {
      channel_name: row.channel_name,
      game_id: row.game_id,
      month: row.month,
      vouchers: row.vouchers ?? 0,
      test: row.test ?? 0,
      welfare: row.welfare ?? 0,
      bad_debt: row.bad_debt ?? 0,
    }
    updateSummary()
  } else if (['split_rate', 'channel_fee_rate', 'tax_rate', 'fixed_fee'].includes(field)) {
    if (mode.value === 'income') {
      const key = `inc:${row.channel_name}|${row.game_id}`
      splitChanges[key] = {
        channel_name: row.channel_name,
        game_id: row.game_id,
        split_rate: row.split_rate,
        channel_fee_rate: row.channel_fee_rate,
        tax_rate: row.tax_rate,
        effective_from: row.effective_from || (row.month ? row.month + '-01' : null),
        effective_to: row.effective_to || null,
      }
    } else {
      const key = `pay:${row.publisher_name}|${row.game_id}`
      splitChanges[key] = {
        publisher_name: row.publisher_name,
        game_id: row.game_id,
        split_rate: row.split_rate,
        channel_fee_rate: row.channel_fee_rate,
        tax_rate: row.tax_rate,
        fixed_fee: row.fixed_fee,
        effective_from: row.effective_from || (row.month ? row.month + '-01' : null),
        effective_to: row.effective_to || null,
      }
    }
  }
}

async function onCellEditingStopped(event) {
  const field = event.colDef.field
  if (field !== 'real_revenue' && field !== 'settlement_amount') return

  const row = event.data
  const val = row[field]
  const unlock = val === null || val === undefined || String(val).trim() === ''
  const payload = {
    game_id: row.game_id,
    month: row.month,
    field: field,
    value: unlock ? '=' : String(val),
    channel_id: mode.value === 'income' ? (row.channel_id || 0) : 0,
    publisher_name: mode.value === 'income' ? '' : (row.publisher_name || ''),
  }
  try {
    const r = await api.lockSettlement(payload)
    if (r.data.status === 'unlocked') {
      row[field] = r.data.formula_value
      row['locked_' + field] = null
      _showSaveMsg('已解锁，恢复公式计算值')
    } else {
      row['locked_' + field] = r.data.value
      _showSaveMsg('已锁定')
    }
    event.api.redrawRows({ rowNodes: [event.node] })
    updateSummary()
  } catch (e) {
    row['locked_' + field] = row['locked_' + field] || null
    const detail = e.response?.data?.detail
    const msg = detail ? (typeof detail === 'string' ? detail : JSON.stringify(detail)) : e.message
    _showSaveMsg('锁定失败: ' + msg, 'error')
    event.api.redrawRows({ rowNodes: [event.node] })
  }
}

let saveTimer = null
function _showSaveMsg(msg, type = 'success') {
  saveMsg.value = msg
  saveMsgType.value = type
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { saveMsg.value = '' }, 3000)
}

async function saveAll() {
  const dedUpdates = Object.values(deductionChanges)
  const splitUpdates = Object.values(splitChanges)
  try {
    if (dedUpdates.length > 0) {
      await api.batchDeductions(dedUpdates)
      Object.keys(deductionChanges).forEach(k => delete deductionChanges[k])
    }
    if (splitUpdates.length > 0) {
      if (mode.value === 'income') await api.batchIncomeSplitConfig(splitUpdates)
      else await api.batchPaymentSplitConfig(splitUpdates)
      Object.keys(splitChanges).forEach(k => delete splitChanges[k])
    }
    await search()
    _showSaveMsg('保存成功')
  } catch (e) {
    const detail = e.response?.data?.detail
    const msg = detail ? (typeof detail === 'string' ? detail : JSON.stringify(detail)) : e.message
    _showSaveMsg('保存失败: ' + msg, 'error')
  }
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
  nextTick(() => {
    const api = mode.value === 'income' ? incomeGridApi.value : paymentGridApi.value
    if (api && !api.isDestroyed()) api.sizeColumnsToFit()
  })
}

function onKeydown(e) {
  if (e.key === 'Escape' && isFullscreen.value) {
    toggleFullscreen()
    return
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    if (dedDirty.value || splitDirty.value) saveAll()
  }
}

onMounted(() => { document.addEventListener('keydown', onKeydown); search(); loadPartyInfo(); loadGamesMap() })
onUnmounted(() => { document.removeEventListener('keydown', onKeydown) })
</script>

<style scoped>
/* ── 页面头部：标题 + Tab 同行 ── */
.page-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px;
}
h2 { font-size: 20px; margin: 0; }
.tabs { display: flex; gap: 8px; margin: 0; }
.tabs button {
  padding: 6px 16px; border: 1px solid var(--border-default); border-radius: 6px;
  background: var(--bg-card); cursor: pointer; font-size: 13px; color: var(--text-secondary);
}
.tabs button.active { background: var(--color-primary); color: var(--text-on-primary); border-color: var(--color-primary); }
.search-panel {
  display: flex; align-items: center; gap: 10px;
  background: var(--bg-card); padding: 8px 14px; border-radius: 8px;
  box-shadow: var(--shadow-card); margin-bottom: 10px; flex-wrap: wrap;
}
.search-panel label { font-size: 13px; color: var(--text-secondary); }
.input-sm { padding: 5px 8px; border: 1px solid var(--border-default); border-radius: 4px; font-size: 13px; width: 120px; background: var(--bg-card); color: var(--text-primary); }
.btn-search { padding: 6px 16px; background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-export { padding: 6px 14px; background: var(--palette-gray-80); border: 1px solid var(--border-default); border-radius: 6px; cursor: pointer; font-size: 13px; color: var(--text-secondary); }
.btn-bill { padding: 6px 14px; background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-bill:disabled { background: var(--text-light); cursor: not-allowed; }
.grid-container {
  background: var(--bg-card); border-radius: 8px; box-shadow: var(--shadow-card); padding: 8px;
  height: calc(100vh - 230px); min-height: 400px;
  position: relative;
}
/* 全屏模式 */
.grid-container.fullscreen {
  position: fixed; inset: 0; z-index: 1000;
  border-radius: 0; padding: 0;
  height: 100vh; min-height: auto;
}
.fs-toolbar {
  position: absolute; top: 0; left: 0; right: 0; z-index: 10;
  display: flex; align-items: center; gap: 10px;
  padding: 8px 16px;
  background: var(--bg-card); border-bottom: 1px solid var(--border-default);
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.fs-title { font-size: 16px; font-weight: 700; color: var(--text-primary); margin-right: 8px; }
.fs-count { font-size: 13px; color: var(--text-muted); }
.fs-summary {
  position: absolute; bottom: 0; left: 0; right: 0; z-index: 10;
  display: flex; align-items: center; justify-content: flex-start;
  padding: 5px 14px;
  background: var(--bg-card); border-top: 1px solid var(--border-default);
  box-shadow: 0 -1px 4px rgba(0,0,0,0.08);
}
.fs-summary .summary-cards { display: flex; gap: 16px; }
.fs-summary .s-card {
  display: flex; flex-direction: column; gap: 1px; min-width: 100px;
  padding: 0 12px 0 0; border-right: 1px solid var(--border-light);
}
.fs-summary .s-card:last-child { border-right: none; }
.fs-summary .s-label { font-size: 10px; }
.fs-summary .s-value { font-size: 13px; }
.grid-container.fullscreen .grid {
  position: absolute;
  top: 46px;
  bottom: 38px;
  left: 0;
  right: 0;
  width: auto;
  height: auto;
}
.btn-fullscreen {
  padding: 5px 12px; border: 1px solid var(--border-default); border-radius: 6px;
  background: var(--bg-card); cursor: pointer; font-size: 13px; color: var(--text-secondary);
  white-space: nowrap;
}
.btn-fullscreen:hover { background: var(--palette-gray-80); }
.quick-filter {
  background: var(--bg-card); color: var(--text-primary);
  border: 1px solid var(--border-default);
}
.quick-filter::placeholder { color: var(--text-light); }
.grid { width: 100%; height: 100%; }
:deep(.ag-cell) { border-right: 1px solid var(--border-cell); }
:deep(.ag-header-cell) { border-right: 1px solid var(--border-header-cell); font-weight: 600; }
.summary { margin-top: 12px; font-size: 14px; color: var(--text-secondary); }
.summary-bar {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 6px; padding: 5px 12px;
  background: var(--bg-card); border-radius: 8px; box-shadow: var(--shadow-card);
}
.summary-cards { display: flex; gap: 16px; }
.s-card {
  display: flex; flex-direction: column; gap: 2px; min-width: 110px;
  padding: 0 12px 0 0; border-right: 1px solid var(--border-light);
}
.s-card:last-child { border-right: none; }
.s-card-total { min-width: 140px; }
.s-label { font-size: 11px; color: var(--text-light); }
.s-value { font-size: 14px; font-weight: 700; color: var(--text-primary); letter-spacing: 0.5px; }
.s-value-red { color: var(--color-danger); }
.s-value-green { color: var(--color-success); }
.summary-count { font-size: 13px; color: var(--text-muted); white-space: nowrap; }
.deduction-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; padding: 6px 12px; background: var(--bg-deduction-bar); border-radius: 6px; border: 1px solid var(--border-deduction); }
.btn-save { padding: 6px 16px; background: var(--color-primary); color: var(--text-on-primary); border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-save:disabled { background: var(--text-light); cursor: not-allowed; }
.change-badge { background: var(--color-danger); color: #fff; font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.toolbar-sep { width: 1px; height: 24px; background: var(--border-default); margin: 0 4px; }
.toolbar-hint { font-size: 12px; color: var(--text-muted); margin-left: auto; }
.toggle-label { font-size: 13px; color: var(--text-secondary); cursor: pointer; display: flex; align-items: center; gap: 4px; user-select: none; }
.save-toast {
  position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
  z-index: 9999; font-size: 14px; padding: 10px 28px; border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15); animation: fadeIn 0.25s ease;
  pointer-events: none;
}
.toast-success { background: #2e7d32; color: #fff; }
:deep(.cell-locked) { border-left: 3px solid var(--color-primary) !important; }
.toast-error { background: #c62828; color: #fff; }
@keyframes fadeIn { from { opacity: 0; transform: translateX(-50%) translateY(-8px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }

/* Bill export dialog */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center;
  z-index: 10000;
}
.modal-dialog {
  background: var(--bg-card); border-radius: var(--radius-lg);
  padding: var(--space-2xl) var(--space-3xl);
  width: 480px; max-width: 90vw;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}
.modal-dialog h3 { font-size: var(--text-xl); margin-bottom: var(--space-sm); color: var(--text-primary); }
.modal-hint { font-size: var(--text-base); color: var(--text-muted); margin-bottom: var(--space-xl); }
.form-row { display: flex; align-items: center; gap: var(--space-md); margin-bottom: var(--space-lg); }
.form-row label { font-size: var(--text-md); color: var(--text-secondary); min-width: 80px; text-align: right; }
.input-md { padding: var(--space-sm) var(--space-md); border: 1px solid var(--border-default); border-radius: var(--radius-md); font-size: var(--text-base); width: 280px; background: var(--bg-card); color: var(--text-primary); transition: border-color var(--transition-fast); }
.input-md:focus { border-color: var(--border-input-focus); background: var(--bg-input-focus); outline: none; }
.modal-actions { display: flex; gap: 12px; justify-content: center; margin-top: 24px; }
.tpl-hint { font-size: 12px; color: var(--text-muted); font-style: italic; }

/* ── Party autocomplete ── */
.autocomplete-row { position: relative; }
.autocomplete-wrapper { position: relative; flex: 1; }
.autocomplete-wrapper .input-md { width: 100%; box-sizing: border-box; }
.autocomplete-wrapper .input-md:focus {
  border-color: var(--border-input-focus);
  background: var(--bg-input-focus);
}
.autocomplete-dropdown {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 100;
  background: var(--bg-card); border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-elevated);
  max-height: 200px; overflow-y: auto; list-style: none;
  margin: var(--space-xs) 0 0 0; padding: var(--space-xs) 0;
}
.autocomplete-dropdown li {
  padding: var(--space-sm) var(--space-md);
  cursor: pointer; font-size: var(--text-base);
  color: var(--text-primary); display: flex; align-items: center; gap: var(--space-sm);
  transition: background var(--transition-fast);
}
.autocomplete-dropdown li:hover {
  background: var(--bg-row-alt);
}
.autocomplete-dropdown li.highlighted {
  background: var(--bg-input-focus);
  color: var(--color-primary);
  font-weight: var(--weight-medium);
}
.party-type-tag {
  font-size: var(--text-xs); color: var(--text-light); background: var(--palette-gray-50);
  padding: 0 var(--space-sm); border-radius: var(--radius-sm); white-space: nowrap;
}
.selected-badge {
  font-size: var(--text-sm); color: var(--color-success); white-space: nowrap; margin-left: var(--space-xs);
  font-weight: var(--weight-semibold);
}

/* Payment registration */
.payment-preview {
  background: var(--palette-gray-50); border-radius: 6px; padding: 12px;
  margin-bottom: 12px; max-height: 200px; overflow-y: auto;
}
.preview-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--text-secondary); }
.preview-table { width: 100%; font-size: 13px; border-collapse: collapse; }
.preview-table th { text-align: left; padding: 4px 6px; border-bottom: 2px solid var(--border-default); font-weight: 600; color: var(--text-secondary); }
.preview-table td { padding: 4px 6px; border-bottom: 1px solid var(--border-light); }
.preview-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.preview-warn { font-size: 12px; color: var(--color-danger); margin-top: 6px; }
.payment-result { font-size: 14px; color: var(--color-success); padding: 8px 0; }
.form-error { font-size: 13px; color: var(--color-danger); padding: 6px 0; }
</style>
