<template>
  <div class="data-import">
    <h2>数据导入</h2>

    <div class="import-panel">
      <div class="form-row">
        <label>选择模板类型:</label>
        <select v-model="templateType">
          <option value="">-- 请选择 --</option>
          <option v-for="t in templates" :key="t.type" :value="t.type">{{ t.label }}</option>
        </select>
        <AppButton v-if="templateType" variant="default" size="sm" @click="downloadTemplate">下载空白模板</AppButton>
      </div>
      <div class="form-row" v-if="templateType">
        <label>上传文件:</label>
        <input type="file" accept=".xlsx" @change="onFileChange" ref="fileInput" />
        <AppButton variant="primary" size="sm" @click="preview" :disabled="!selectedFile">预览</AppButton>
      </div>
    </div>

    <!-- Error message -->
    <div v-if="errorMessage" class="errors-box">
      <h4>错误</h4>
      <pre style="white-space: pre-wrap; font-size: 13px; margin: 0;">{{ errorMessage }}</pre>
    </div>

    <!-- Preview -->
    <div v-if="previewResult" class="preview-section">
      <div class="preview-header">
        <span class="preview-summary">共 <strong>{{ previewResult.total_rows }}</strong> 行数据</span>
        <span v-if="previewResult.has_conflict" class="conflict-warn">
          检测到 <strong>{{ previewResult.conflict_count }}</strong> 条重复数据
        </span>
        <span v-if="!previewResult.errors.length && !previewResult.has_conflict" class="ok-badge">校验通过</span>
      </div>

      <!-- Errors -->
      <div v-if="previewResult.errors.length" class="errors-box">
        <h4>校验错误 ({{ previewResult.errors.length }} 条)</h4>
        <div v-for="e in previewResult.errors" :key="e.row" class="error-item">
          <strong>第 {{ e.row }} 行:</strong>
          <span v-if="e.errors">{{ e.errors.join('; ') }}</span>
          <span v-if="e.error">{{ e.error }}</span>
        </div>
      </div>

      <!-- Preview grid -->
      <div v-if="previewResult.preview_rows.length" class="preview-grid">
        <h4>预览 (前 5 行)</h4>
        <div class="excel-wrapper">
          <ag-grid-vue
            :rowData="previewRowsWithNo"
            :columnDefs="previewColsWithNo"
            class="ag-theme-quartz"
            domLayout="autoHeight"
            :defaultColDef="{ resizable: true, sortable: false, filter: false }"
            :headerHeight="32"
            :rowHeight="28"
            :enableCellTextSelection="true"
          />
        </div>
      </div>

      <!-- Confirm -->
      <div class="confirm-row" v-if="!previewResult.errors.length">
        <label v-if="previewResult.has_conflict">
          <input type="checkbox" v-model="overwrite" /> 覆盖已存在的重复数据
        </label>
        <label v-if="templateType === 'raw_transactions'">
          <input type="checkbox" v-model="accumulate" /> 累计导入（追加到已有数据，不覆盖）
        </label>
        <AppButton variant="success" size="sm" @click="confirmImport">确认导入</AppButton>
      </div>
    </div>

    <!-- Result -->
    <div v-if="importResult" class="result-box">
      成功导入 {{ importResult.imported }} 条数据
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import api from '../api'

const templates = ref([])
const templateType = ref('')
const selectedFile = ref(null)
const previewResult = ref(null)
const overwrite = ref(false)
const accumulate = ref(false)
watch(templateType, () => { accumulate.value = false; errorMessage.value = '' })
const importResult = ref(null)
const fileInput = ref(null)
const errorMessage = ref('')

onMounted(async () => {
  const r = await api.getTemplates()
  templates.value = r.data.templates
})

function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
  previewResult.value = null
  importResult.value = null
  errorMessage.value = ''
}

function downloadTemplate() {
  api.downloadTemplate(templateType.value).then(r => {
    const url = URL.createObjectURL(new Blob([r.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = `${templateType.value}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  }).catch(e => {
    errorMessage.value = '下载模板失败: ' + (e.response?.data?.detail || e.message)
  })
}

async function preview() {
  if (!templateType.value || !selectedFile.value) return
  errorMessage.value = ''
  try {
    const r = await api.previewImport(templateType.value, selectedFile.value)
    previewResult.value = r.data
  } catch (e) {
    const detail = e.response?.data?.detail
    if (typeof detail === 'string') {
      errorMessage.value = detail
    } else if (detail?.errors) {
      errorMessage.value = detail.errors.map(er => `第${er.row}行: ${er.error || er.errors?.join('; ')}`).join('\n')
    } else {
      errorMessage.value = '预览失败: ' + (e.message || '未知错误')
    }
  }
}

async function confirmImport() {
  errorMessage.value = ''
  if (!templateType.value || !selectedFile.value) return
  try {
    const overwriteFlag = templateType.value === 'raw_transactions' ? !accumulate.value : overwrite.value
    const r = await api.confirmImport(templateType.value, selectedFile.value, overwriteFlag)
    importResult.value = r.data
    previewResult.value = null
  } catch (e) {
    const detail = e.response?.data?.detail
    if (typeof detail === 'string') {
      errorMessage.value = detail
    } else if (detail?.errors) {
      errorMessage.value = detail.errors.map(er => `第${er.row}行: ${er.error || er.errors?.join('; ')}`).join('\n')
    } else {
      errorMessage.value = '导入失败: ' + (e.message || '未知错误')
    }
  }
}

const previewCols = computed(() => {
  const t = templates.value.find(t => t.type === templateType.value)
  if (!t) return []
  return t.columns.map(c => ({ field: c, headerName: c }))
})

const previewColsWithNo = computed(() => {
  const cols = [
    {
      field: '_rowNo', headerName: '', width: 40,
      pinned: 'left',
      valueFormatter: p => (p.node?.rowIndex ?? 0) + 1,
      cellStyle: { color: 'var(--text-light)', backgroundColor: '#f8f8f8', textAlign: 'center', borderRight: '1px solid var(--border-header-cell)' },
      resizable: false,
    },
    ...previewCols.value.map((c, i) => ({
      ...c,
      cellStyle: { borderRight: '1px solid var(--border-cell)' },
      headerName: `${String.fromCharCode(65 + i)} / ${c.headerName}`,
    })),
  ]
  return cols
})

const previewRowsWithNo = computed(() => {
  return (previewResult.value?.preview_rows || []).map((row, i) => ({ _rowNo: i + 1, ...row }))
})
</script>

<style scoped>
h2 { margin-bottom: 16px; font-size: 20px; }
.import-panel { background: var(--bg-card); padding: 16px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); margin-bottom: 16px; }
.form-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.form-row label { min-width: 100px; font-size: 14px; }
select, input[type=file] { padding: 6px 10px; border: 1px solid var(--border-default); border-radius: 4px; font-size: 13px; }
button { padding: 6px 16px; border: 1px solid var(--border-default); border-radius: 6px; cursor: pointer; font-size: 13px; background: var(--bg-card); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-download { background: var(--bg-tag-blue); border-color: var(--color-info); }
.btn-preview { background: var(--color-primary); color: var(--bg-card); border-color: var(--color-primary); }

.preview-section { background: var(--bg-card); padding: 16px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); margin-bottom: 16px; }
.preview-header { display: flex; gap: 16px; margin-bottom: 12px; font-size: 14px; align-items: center; }
.preview-summary { color: var(--text-primary); }
.conflict-warn { color: var(--color-warning); font-weight: 600; }
.ok-badge { color: var(--color-success); font-weight: 600; font-size: 12px; background: var(--bg-badge-ok); padding: 2px 10px; border-radius: 10px; }

.excel-wrapper { border: 1px solid var(--border-header-cell); border-radius: 4px; overflow: hidden; }
:deep(.ag-cell) { border-right: 1px solid var(--border-cell); border-bottom: 1px solid var(--border-light); }
:deep(.ag-header-cell) { border-right: 1px solid var(--border-header-cell); font-weight: 600; background: var(--palette-gray-50); }

.errors-box { background: var(--bg-row-danger); border: 1px solid var(--color-danger); padding: 12px; border-radius: 6px; margin-bottom: 12px; }
.errors-box h4 { color: var(--color-danger); margin-bottom: 8px; font-size: 14px; }
.error-item { font-size: 13px; margin-bottom: 4px; }
.preview-grid { margin-bottom: 12px; }
.preview-grid h4 { margin-bottom: 8px; font-size: 14px; }
.confirm-row { display: flex; align-items: center; gap: 16px; margin-top: 12px; }
.confirm-row label { font-size: 14px; display: flex; align-items: center; gap: 6px; cursor: pointer; }
.btn-confirm { background: var(--color-success); color: var(--bg-card); border-color: var(--color-success); padding: 8px 24px; font-size: 14px; }
.result-box { background: var(--bg-badge-ok); padding: 16px; border-radius: 8px; font-size: 15px; }
</style>
