<template>
  <div class="ocr-page">
    <h2>OCR 账单识别导入
      <span class="badge beta">Beta</span>
      <span class="bridge-dot" :class="bridgeOnline ? 'on' : (bridgeStarting ? 'starting' : 'off')" :title="bridgeOnline ? 'PaddleOCR 在线' : 'PaddleOCR 离线'"></span>
      <button v-if="!bridgeOnline && !bridgeStarting" class="btn tiny" @click="startBridge" :disabled="bridgeStarting">启动 OCR</button>
      <button v-if="bridgeOnline" class="btn tiny danger" @click="stopBridge">停止 OCR</button>
      <span v-if="bridgeStarting" class="starting-text">启动中…</span>
    </h2>
    <p class="beta-notice">⚠ 图片识别较慢（约3分钟/张），建议优先使用 <a href="/flex-import">弹性导入</a> 处理 Excel 账单。</p>

    <!-- Step indicator -->
    <div class="steps">
      <div class="step" :class="{ active: step >= 0 }">1. 选择渠道</div>
      <div class="step-arrow">→</div>
      <div class="step" :class="{ active: step >= 1 }">2. 上传识别</div>
      <div class="step-arrow">→</div>
      <div class="step" :class="{ active: step >= 2 }">3. 确认列映射</div>
      <div class="step-arrow">→</div>
      <div class="step" :class="{ active: step >= 3 }">4. 匹配审核</div>
      <div class="step-arrow">→</div>
      <div class="step" :class="{ active: step >= 4 }">5. 保存</div>
    </div>

    <!-- Step 0: Channel + Month selection -->
    <div v-if="step === 0" class="section">
      <div class="step0-row">
        <div class="step0-field">
          <label>选择渠道（整张账单归属此渠道）：</label>
          <div class="combobox" :class="{ open: chDropdownOpen }">
            <input
              v-model="channelSearch"
              class="combobox-input"
              placeholder="输入渠道名称搜索…"
              @focus="chDropdownOpen = true"
              @blur="delayCloseChDropdown"
              @input="filterChannels"
            />
            <span v-if="channelSearch && !selectedChannel" class="combobox-clear" @mousedown.prevent="clearChannel">×</span>
            <ul v-if="chDropdownOpen" class="combobox-list">
              <li
                v-for="ch in filteredChannels"
                :key="ch.channel_id"
                :class="{ active: selectedChannel === ch.channel_name }"
                @mousedown.prevent="selectChannel(ch.channel_name)"
              >{{ ch.channel_name }}</li>
              <li v-if="filteredChannels.length === 0" class="no-match">无匹配渠道</li>
            </ul>
          </div>
        </div>
        <div class="step0-field">
          <label>选择月份（账单所属月份）：</label>
          <input v-model="selectedMonth" type="month" class="month-input" />
        </div>
      </div>
      <button class="btn primary" :disabled="!selectedChannel || !selectedMonth" @click="step = 1">下一步</button>
    </div>

    <!-- Step 1: Upload & OCR -->
    <div v-if="step === 1" class="section">
      <div
        class="dropzone"
        :class="{ dragover }"
        @dragover.prevent="dragover = true"
        @dragleave="dragover = false"
        @drop.prevent="handleDrop"
        @click="triggerFile"
      >
        <input ref="fileInput" type="file" accept="image/*" hidden @change="handleFile" />
        <div v-if="!imagePreview" class="dropzone-hint">
          <span class="dropzone-icon">📷</span>
          <span>拖拽账单截图到此处，或点击选择文件</span>
        </div>
        <img v-else :src="imagePreview" class="preview-img" />
      </div>
      <div class="step-actions">
        <button class="btn" @click="step = 0">上一步</button>
        <button class="btn primary" :disabled="!imageFile || ocrLoading" @click="doOCR">
          <span v-if="ocrLoading">识别中… {{ ocrProgress }}%</span>
          <span v-else>开始识别</span>
        </button>
      </div>
    </div>

    <!-- Step 2: Column mapping -->
    <div v-if="step === 2" class="section">
      <p class="hint">请确认每列的数据类型。表头行已用颜色标记推断结果，可手动调整。</p>
      <div class="table-wrap">
        <table class="ocr-table">
          <thead>
            <tr>
              <th v-for="(col, ci) in colHeaders" :key="ci" :class="headerClass(ci)">
                <select v-model="columnMapping[ci]" class="col-select">
                  <option v-for="opt in COL_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in tableData" :key="ri">
              <td v-for="(cell, ci) in row" :key="ci" :class="cellClass(ci, ri === 0)">
                {{ cell }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="step-actions">
        <button class="btn" @click="step = 1">上一步</button>
        <button class="btn primary" :disabled="!hasGameNameCol" @click="doMatch">匹配数据库</button>
      </div>
    </div>

    <!-- Step 3: Match review -->
    <div v-if="step === 3" class="section">
      <div class="match-summary">
        <span>匹配结果：</span>
        <span class="badge green">{{ matchSummary.high }} 高置信</span>
        <span class="badge yellow">{{ matchSummary.medium }} 中置信</span>
        <span class="badge red">{{ matchSummary.low }} 低置信</span>
        <span class="badge gray" v-if="matchSummary.none">{{ matchSummary.none }} 未匹配</span>
      </div>
      <div class="table-wrap">
        <table class="ocr-table">
          <thead>
            <tr>
              <th v-for="h in matchHeaders" :key="h">{{ h }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in matchRows" :key="ri">
              <td
                v-for="(cell, ci) in row"
                :key="ci"
                :class="matchCellClass(ri, ci)"
              >
                <template v-if="ci === gameNameColIdx">
                  <div class="game-cell" @click="cell.candidates?.length > 1 && toggleCandidates(ri)">
                    <span>{{ cell.text || cell.original }}</span>
                    <span v-if="cell.confidence != null" class="conf-tag" :class="cell.confClass">{{ cell.confidence }}%</span>
                    <span v-if="cell.candidates?.length > 1" class="cand-arrow">▾</span>
                  </div>
                  <ul v-if="candOpenIdx === ri && cell.candidates?.length > 1" class="cand-list">
                    <li
                      v-for="c in cell.candidates"
                      :key="c.game_id"
                      :class="{ selected: c.game_id === cell.matchedId }"
                      @mousedown.prevent="pickCandidate(ri, c)"
                    >{{ c.game_name }} <span class="cand-score">{{ c.score }}%</span></li>
                  </ul>
                  <input
                    v-else-if="candOpenIdx === ri && (!cell.candidates || cell.candidates.length <= 1)"
                    v-model="editVal"
                    class="cell-edit"
                    @blur="finishEdit(ri)"
                    @keydown.enter="finishEdit(ri)"
                  />
                </template>
                <span v-else>{{ typeof cell === 'object' ? (cell.text ?? cell.original ?? '') : cell }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="step-actions">
        <button class="btn" @click="step = 2">上一步</button>
        <button class="btn primary" @click="doSave">一键保存</button>
      </div>
    </div>

    <!-- Step 4: Save result -->
    <div v-if="step === 4" class="section">
      <div v-if="saveMsg" class="save-result" :class="{ error: saveError }">
        {{ saveMsg }}
      </div>
      <button class="btn primary" @click="resetAll">再来一张</button>
      <button class="btn" @click="$router.push('/settlement')">去结算页查看</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import api, { logError } from '../api'
import { useToast } from '../components/AppToast/useToast'

const step = ref(0)

const COL_OPTIONS = [
  { value: 'game_name', label: '游戏名称' },
  { value: 'amount_total', label: '金额-月流水/充值' },
  { value: 'amount_vouchers', label: '金额-代金券' },
  { value: 'amount_test', label: '金额-测试' },
  { value: 'amount_welfare', label: '金额-福利币' },
  { value: 'amount_bad_debt', label: '金额-坏账' },
  { value: 'ratio', label: '比例' },
  { value: 'settlement_amount', label: '金额-结算' },
  { value: 'month', label: '月份（覆盖所选月份）' },
  { value: 'ignore', label: '忽略' },
]

// ── Step 0: Channel + Month ──
const channels = ref([])
const channelSearch = ref('')
const selectedChannel = ref('')
const selectedMonth = ref(_prevMonth())
const chDropdownOpen = ref(false)

function _prevMonth() {
  const d = new Date()
  const m = new Date(d.getFullYear(), d.getMonth() - 1, 1)
  return m.getFullYear() + '-' + String(m.getMonth() + 1).padStart(2, '0')
}
const filteredChannels = computed(() => {
  if (!channelSearch.value) return channels.value
  const q = channelSearch.value.toLowerCase()
  return channels.value.filter(ch => ch.channel_name.toLowerCase().includes(q))
})

let chBlurTimer = null
function delayCloseChDropdown() {
  chBlurTimer = setTimeout(() => { chDropdownOpen.value = false }, 150)
}
function selectChannel(name) {
  selectedChannel.value = name
  channelSearch.value = name
  chDropdownOpen.value = false
}
function clearChannel() {
  selectedChannel.value = ''
  channelSearch.value = ''
}
function filterChannels() {
  chDropdownOpen.value = true
  if (selectedChannel.value && channelSearch.value !== selectedChannel.value) {
    selectedChannel.value = ''
  }
}

const bridgeOnline = ref(false)
const bridgeStarting = ref(false)
let _bridgeTimer = null

async function checkBridge() {
  try {
    const r = await api.getOcrStatus()
    bridgeOnline.value = r.data.online
    if (bridgeOnline.value) bridgeStarting.value = false
  } catch { bridgeOnline.value = false }
}

async function startBridge() {
  bridgeStarting.value = true
  try {
    await api.startOcrBridge()
    await checkBridge()
  } catch (e) {
    toast.error('OCR 启动失败: ' + (e.response?.data?.detail || e.message))
    bridgeStarting.value = false
  }
}

async function stopBridge() {
  try {
    await api.stopOcrBridge()
    bridgeOnline.value = false
  } catch (e) { /* ignore */ }
}

onMounted(async () => {
  try {
    const r = await api.getSettlementChannels()
    channels.value = r.data.data || []
  } catch (e) { /* ignore */ }
  checkBridge()
  _bridgeTimer = setInterval(checkBridge, 15000)
})

onUnmounted(() => {
  clearInterval(_bridgeTimer)
})

// ── Step 1: Upload & OCR ──
const fileInput = ref(null)
const dragover = ref(false)
const imageFile = ref(null)
const imagePreview = ref(null)
const ocrLoading = ref(false)
const ocrProgress = ref(0)

function triggerFile() { fileInput.value?.click() }
function handleFile(e) {
  const f = e.target.files?.[0]
  if (f) loadImage(f)
}
function handleDrop(e) {
  dragover.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f) loadImage(f)
}
function loadImage(f) {
  imageFile.value = f
  imagePreview.value = URL.createObjectURL(f)
}

// ── Step 2: Table parsing & column mapping ──
const tableData = ref([])
const columnMapping = ref([])
const colHeaders = computed(() => columnMapping.value.map(t => COL_OPTIONS.find(o => o.value === t)?.label || t))
const hasGameNameCol = computed(() => columnMapping.value.includes('game_name'))

function headerClass(ci) {
  const t = columnMapping.value[ci]
  if (t === 'ignore') return 'col-ignore'
  if (t === 'game_name') return 'col-game'
  if (t?.startsWith('amount_')) return 'col-amount'
  if (t === 'ratio') return 'col-ratio'
  if (t === 'settlement_amount') return 'col-amount'
  if (t === 'month') return 'col-month'
  return ''
}
function cellClass(ci, isHeader) { return isHeader ? headerClass(ci) : '' }

const _GAME_KEYWORDS = ['游戏', '名称', '游戏名称', '产品', '应用', '项目']
const _TOTAL_KEYWORDS = ['流水', '充值', '总金额', '原始流水', '月流水', '收入总额', '收入']
const _SETTLE_KEYWORDS = ['结算', '结算金额', '实结', '分成后']
const _RATIO_KEYWORDS = ['比例', '分成', '分成比', '分成比例', '费率']
const _MONTH_KEYWORDS = ['月份', '月', '日期', '时间', '周期']
const _AMOUNT_SPECIFIC = [
  { kw: ['代金券', '代金'], col: 'amount_vouchers' },
  { kw: ['测试', '测试费'], col: 'amount_test' },
  { kw: ['福利币', '福利'], col: 'amount_welfare' },
  { kw: ['坏账', '坏帐'], col: 'amount_bad_debt' },
]

function inferColumnType(headerText) {
  const t = headerText.trim()
  if (!t) return 'ignore'
  for (const { kw, col } of _AMOUNT_SPECIFIC) {
    if (kw.some(k => t.includes(k))) return col
  }
  if (_GAME_KEYWORDS.some(k => t.includes(k))) return 'game_name'
  if (_MONTH_KEYWORDS.some(k => t.includes(k))) return 'month'
  if (_SETTLE_KEYWORDS.some(k => t.includes(k))) return 'settlement_amount'
  if (_RATIO_KEYWORDS.some(k => t.includes(k))) return 'ratio'
  if (_TOTAL_KEYWORDS.some(k => t.includes(k))) return 'amount_total'
  return 'ignore'
}

function parseTable(words) {
  if (!words || words.length === 0) return []
  const valid = words.filter(w => w.confidence > 30 && w.text.trim())
  if (valid.length === 0) return []

  const heights = valid.map(w => w.bbox.y1 - w.bbox.y0).sort((a, b) => a - b)
  const medianH = heights[Math.floor(heights.length / 2)] || 10
  const rowThreshold = medianH * 0.6

  const sorted = [...valid].sort((a, b) => a.bbox.y0 - b.bbox.y0)
  const rows = []
  let curRow = [sorted[0]]
  let curY = sorted[0].bbox.y0
  for (let i = 1; i < sorted.length; i++) {
    if (Math.abs(sorted[i].bbox.y0 - curY) < rowThreshold) {
      curRow.push(sorted[i])
    } else {
      rows.push(curRow)
      curRow = [sorted[i]]
      curY = sorted[i].bbox.y0
    }
  }
  rows.push(curRow)

  return rows
    .map(r => r.sort((a, b) => a.bbox.x0 - b.bbox.x0).map(w => w.text.trim()))
    .filter(r => r.length > 0 && r.some(c => c))
}

function parseTableLines(lines) {
  // lines: [{text, bbox, words: [{text, bbox, confidence}]}]
  if (!lines || lines.length === 0) return []
  return lines
    .map(line => {
      if (line.words && line.words.length > 0) {
        return line.words
          .sort((a, b) => a.bbox.x0 - b.bbox.x0)
          .map(w => w.text.trim())
          .filter(t => t)
      }
      // No word-level data, try splitting line text by whitespace
      return line.text.split(/\s{2,}/).map(s => s.trim()).filter(s => s)
    })
    .filter(r => r.length > 0)
}

function parseTextFallback(text) {
  // Last resort: split full text into rows/columns
  if (!text) return []
  const lines = text.split('\n').map(l => l.trim()).filter(l => l)
  return lines
    .map(line => {
      // Split by 2+ spaces (common in OCR table output) or tabs
      const cells = line.split(/\s{2,}|\t/).map(c => c.trim()).filter(c => c)
      return cells.length > 1 ? cells : [line]  // single cell is OK as a row
    })
    .filter(r => r.length > 0)
}

async function doOCR() {
  if (!imageFile.value) return
  ocrLoading.value = true
  ocrProgress.value = 10
  try {
    const r = await api.parseOcr(imageFile.value)
    ocrProgress.value = 90
    const allWords = r.data.data || []
    console.log('OCR:', { words: allWords.length, sample: allWords.slice(0, 3) })

    let grid = parseTable(allWords)
    if (grid.length === 0) {
      toast.info('未能识别到表格数据，请尝试更清晰的图片')
      ocrLoading.value = false
      return
    }
    console.log('Parsed grid:', grid.length, 'rows x', grid[0]?.length, 'cols')

    tableData.value = grid

    // Auto-infer column types
    const nCols = grid[0].length
    const headerRow = grid[0]
    const inferred = headerRow.map(c => inferColumnType(c))

    if (!inferred.includes('game_name') && grid.length > 1) {
      for (let ci = 0; ci < nCols; ci++) {
        const samples = grid.slice(1, Math.min(grid.length, 10)).map(r => r[ci] || '')
        const nonNumeric = samples.filter(s => s && isNaN(parseFloat(s.replace(/[,%]/g, ''))))
        if (nonNumeric.length > samples.length * 0.5 && inferred[ci] === 'ignore') {
          inferred[ci] = 'game_name'
          break
        }
      }
    }
    columnMapping.value = inferred
    step.value = 2
  } catch (e) {
    logError('ocr', e)
    toast.error('OCR识别失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    ocrLoading.value = false
  }
}

// ── Step 3: Match ──
const matchRows = ref([])
const matchSummary = ref({ total: 0, high: 0, medium: 0, low: 0, none: 0 })
const gameNameColIdx = ref(-1)
const candOpenIdx = ref(-1)
const editVal = ref('')

const matchHeaders = computed(() => {
  const h = []
  columnMapping.value.forEach((t, i) => {
    if (t === 'ignore') return
    const label = COL_OPTIONS.find(o => o.value === t)?.label || t
    h.push(t === 'game_name' ? label + ' (识别→匹配)' : label)
  })
  return h
})

async function doMatch() {
  try {
    const gidx = columnMapping.value.indexOf('game_name')
    gameNameColIdx.value = gidx

    const r = await api.matchOcr({
      channel_name: selectedChannel.value,
      table_data: tableData.value,
      column_mapping: columnMapping.value,
    })

    const data = r.data
    matchSummary.value = data.summary

    // Build match header index: which position in row corresponds to which column
    const colIndices = []
    columnMapping.value.forEach((t, i) => {
      if (t !== 'ignore') colIndices.push(i)
    })
    const gidxInMatch = colIndices.indexOf(gidx)

    matchRows.value = data.rows.map(row => {
      const cells = row.cells
      const gm = row.game_match
      const out = []
      columnMapping.value.forEach((t, i) => {
        if (t === 'ignore') return
        if (t === 'game_name') {
          out.push({
            text: gm?.matched_game_name || cells.game_name || '',
            original: cells.game_name || '',
            matchedId: gm?.matched_game_id,
            confidence: gm?.confidence ?? null,
            confClass: gm?.status === 'high' ? 'conf-high'
              : (gm?.status === 'medium' ? 'conf-mid'
              : (gm?.status === 'low' ? 'conf-low' : '')),
            candidates: gm?.candidates || [],
          })
        } else {
          out.push({ text: cells[t] || '', original: cells[t] || '' })
        }
      })
      return out
    })

    step.value = 3
  } catch (e) {
    toast.error('匹配失败: ' + (e.response?.data?.detail || e.message))
  }
}

function matchCellClass(ri, ci) {
  const cell = matchRows.value[ri]?.[ci]
  if (!cell || typeof cell !== 'object') return ''
  if (cell.confClass === 'conf-high') return 'cell-high'
  if (cell.confClass === 'conf-mid') return 'cell-mid'
  if (cell.confClass === 'conf-low' || cell.confidence != null && cell.confidence < 70)
    return 'cell-low'
  return ''
}

function toggleCandidates(ri) {
  if (candOpenIdx.value === ri) {
    candOpenIdx.value = -1
  } else {
    candOpenIdx.value = ri
    editVal.value = matchRows.value[ri]?.[gameNameColIdx.value]?.text || ''
  }
}

function pickCandidate(ri, candidate) {
  const cell = matchRows.value[ri][gameNameColIdx.value]
  cell.text = candidate.game_name
  cell.matchedId = candidate.game_id
  cell.confidence = candidate.score
  cell.confClass = candidate.score >= 90 ? 'conf-high' : (candidate.score >= 70 ? 'conf-mid' : 'conf-low')
  candOpenIdx.value = -1
}

function finishEdit(ri) {
  if (matchRows.value[ri] && matchRows.value[ri][gameNameColIdx.value]) {
    const cell = matchRows.value[ri][gameNameColIdx.value]
    cell.text = editVal.value
    cell.matchedId = null
    cell.confidence = null
    cell.confClass = 'conf-manual'
  }
  candOpenIdx.value = -1
}

// ── Step 4: Save ──
const saveMsg = ref('')
const saveError = ref(false)

async function doSave() {
  try {
    const gidx = gameNameColIdx.value
    const updates = []
    const monthColIdx = columnMapping.value.indexOf('month')

    for (const row of matchRows.value) {
      const gc = row[gidx]
      if (!gc || !gc.text) continue

      const month = monthColIdx >= 0
        ? (typeof row[monthColIdx]?.text === 'string' ? row[monthColIdx].text : (row[monthColIdx]?.text || ''))
        : ''

      const getVal = (type) => {
        const idx = columnMapping.value.indexOf(type)
        if (idx < 0) return 0
        const v = row[idx]?.text
        const n = parseFloat(String(v || '').replace(/[,%]/g, ''))
const toast = useToast()
        return isNaN(n) ? 0 : n
      }

      updates.push({
        channel_name: selectedChannel.value,
        game_id: gc.matchedId || gc.text,
        month: month || selectedMonth.value,
        vouchers: getVal('amount_vouchers'),
        test: getVal('amount_test'),
        welfare: getVal('amount_welfare'),
        bad_debt: getVal('amount_bad_debt'),
      })
    }

    if (updates.length === 0) {
      toast.info('没有可保存的数据')
      return
    }

    await api.batchDeductions(updates)
    saveMsg.value = `成功保存 ${updates.length} 条扣除数据！`
    saveError.value = false
    step.value = 4
  } catch (e) {
    saveMsg.value = '保存失败: ' + (e.response?.data?.detail || e.message)
    saveError.value = true
  }
}

function resetAll() {
  step.value = 0
  imageFile.value = null
  imagePreview.value = null
  tableData.value = []
  columnMapping.value = []
  matchRows.value = []
  saveMsg.value = ''
  selectedChannel.value = ''
  selectedMonth.value = _prevMonth()
  channelSearch.value = ''
}
</script>

<style scoped>
.ocr-page { max-width: 1200px; margin: 0 auto; padding: 20px; }
.ocr-page h2 { margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
.bridge-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.bridge-dot.on { background: var(--color-success); box-shadow: 0 0 4px var(--color-success); }
.bridge-dot.off { background: var(--border-dashed); }
.bridge-dot.starting { background: var(--color-warning); animation: pulse 1s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.starting-text { font-size: 13px; color: var(--color-warning); font-weight: normal; }
.badge.beta { font-size: 11px; background: var(--color-warning); color: var(--text-on-primary); padding: 2px 8px; border-radius: 10px; font-weight: 600; vertical-align: middle; }
.beta-notice { background: var(--bg-tag-yellow); border: 1px solid var(--color-warning); color: var(--color-warning); padding: 10px 14px; border-radius: 6px; font-size: 13px; margin-bottom: 16px; }
.beta-notice a { color: var(--color-info); font-weight: 600; }
.btn.tiny { padding: 3px 10px; font-size: 12px; }
.btn.tiny.danger { border-color: var(--color-danger); color: var(--color-danger); }

/* Steps */
.steps { display: flex; align-items: center; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; }
.step { padding: 6px 14px; border-radius: 16px; background: var(--border-light); color: var(--text-light); font-size: 13px; }
.step.active { background: var(--color-info); color: var(--bg-card); font-weight: 600; }
.step-arrow { color: #ccc; }

/* Sections */
.section { background: var(--bg-card); border-radius: 8px; padding: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.section label { display: block; margin-bottom: 8px; font-weight: 500; }
.hint { color: var(--text-muted); margin-bottom: 12px; font-size: 13px; }
.step-actions { display: flex; gap: 12px; margin-top: 16px; }

/* Combobox (searchable channel) */
.combobox { position: relative; margin-bottom: 16px; }
.combobox-input { width: 100%; max-width: 400px; padding: 8px 12px; border: 1px solid var(--border-dashed); border-radius: 4px; font-size: 14px; }
.combobox-input:focus { border-color: var(--color-info); outline: none; box-shadow: 0 0 0 2px rgba(24,144,255,.2); }
.combobox-clear { position: absolute; right: calc(100% - 390px); top: 8px; cursor: pointer; color: var(--text-light); font-size: 16px; }
.combobox-list { position: absolute; top: 100%; left: 0; right: 0; max-width: 400px; max-height: 200px; overflow-y: auto; background: var(--bg-card); border: 1px solid var(--border-dashed); border-top: none; border-radius: 0 0 4px 4px; list-style: none; padding: 0; margin: 0; z-index: 10; box-shadow: 0 4px 8px rgba(0,0,0,.1); }
.combobox-list li { padding: 8px 12px; cursor: pointer; font-size: 13px; }
.combobox-list li:hover, .combobox-list li.active { background: var(--bg-input-focus); }
.combobox-list li.no-match { color: var(--text-light); cursor: default; }

/* Step 0 layout */
.step0-row { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 16px; }
.step0-field { flex: 1; min-width: 280px; }
.month-input { padding: 8px 12px; border: 1px solid var(--border-dashed); border-radius: 4px; font-size: 14px; width: 100%; max-width: 280px; }

/* Dropzone */
.dropzone { border: 2px dashed var(--border-dashed); border-radius: 8px; padding: 40px; text-align: center; cursor: pointer; transition: .2s; }
.dropzone:hover, .dropzone.dragover { border-color: var(--color-info); background: var(--bg-input-focus); }
.dropzone-hint { color: var(--text-light); display: flex; flex-direction: column; align-items: center; gap: 8px; }
.dropzone-icon { font-size: 40px; }
.preview-img { max-width: 100%; max-height: 400px; object-fit: contain; }

/* Table */
.table-wrap { overflow-x: auto; max-height: 500px; overflow-y: auto; border: 1px solid var(--border-light); border-radius: 4px; }
.ocr-table { border-collapse: collapse; width: 100%; font-size: 13px; }
.ocr-table th, .ocr-table td { padding: 6px 12px; border: 1px solid var(--border-light); white-space: nowrap; min-width: 80px; }
.ocr-table thead { position: sticky; top: 0; background: var(--palette-gray-50); z-index: 5; }

/* Column header colors */
.col-game { background: var(--bg-input-focus) !important; }
.col-amount { background: var(--bg-tag-green) !important; }
.col-ratio { background: var(--bg-tag-blue) !important; }
.col-month { background: var(--bg-tag-yellow) !important; }
.col-ignore { background: var(--palette-gray-50) !important; color: var(--text-light); }

.col-select { padding: 2px 4px; font-size: 12px; border: 1px solid var(--border-dashed); border-radius: 2px; background: var(--bg-card); max-width: 130px; }

/* Match confidence */
.match-summary { margin-bottom: 12px; display: flex; gap: 8px; align-items: center; }
.badge { padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; }
.badge.green { background: var(--bg-tag-green); color: var(--color-success); }
.badge.yellow { background: var(--bg-tag-yellow); color: var(--color-warning); }
.badge.red { background: var(--bg-row-danger); color: var(--color-danger); }
.badge.gray { background: var(--palette-gray-50); color: var(--text-light); }

.cell-high { background: var(--bg-tag-green); }
.cell-mid { background: var(--bg-tag-yellow); }
.cell-low { background: var(--bg-row-danger); }

.game-cell { display: flex; align-items: center; gap: 4px; cursor: pointer; min-height: 24px; }
.game-cell:hover { background: rgba(24,144,255,.05); }

.conf-tag { font-size: 11px; padding: 1px 6px; border-radius: 8px; }
.conf-high { background: var(--bg-tag-green); color: var(--color-success); }
.conf-mid { background: var(--bg-tag-yellow); color: var(--color-warning); }
.conf-low { background: var(--bg-badge-error); color: var(--color-danger); }
.conf-manual { background: var(--border-dashed); color: var(--text-secondary); }

.cand-arrow { color: var(--color-info); font-size: 12px; margin-left: auto; }
.cand-list { position: absolute; background: var(--bg-card); border: 1px solid var(--border-dashed); border-radius: 4px; list-style: none; padding: 4px 0; margin: 0; z-index: 10; box-shadow: 0 4px 8px rgba(0,0,0,.1); min-width: 200px; }
.cand-list li { padding: 6px 12px; cursor: pointer; font-size: 13px; display: flex; justify-content: space-between; }
.cand-list li:hover, .cand-list li.selected { background: var(--bg-input-focus); }
.cand-score { color: var(--text-light); font-size: 11px; }

.cell-edit { width: 100%; padding: 2px 4px; border: 1px solid var(--color-info); border-radius: 2px; font-size: 13px; }

/* Buttons */
.btn { padding: 8px 20px; border: 1px solid var(--border-dashed); border-radius: 4px; background: var(--bg-card); cursor: pointer; font-size: 13px; }
.btn.primary { background: var(--color-info); color: var(--bg-card); border-color: var(--color-info); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn.primary:hover:not(:disabled) { background: var(--color-info); border-color: var(--color-info); }

.save-result { padding: 16px; border-radius: 4px; background: var(--bg-tag-green); color: var(--color-success); font-size: 15px; margin-bottom: 16px; }
.save-result.error { background: var(--bg-row-danger); color: var(--color-danger); }
</style>
