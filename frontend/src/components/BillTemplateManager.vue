<template>
  <div class="bill-template-manager">
    <div class="section-header">
      <h3>对账单模板</h3>
      <AppButton variant="info" size="md" @click="showUpload = true">+ 上传模板</AppButton>
    </div>
    <table class="list-table" v-if="templates.length">
      <thead>
        <tr>
          <th>名称</th>
          <th>适用类型</th>
          <th>默认</th>
          <th>描述</th>
          <th>更新时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in templates" :key="t.id">
          <td><strong>{{ t.name }}</strong></td>
          <td><span class="tag">{{ TYPE_LABEL[t.bill_type] || t.bill_type }}</span></td>
          <td>{{ t.is_default ? '✓' : '-' }}</td>
          <td class="muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            {{ t.description || '-' }}
          </td>
          <td class="muted" style="font-size:12px">{{ t.updated_at?.slice(0, 10) }}</td>
          <td>
            <AppButton variant="default" size="sm" @click="download(t)">下载</AppButton>
            <AppButton variant="default" size="sm" @click="editMeta(t)">编辑</AppButton>
            <AppButton variant="danger" size="sm" @click="confirmDelete(t)">删除</AppButton>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">暂无对账模板，点击上方"上传模板"创建</p>

    <!-- Upload modal -->
    <AppModal v-model="showUpload" title="上传对账模板" width="480px">
      <div class="form-group">
        <label class="form-label">模板名称</label>
        <input v-model="form.name" class="form-input" placeholder="如：华为渠道对账单" />
      </div>
      <div class="form-group">
        <label class="form-label">适用类型</label>
        <select v-model="form.bill_type" class="form-select">
          <option value="income">收入结算</option>
          <option value="payment">付款结算</option>
          <option value="all">通用（收入+付款）</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">描述（可选）</label>
        <input v-model="form.description" class="form-input" placeholder="用途说明" />
      </div>
      <div class="form-group">
        <label class="form-label">模板文件 (.xlsx)</label>
        <input type="file" ref="fileInput" accept=".xlsx,.xls" @change="onFileChange" />
      </div>
      <div class="form-group" style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" id="tplDefault" v-model="form.is_default" class="form-checkbox" />
        <label for="tplDefault" style="margin:0;font-size:var(--text-base)">设为默认模板</label>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <template #footer>
        <AppButton variant="default" @click="showUpload = false; resetForm()">取消</AppButton>
        <AppButton variant="primary" :disabled="saving || !form.name || !file" :loading="saving" @click="doUpload">确认上传</AppButton>
      </template>
    </AppModal>

    <!-- Edit metadata modal -->
    <AppModal v-model="showEdit" title="编辑模板" width="480px">
      <div class="form-group">
        <label class="form-label">模板名称</label>
        <input v-model="form.name" class="form-input" />
      </div>
      <div class="form-group">
        <label class="form-label">适用类型</label>
        <select v-model="form.bill_type" class="form-select">
          <option value="income">收入结算</option>
          <option value="payment">付款结算</option>
          <option value="all">通用（收入+付款）</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">描述</label>
        <input v-model="form.description" class="form-input" />
      </div>
      <div class="form-group" style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" id="tplDefaultEdit" v-model="form.is_default" class="form-checkbox" />
        <label for="tplDefaultEdit" style="margin:0;font-size:var(--text-base)">设为默认模板</label>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <template #footer>
        <AppButton variant="default" @click="showEdit = false; resetForm()">取消</AppButton>
        <AppButton variant="primary" :disabled="saving || !form.name" :loading="saving" @click="doSaveMeta">保存</AppButton>
      </template>
    </AppModal>

    <!-- Delete confirm -->
    <AppModal v-model="showDel" title="确认删除">
      <p>确定删除模板「{{ delTarget?.name }}」？此操作不可恢复。</p>
      <template #footer>
        <AppButton variant="default" @click="showDel = false">取消</AppButton>
        <AppButton variant="danger" :disabled="saving" @click="doDelete">确认删除</AppButton>
      </template>
    </AppModal>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../api/index.js'
import { useToast } from './AppToast/useToast.js'

const toast = useToast()
const TYPE_LABEL = { income: '收入结算', payment: '付款结算', all: '通用' }

const templates = ref([])
const showUpload = ref(false)
const showEdit = ref(false)
const showDel = ref(false)
const delTarget = ref(null)
const saving = ref(false)
const file = ref(null)
const fileInput = ref(null)
const error = ref('')
const form = reactive({
  name: '',
  description: '',
  bill_type: 'income',
  is_default: false,
  _editId: null,
})

function resetForm() {
  form.name = ''
  form.description = ''
  form.bill_type = 'income'
  form.is_default = false
  form._editId = null
  file.value = null
  error.value = ''
}

function onFileChange(e) {
  file.value = e.target.files[0] || null
}

async function fetchTemplates() {
  try {
    const r = await api.getBillTemplates()
    templates.value = r.data.data || []
  } catch (e) { /* silently fail */ }
}

async function doUpload() {
  if (!form.name || !file.value) return
  saving.value = true
  error.value = ''
  try {
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('description', form.description || '')
    fd.append('bill_type', form.bill_type)
    fd.append('is_default', String(form.is_default))
    fd.append('file', file.value)
    await api.createBillTemplate(fd)
    showUpload.value = false
    resetForm()
    fetchTemplates()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}

function editMeta(t) {
  form.name = t.name
  form.description = t.description || ''
  form.bill_type = t.bill_type
  form.is_default = t.is_default
  form._editId = t.id
  showEdit.value = true
}

async function doSaveMeta() {
  if (!form.name || !form._editId) return
  saving.value = true
  error.value = ''
  try {
    await api.updateBillTemplate(form._editId, {
      name: form.name,
      description: form.description || '',
      bill_type: form.bill_type,
      is_default: form.is_default,
    })
    showEdit.value = false
    resetForm()
    fetchTemplates()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    saving.value = false
  }
}

function confirmDelete(t) {
  delTarget.value = t
  showDel.value = true
}

async function doDelete() {
  if (!delTarget.value) return
  saving.value = true
  try {
    await api.deleteBillTemplate(delTarget.value.id)
    showDel.value = false
    delTarget.value = null
    fetchTemplates()
  } catch (e) {
    toast.error('删除失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function download(t) {
  try {
    const r = await api.downloadBillTemplate(t.id)
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a')
    a.href = url
    a.download = t.name + '.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    toast.error('下载失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(() => {
  fetchTemplates()
})
</script>
