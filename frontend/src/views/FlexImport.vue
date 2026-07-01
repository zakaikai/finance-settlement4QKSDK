<template>
  <div :class="['flex-page', { 'review-wide': step === 2 }]">
    <h2>弹性账单导入
      <span class="badge beta">Beta</span>
      <button class="btn tiny dict-btn" @click="showDict = !showDict" title="管理列名同义词词典">
        {{ showDict ? '收起词典' : '词典' }}
      </button>
    </h2>
    <p class="subtitle">上传任意格式渠道账单 Excel，自动推断列映射，智能匹配游戏名称</p>

    <!-- Dictionary panel -->
    <div v-if="showDict" class="dict-panel">
      <div class="dict-header">
        <strong>列名同义词词典</strong>
        <span class="dict-hint">导出 → 编辑添加渠道特有列名 → 上传覆写</span>
      </div>
      <div class="dict-actions">
        <button class="btn small" @click="exportDict">导出词典</button>
        <label class="btn small upload-label">
          上传词典
          <input type="file" accept=".json" hidden @change="importDict" />
        </label>
      </div>
      <div v-if="dictError" class="dict-error">{{ dictError }}</div>
      <div v-if="dictOk" class="dict-ok">{{ dictOk }}</div>
    </div>

    <!-- Step indicator -->
    <div class="steps">
      <div class="step" :class="{ active: step >= 0, done: step > 0 }">1. 上传配置</div>
      <div class="step-arrow">→</div>
      <div class="step" :class="{ active: step >= 1, done: step > 1 }">2. 确认列映射</div>
      <div class="step-arrow">→</div>
      <div class="step" :class="{ active: step >= 2 }">3. 审核导入</div>
    </div>

    <!-- Step 0: Upload & Config -->
    <div v-if="step === 0" class="section">
      <div class="step0-grid">
        <div class="step0-field">
          <label>上传账单 Excel 文件</label>
          <div class="dropzone" @dragover.prevent="dragover = true" @dragleave="dragover = false"
            @drop.prevent="handleDrop" @click="triggerFile" :class="{ dragover }">
            <input ref="fileInput" type="file" accept=".xlsx,.xls" hidden @change="handleFile" />
            <div v-if="!excelFile" class="dropzone-hint">
              <span class="dropzone-icon">📄</span>
              <span>拖拽 .xlsx 文件到此处，或点击选择</span>
            </div>
            <div v-else class="file-selected">
              <span class="file-icon">📄</span>
              <span>{{ excelFile.name }}</span>
              <span class="file-size">({{ (excelFile.size / 1024).toFixed(0) }} KB)</span>
              <button class="btn tiny" @click.stop="excelFile = null; imageFile = null">清除</button>
            </div>
          </div>
        </div>

        <div class="step0-field">
          <label>表头所在行号 (题头行之后)</label>
          <input v-model.number="headerRow" type="number" min="1" max="20" class="num-input" />
          <span class="hint">通常第 1 行是表头，如有题头则填写题头之后的行号</span>
        </div>

        <div class="step0-field">
          <label>选择渠道 (本账单归属)</label>
          <ChannelPicker v-model="selectedChannelId" placeholder="输入渠道名称搜索…" />
        </div>

        <div class="step0-field">
          <label>账单所属月份</label>
          <input v-model="selectedMonth" type="month" class="month-input" />
        </div>
      </div>

      <div class="step-actions">
        <button class="btn primary" :disabled="!excelFile || !selectedChannelId || previewLoading"
          @click="doPreview">
          <span v-if="previewLoading">解析中…</span>
          <span v-else>下一步：确认列映射</span>
        </button>
      </div>
    </div>

    <!-- Step 1: Column Mapping -->
    <div v-if="step === 1" class="section">
      <p class="hint">
        已自动推断各列映射关系，请逐一核实。每列可手动调整为正确的字段类型。
      </p>
      <div class="table-wrap">
        <table class="map-table">
          <thead>
            <tr>
              <th>列序号</th>
              <th>Excel 表头</th>
              <th>映射到字段</th>
              <th>置信度</th>
              <th>预览数据 (前5行)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(m, ci) in suggestedMapping" :key="ci"
              :class="{ 'row-low': m.confidence < 60 && m.suggested_field !== 'ignore' }">
              <td class="col-idx">{{ ci + 1 }}</td>
              <td class="col-header">{{ m.header || '（空）' }}</td>
              <td>
                <select v-model="columnMapping[ci]" class="col-select"
                  :class="confidenceClass(ci)">
                  <option v-for="opt in FIELD_OPTIONS" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </td>
              <td class="col-conf">
                <span v-if="m.confidence > 0" :class="confTagClass(m.confidence)">
                  {{ m.confidence }}%
                </span>
                <span v-else class="conf-unk">—</span>
              </td>
              <td class="col-preview">
                <span v-for="(cell, ri) in previewCol(ci)" :key="ri" class="pv-cell">{{ cell }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="step-actions">
        <button class="btn" @click="step = 0">上一步</button>
        <button class="btn primary" :disabled="!hasGameNameCol || confirmLoading" @click="doConfirm">
          <span v-if="confirmLoading">导入中…</span>
          <span v-else>下一步：审核导入</span>
        </button>
        <span v-if="!hasGameNameCol" class="warn-inline">⚠ 请至少将一列映射为「游戏名称」</span>
      </div>
    </div>

    <!-- Step 2: Review & Import (Step 3 in wizard) -->
    <div v-if="step === 2" class="section">
      <div class="result-bar">
        <span>共 <strong>{{ parsedRows.length }}</strong> 行
          <span v-if="matchSummary.total > 0">，匹配: </span>
        </span>
        <span v-if="matchSummary.total > 0" class="match-summary">
          <span class="tag high">{{ matchSummary.high }} 高</span>
          <span class="tag medium">{{ matchSummary.medium }} 中</span>
          <span class="tag low">{{ matchSummary.low }} 低</span>
          <span class="tag none">{{ matchSummary.none }} 无</span>
        </span>
        <span v-if="changedCount > 0" class="changed-hint">，{{ changedCount }} 行有数据变化</span>
      </div>

      <div v-if="monthMissing" class="month-warn">
        未指定账单所属月份，无法抓取旧数据进行对比。若账单包含「月份」列，请将其映射后返回上一步重新确认。
      </div>

      <div v-if="dupGameIds.length > 0" class="dup-warn">
        ⚠ 检测到 {{ dupGameIds.length }} 个游戏被多行重复匹配，导入时同游戏同月份只能保留一行。
        请在下方修正游戏名称或取消重复行的勾选。
        <ul><li v-for="gid in dupGameIds" :key="gid">游戏: {{ dupGameName(gid) }}（行: {{ dupRows(gid).join(', ') }}）</li></ul>
      </div>

      <div class="sel-bar">
        <label class="sel-all"><input type="checkbox" :checked="allSelected" @change="toggleAll" /> 全选</label>
        <span class="sel-count">已选 {{ selectedCount }} / {{ parsedRows.length }} 行</span>
      </div>

      <div class="table-wrap" v-if="parsedRows.length > 0">
        <table class="review-table">
          <thead>
            <tr>
              <th class="th-sel">导入</th>
              <th>游戏名称</th>
              <th>匹配</th>
              <th v-if="showMonthColumn">月份</th>
              <th v-for="f in comparisonFields" :key="f.key" class="th-comp">{{ f.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in parsedRows" :key="ri"
              :class="{ 'row-changed': rowHasChanges(ri), 'row-low': row.match_status === 'low' }">
              <td class="td-sel">
                <input type="checkbox" :checked="!!selectedRows[ri]" @change="onSelectRow(ri, $event)" />
              </td>
              <td class="td-game" @dblclick="editCell(ri, 'game_name')">
                <template v-if="editingCell === `${ri}-game_name`">
                  <input v-model="editVal" @blur="saveEdit(ri, 'game_name')" @keydown.enter="saveEdit(ri, 'game_name')"
                    class="cell-input" autofocus />
                </template>
                <template v-else>
                  {{ row.game_name || row.matched_game_name }}
                  <span v-if="isDupRow(ri)" class="badge-dup" title="该游戏被多行重复匹配">重复</span>
                </template>
              </td>
              <td class="td-match">
                <span v-if="row.match_status" :class="'tag ' + row.match_status">
                  {{ row.matched_game_name || '?' }}
                  <small v-if="row.match_confidence">({{ row.match_confidence }}%)</small>
                </span>
                <span v-else class="tag none">—</span>
              </td>
              <td v-if="showMonthColumn" class="td-month">{{ row.month }}</td>
              <td v-for="f in comparisonFields" :key="f.key" class="td-comp"
                :class="{ 'cell-changed': getComp(ri, f.key).changed }"
                @dblclick="editCell(ri, f.key)">
                <template v-if="editingCell === `${ri}-${f.key}`">
                  <input v-model="editVal" @blur="saveEdit(ri, f.key)" @keydown.enter="saveEdit(ri, f.key)"
                    class="cell-input" autofocus />
                </template>
                <template v-else>
                  <span class="val-new">{{ displayVal(getComp(ri, f.key)) }}</span>
                  <template v-if="getComp(ri, f.key).changed">
                    <span class="val-arrow">←</span>
                    <span class="val-old">{{ fmtVal(getComp(ri, f.key).old) }}</span>
                  </template>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">暂无解析数据</div>

      <div class="step-actions">
        <button class="btn" @click="step = 1">上一步</button>
        <button class="btn success" :disabled="importLoading || selectedCount === 0" @click="doImport">
          <span v-if="importLoading">写入中…</span>
          <span v-else>确认导入 ({{ selectedCount }} 行)</span>
        </button>
      </div>
    </div>

    <!-- Error display -->
    <div v-if="errorMsg" class="error-box">
      <strong>错误：</strong> {{ errorMsg }}
      <button class="btn tiny" @click="errorMsg = ''">关闭</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api, { logError } from '../api'
import ChannelPicker from '../components/ChannelPicker.vue'
import { useToast } from '../components/AppToast/useToast'

// ── Field options for column mapping ──
const FIELD_OPTIONS = [
  { value: 'game_name', label: '游戏名称' },
  { value: 'game_id', label: '游戏编号' },
  { value: 'raw_revenue', label: '原始流水' },
  { value: 'real_revenue', label: '真实流水' },
  { value: 'vouchers', label: '代金券' },
  { value: 'test', label: '测试费' },
  { value: 'welfare', label: '福利币' },
  { value: 'bad_debt', label: '坏账' },
  { value: 'total_deductions', label: '扣除合计' },
  { value: 'split_rate', label: '分成比例' },
  { value: 'channel_fee_rate', label: '通道费率' },
  { value: 'tax_rate', label: '税率' },
  { value: 'settlement_amount', label: '结算金额' },
  { value: 'month', label: '月份' },
  { value: 'ignore', label: '忽略此列' },
]

// ── State ──
const step = ref(0)
const dragover = ref(false)
const excelFile = ref(null)
const headerRow = ref(1)
const selectedMonth = ref('')
const selectedChannelId = ref(null)
const allChannels = ref([])

const previewLoading = ref(false)
const confirmLoading = ref(false)
const importLoading = ref(false)
const errorMsg = ref('')

const suggestedMapping = ref([])
const columnMapping = ref({})
const previewHeaders = ref([])
const previewRows = ref([])
const parsedRows = ref([])
const matchResults = ref([])
const matchSummary = ref({ total: 0, high: 0, medium: 0, low: 0, none: 0 })
const comparison = ref([])
const selectedRows = ref({})
const editingCell = ref(null)
const editVal = ref('')
const monthMissing = ref(false)
const toast = useToast()

// Fields to show in comparison table — only user-mapped columns
const allComparisonFields = [
  { key: 'raw_revenue', label: '原始流水' },
  { key: 'real_revenue', label: '真实流水' },
  { key: 'vouchers', label: '代金券' },
  { key: 'test', label: '测试' },
  { key: 'welfare', label: '福利币' },
  { key: 'bad_debt', label: '坏账' },
  { key: 'split_rate', label: '分成比例' },
  { key: 'channel_fee_rate', label: '通道费率' },
  { key: 'tax_rate', label: '税率' },
  { key: 'settlement_amount', label: '结算金额' },
]

const comparisonFields = computed(() => {
  const mapped = new Set(Object.values(columnMapping.value).filter(v => v && v !== 'ignore'))
  return allComparisonFields.filter(f => mapped.has(f.key))
})

// ── File handling ──
const fileInput = ref(null)
function triggerFile() { fileInput.value?.click() }

function autoDetectChannel(filename) {
  if (!filename || allChannels.value.length === 0) return
  const basename = filename.replace(/\.[^.]+$/, '').toLowerCase().trim()
  if (!basename) return
  const matches = allChannels.value.filter(ch =>
    ch.channel_name.toLowerCase().includes(basename) ||
    basename.includes(ch.channel_name.toLowerCase())
  )
  if (matches.length === 1) selectedChannelId.value = matches[0].channel_id
}

onMounted(async () => {
  try {
    const r = await api.getSettlementChannels()
    allChannels.value = r.data.data || []
  } catch { /* ignore */ }
})

function handleFile(e) {
  const f = e.target.files[0]
  if (f) {
    excelFile.value = f
    autoDetectChannel(f.name)
  }
}

function handleDrop(e) {
  dragover.value = false
  const f = e.dataTransfer.files[0]
  if (f) {
    excelFile.value = f
    autoDetectChannel(f.name)
  }
}

// ── Preview: upload → infer mapping ──
const hasGameNameCol = computed(() => {
  return Object.values(columnMapping.value).includes('game_name')
})

async function doPreview() {
  if (!excelFile.value) return
  if (!selectedChannelId.value) { errorMsg.value = '请先选择渠道'; return }
  previewLoading.value = true
  errorMsg.value = ''
  try {
    const r = await api.flexiblePreview(excelFile.value, headerRow.value)
    const data = r.data
    suggestedMapping.value = data.suggested_mapping || []
    previewHeaders.value = data.headers || []
    previewRows.value = data.preview_rows || []

    // Init column mapping from suggestions
    const cm = {}
    for (const m of suggestedMapping.value) {
      cm[m.col_index] = m.suggested_field
    }
    columnMapping.value = cm

    step.value = 1
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || e.message || '预览失败'
    logError('flexPreview', e)
  } finally {
    previewLoading.value = false
  }
}

// ── Confirm: parse with user mapping → game match → review (no DB write) ──
async function doConfirm() {
  confirmLoading.value = true
  errorMsg.value = ''
  try {
    const r = await api.flexibleConfirm(
      excelFile.value, headerRow.value,
      selectedMonth.value, selectedChannelId.value, columnMapping.value
    )
    const d = r.data
    parsedRows.value = (d.rows || []).map(row => ({
      ...row,
      match_status: row.match_status || 'none',
      match_confidence: row.match_confidence || 0,
      matched_game_name: row.matched_game_name || '',
      match_candidates: row.match_candidates || [],
    }))
    matchResults.value = d.match_results || []
    matchSummary.value = computeSummary(parsedRows.value)
    comparison.value = d.comparison || []
    monthMissing.value = d.month_missing || false

    // Default select rows with >=60% match confidence (high + medium)
    const sel = {}
    for (let i = 0; i < parsedRows.value.length; i++) {
      const s = parsedRows.value[i].match_status
      sel[i] = s === 'high' || s === 'medium'
    }
    selectedRows.value = sel

    if (d.errors && d.errors.length > 0) {
      errorMsg.value = d.errors.map(e =>
        `[第${e.row}行] ${Array.isArray(e.errors) ? e.errors.join('; ') : e.error}`
      ).join('\n')
    }
    step.value = 2
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || e.message || '解析失败'
    logError('flexConfirm', e)
  } finally {
    confirmLoading.value = false
  }
}

function computeSummary(rows) {
  const s = { total: rows.length, high: 0, medium: 0, low: 0, none: 0 }
  for (const r of rows) {
    const st = r.match_status || 'none'
    s[st] = (s[st] || 0) + 1
  }
  return s
}

// ── Import: write to DB ──
async function doImport() {
  importLoading.value = true
  errorMsg.value = ''
  try {
    const selIndices = Object.entries(selectedRows.value)
      .filter(([, v]) => v)
      .map(([k]) => parseInt(k))

    if (selIndices.length === 0) { errorMsg.value = '请至少选择一行导入'; return }

    const r = await api.flexibleImport(
      excelFile.value, headerRow.value,
      selectedMonth.value, selectedChannelId.value, columnMapping.value, selIndices
    )

    toast.success(`导入成功！\n扣除项目: ${r.data.imported_deductions} 条\n分成配置: ${r.data.imported_configs || 0} 条`)
    step.value = 0
    excelFile.value = null
    parsedRows.value = []
    matchResults.value = []
  } catch (e) {
    const detail = e.response?.data?.detail
    if (detail && typeof detail === 'object' && detail.errors) {
      errorMsg.value = detail.errors.map(e =>
        `[第${e.row}行] ${Array.isArray(e.errors) ? e.errors.join('; ') : e.error}`
      ).join('\n')
    } else {
      errorMsg.value = (typeof detail === 'string' ? detail : '') || e.message || '导入失败'
    }
    logError('flexImport', e)
  } finally {
    importLoading.value = false
  }
}

// ── UI helpers ──
const activeCols = computed(() => {
  return suggestedMapping.value
    .filter(m => columnMapping.value[m.col_index] !== 'ignore')
    .map(m => ({ header: m.header, field: columnMapping.value[m.col_index] }))
})

const allSelected = computed(() => parsedRows.value.length > 0 && selectedCount.value === parsedRows.value.length)
const selectedCount = computed(() => Object.values(selectedRows.value).filter(Boolean).length)
const changedCount = computed(() => {
  return comparison.value.filter(c => Object.values(c.fields || {}).some(f => f.changed)).length
})

const showMonthColumn = computed(() => !selectedMonth.value)

function toggleAll() {
  const v = !allSelected.value
  if (v) {
    // Select all non-duplicate rows, plus one row per duplicate game group
    const sel = {}
    const dupByGame = {}
    // Find duplicate game groups
    for (let i = 0; i < parsedRows.value.length; i++) {
      const comp = comparison.value[i]
      if (comp && comp.is_duplicate) {
        const gid = comp.game_id
        if (!dupByGame[gid]) dupByGame[gid] = []
        dupByGame[gid].push(i)
      }
    }
    for (let i = 0; i < parsedRows.value.length; i++) {
      const comp = comparison.value[i]
      if (comp && comp.is_duplicate) {
        const gid = comp.game_id
        // Only select the first row of each duplicate group
        sel[i] = dupByGame[gid] && dupByGame[gid][0] === i
      } else {
        sel[i] = true
      }
    }
    selectedRows.value = sel
  } else {
    const sel = {}
    for (let i = 0; i < parsedRows.value.length; i++) sel[i] = false
    selectedRows.value = sel
  }
}

function onSelectRow(ri, event) {
  const checked = event.target.checked
  if (checked) {
    // Check if this row has a duplicate game_id; if so, uncheck sibling dup rows
    const comp = comparison.value[ri]
    if (comp && comp.is_duplicate) {
      const gid = comp.game_id
      const newSel = { ...selectedRows.value }
      for (let i = 0; i < parsedRows.value.length; i++) {
        if (i !== ri) {
          const c = comparison.value[i]
          if (c && c.is_duplicate && c.game_id === gid) {
            newSel[i] = false
          }
        }
      }
      newSel[ri] = true
      selectedRows.value = newSel
      return
    }
  }
  selectedRows.value = { ...selectedRows.value, [ri]: checked }
}

// Duplicate detection helpers
const dupGameIds = computed(() => {
  const dup = new Set()
  const seen = {}
  for (const c of comparison.value) {
    if (!c.game_id) continue
    if (seen[c.game_id]) {
      dup.add(c.game_id)
    } else {
      seen[c.game_id] = true
    }
  }
  return [...dup]
})

function dupGameName(gid) {
  for (const row of parsedRows.value) {
    if (row.game_id === gid) return row.matched_game_name || row.game_name || gid
  }
  return gid
}

function dupRows(gid) {
  const indices = []
  for (let i = 0; i < comparison.value.length; i++) {
    if (comparison.value[i].game_id === gid) indices.push(i + 1)
  }
  return indices
}

function isDupRow(ri) {
  const c = comparison.value[ri]
  return c && c.is_duplicate
}

function getComp(ri, fieldKey) {
  const c = comparison.value[ri]
  if (!c || !c.fields) return { old: null, new: null, changed: false }
  return c.fields[fieldKey] || { old: null, new: null, changed: false }
}

function rowHasChanges(ri) {
  const c = comparison.value[ri]
  if (!c || !c.fields) return false
  return Object.values(c.fields).some(f => f.changed)
}

function fmtVal(v) {
  if (v === null || v === undefined || v === '') return null
  if (typeof v === 'number') return v.toLocaleString()
  return v
}

function displayVal(comp) {
  return fmtVal(comp.new) || fmtVal(comp.old) || '—'
}

function editCell(ri, fieldKey) {
  const key = `${ri}-${fieldKey}`
  editingCell.value = key
  if (fieldKey === 'game_name') {
    editVal.value = parsedRows.value[ri]?.game_name || ''
  } else {
    editVal.value = parsedRows.value[ri]?.[fieldKey] ?? ''
  }
}

function saveEdit(ri, fieldKey) {
  const v = editVal.value
  if (parsedRows.value[ri]) {
    if (fieldKey === 'game_name') {
      parsedRows.value[ri].game_name = v
    } else {
      parsedRows.value[ri][fieldKey] = isNaN(Number(v)) ? v : Number(v)
    }
  }
  editingCell.value = null
}

function previewCol(ci) {
  return previewRows.value.slice(0, 5).map(r => r[ci] || '')
}

function confidenceClass(ci) {
  const m = suggestedMapping.value.find(x => x.col_index === ci)
  if (!m) return ''
  if (m.confidence >= 80) return 'sel-high'
  if (m.confidence >= 50) return 'sel-mid'
  return 'sel-low'
}

function confTagClass(conf) {
  if (conf >= 80) return 'conf-high'
  if (conf >= 50) return 'conf-mid'
  return 'conf-low'
}

function matchRowClass(row) {
  const s = row.match_status || 'none'
  return 'row-' + s
}

// ── Dictionary management ──
const showDict = ref(false)
const dictError = ref('')
const dictOk = ref('')

async function exportDict() {
  dictError.value = ''
  dictOk.value = ''
  try {
    const r = await api.exportSynonymDict()
    const blob = new Blob([JSON.stringify(r.data.data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'column_synonyms.json'
    a.click()
    URL.revokeObjectURL(url)
    dictOk.value = '词典已导出'
  } catch (e) {
    dictError.value = '导出失败: ' + (e.response?.data?.detail || e.message)
  }
}

async function importDict(e) {
  dictError.value = ''
  dictOk.value = ''
  const f = e.target.files[0]
  if (!f) return
  try {
    const r = await api.importSynonymDict(f)
    dictOk.value = `词典已更新 (${r.data.fields_updated} 个字段)`
    e.target.value = ''
  } catch (e) {
    dictError.value = '上传失败: ' + (e.response?.data?.detail || e.message)
  }
}

</script>

<style scoped>
.flex-page { max-width: 1100px; }
.flex-page.review-wide { max-width: 100%; }
.subtitle { color: var(--text-muted); font-size: 14px; margin: 4px 0 20px; }
.badge.beta {
  font-size: 11px; background: var(--color-warning); color: var(--text-on-primary); padding: 2px 8px;
  border-radius: 10px; font-weight: 600; vertical-align: middle;
}
.dict-btn { margin-left: 8px; font-size: 11px; padding: 2px 10px; }

/* Dictionary panel */
.dict-panel {
  background: var(--palette-gray-80); border: 1px solid var(--border-light); border-radius: 8px;
  padding: 14px 18px; margin-bottom: 20px; font-size: 13px;
}
.dict-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.dict-hint { color: var(--text-light); font-size: 12px; }
.dict-actions { display: flex; gap: 8px; }
.dict-error { margin-top: 8px; color: var(--color-danger); font-size: 12px; }
.dict-ok { margin-top: 8px; color: var(--color-success); font-size: 12px; }
.upload-label { cursor: pointer; }

/* Steps */
.steps {
  display: flex; gap: 12px; align-items: center; margin-bottom: 24px;
  flex-wrap: wrap;
}
.step {
  padding: 8px 16px; border-radius: 20px; font-size: 13px;
  background: var(--border-light); color: var(--text-muted);
}
.step.active { background: var(--color-primary); color: var(--bg-card); font-weight: 600; }
.step.done { background: var(--color-success); color: var(--text-on-primary); }
.step-arrow { color: #ccc; }

/* Section */
.section { background: var(--bg-card); border-radius: 10px; padding: 24px; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06); }

/* Step 0 */
.step0-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
.step0-field { display: flex; flex-direction: column; gap: 6px; }
.step0-field label { font-weight: 600; font-size: 14px; color: var(--text-primary); }
.num-input { width: 80px; padding: 8px 10px; border: 1px solid var(--border-default); border-radius: 6px; font-size: 14px; }
.month-input { padding: 8px 10px; border: 1px solid var(--border-default); border-radius: 6px; font-size: 14px; }
.hint { font-size: 12px; color: var(--text-light); }

/* Dropzone */
.dropzone {
  border: 2px dashed var(--border-dashed); border-radius: 8px; padding: 24px;
  text-align: center; cursor: pointer; transition: border-color 0.2s, background 0.2s;
  min-height: 80px; display: flex; align-items: center; justify-content: center;
}
.dropzone:hover, .dropzone.dragover { border-color: var(--color-primary); background: var(--bg-tag-blue); }
.dropzone-hint { display: flex; flex-direction: column; align-items: center; gap: 8px; color: var(--text-light); }
.dropzone-icon { font-size: 28px; }
.file-selected { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.file-icon { font-size: 20px; }
.file-size { color: var(--text-light); font-size: 12px; }

/* Combobox */
.combobox { position: relative; }
.combobox-input {
  width: 100%; padding: 8px 10px; border: 1px solid var(--border-default); border-radius: 6px; font-size: 14px;
}
.combobox-clear { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); cursor: pointer; color: var(--text-light); }
.combobox-list {
  position: absolute; top: 100%; left: 0; right: 0; max-height: 200px; overflow-y: auto;
  background: var(--bg-card); border: 1px solid var(--border-default); border-radius: 6px; z-index: 10;
  list-style: none; padding: 4px 0; margin: 4px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.combobox-list li { padding: 8px 12px; cursor: pointer; font-size: 14px; }
.combobox-list li:hover, .combobox-list li.active { background: var(--bg-tag-blue); color: var(--color-primary); }
.no-match { color: var(--text-light); font-style: italic; }

/* Column mapping table */
.table-wrap { overflow-x: auto; margin-bottom: 16px; }
.map-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.map-table th, .map-table td { padding: 8px 10px; border: 1px solid var(--border-light); text-align: left; }
.map-table th { background: var(--palette-gray-50); font-weight: 600; white-space: nowrap; }
.col-idx { width: 50px; text-align: center; color: var(--text-light); }
.col-header { min-width: 100px; font-weight: 500; }
.col-select { padding: 4px 8px; border-radius: 4px; border: 1px solid var(--border-default); font-size: 13px; width: 120px; }
.col-select.sel-high { border-color: var(--color-success); background: var(--bg-tag-green); }
.col-select.sel-mid { border-color: var(--color-warning); background: var(--bg-tag-yellow); }
.col-select.sel-low { border-color: var(--color-danger); background: var(--bg-badge-error); }
.col-conf { width: 60px; text-align: center; }
.conf-high { color: var(--color-success); font-weight: 600; }
.conf-mid { color: var(--color-warning); font-weight: 600; }
.conf-low { color: var(--color-danger); font-weight: 600; }
.conf-unk { color: #ccc; }
.col-preview { min-width: 120px; }
.pv-cell { display: inline-block; background: var(--border-cell); padding: 2px 6px; border-radius: 3px; margin: 1px 2px; font-size: 11px; }
.row-low { background: var(--bg-row-danger); }

/* Review table */
.table-wrap { overflow-x: auto; overflow-y: auto; max-height: 65vh; border: 1px solid var(--border-header-cell); border-radius: 6px; }
.review-table { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: auto; }
.review-table th, .review-table td { padding: 5px 10px; border-bottom: 1px solid var(--border-light); text-align: left; white-space: nowrap; }
.review-table th { background: var(--palette-gray-50); font-weight: 600; position: sticky; top: 0; z-index: 3; border-bottom: 2px solid var(--border-default); }
.review-table tbody tr:nth-child(even) { background: var(--palette-gray-50); }
.review-table tbody tr:hover { background: var(--bg-tag-blue); }
.th-sel { width: 40px; text-align: center; }
.td-sel { text-align: center; }
.td-game { min-width: 130px; cursor: pointer; }
.td-game:hover { background: var(--bg-tag-blue); }
.td-match { min-width: 110px; }
.td-month { min-width: 85px; color: var(--text-secondary); font-size: 12px; }
.td-comp { min-width: 100px; cursor: pointer; position: relative; }
.td-comp:hover { background: var(--bg-tag-blue); }
.cell-changed { background: var(--bg-row-danger) !important; border-left: 3px solid var(--color-danger); }
.cell-changed .val-new { color: var(--color-primary); }
.val-new { font-weight: 700; color: var(--color-primary); }
.val-arrow { color: var(--color-danger); font-size: 10px; margin: 0 3px; }
.val-old { color: var(--color-danger); font-size: 11px; font-weight: 500; }
.row-changed { background: var(--bg-row-changed) !important; }
.row-low { opacity: 0.7; }
.cell-input { width: 100%; padding: 2px 6px; font-size: 12px; border: 1px solid var(--color-info); border-radius: 2px; }

.sel-bar { display: flex; gap: 16px; align-items: center; margin-bottom: 10px; font-size: 13px; }
.sel-all { cursor: pointer; display: flex; align-items: center; gap: 4px; }
.sel-count { color: var(--text-muted); }
.changed-hint { color: var(--color-warning); font-weight: 600; }

/* Tags */
.tag {
  display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600;
}
.tag.high { background: var(--bg-tag-green); color: var(--color-success); }
.tag.medium { background: var(--bg-tag-yellow); color: var(--color-warning); }
.tag.low { background: var(--bg-badge-error); color: var(--color-danger); }
.tag.none { background: var(--palette-gray-100); color: var(--text-muted); }
.tag small { font-weight: 400; opacity: 0.7; }

/* Row highlight */
.row-high { background: var(--bg-tag-green); }
.row-medium { background: var(--bg-tag-yellow); }
.row-low { background: var(--bg-badge-error); }
.row-none { }

/* Result bar */
.result-bar { display: flex; gap: 16px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.match-summary { display: flex; gap: 6px; align-items: center; }

/* Actions */
.step-actions { display: flex; gap: 10px; align-items: center; margin-top: 16px; }
.warn-inline { color: var(--color-warning); font-size: 13px; }

/* Month & duplicate warnings */
.month-warn { margin-bottom: 12px; padding: 10px 14px; background: var(--bg-tag-yellow); border: 1px solid var(--color-warning); border-radius: 6px; color: var(--color-warning); font-size: 13px; }
.dup-warn { margin-bottom: 12px; padding: 10px 14px; background: var(--bg-badge-error); border: 1px solid var(--color-danger); border-radius: 6px; color: var(--color-danger); font-size: 13px; }
.dup-warn ul { margin: 6px 0 0 16px; padding: 0; }
.dup-warn li { margin: 2px 0; }
.badge-dup { display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 700; background: var(--color-danger); color: var(--text-on-primary); vertical-align: middle; }

/* Error */
.error-box { margin-top: 16px; padding: 12px 16px; background: var(--bg-badge-error); border: 1px solid var(--color-danger); border-radius: 8px; color: var(--color-danger); font-size: 13px; display: flex; justify-content: space-between; align-items: center; }

.empty { text-align: center; color: var(--text-light); padding: 40px; }

/* Buttons (reuse global .btn styles) */
</style>
