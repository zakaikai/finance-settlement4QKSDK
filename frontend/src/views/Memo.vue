<template>
  <div class="memo-page">
    <div class="memo-sidebar">
      <div class="sidebar-header">
        <h2>备忘录</h2>
        <div class="sidebar-header-actions">
          <button class="btn-drawer-toggle" @click="showDrawer = true" title="提醒列表">
            🔔<span v-if="reminderCount" class="reminder-badge">{{ reminderCount }}</span>
          </button>
          <AppButton variant="info" size="sm" @click="startCreate">+ 新建</AppButton>
        </div>
      </div>
      <div class="memo-list">
        <div
          v-for="m in memos"
          :key="m.id"
          :class="['memo-item', { active: editingId === m.id }]"
          @click="selectMemo(m)"
        >
          <div class="memo-item-title">{{ m.title }}</div>
          <div class="memo-item-meta">
            <span v-if="m.is_reminder" class="reminder-indicator">🔔</span>
            <span v-if="m.party_name" class="party-tag">{{ m.party_name }}</span>
            <span v-if="m.has_attachment" class="attach-indicator">📎</span>
            <span class="memo-date">{{ m.updated_at?.slice(0, 10) }}</span>
          </div>
        </div>
        <div v-if="!memos.length && !loading" class="empty">暂无备忘录</div>
        <div v-if="loading" class="empty">加载中...</div>
      </div>
    </div>

    <div class="memo-editor">
      <template v-if="editingId">
        <div class="editor-header">
          <input v-model="form.title" class="input-title" placeholder="标题" />
          <div class="editor-actions">
            <AppButton variant="success" size="sm" @click="saveMemo" :disabled="saving || !form.title.trim()" :loading="saving">保存</AppButton>
            <AppButton variant="default" size="sm" @click="cancelEdit">取消</AppButton>
            <AppButton variant="danger" size="sm" @click="deleteMemo">删除</AppButton>
          </div>
        </div>

        <div class="editor-body">
          <div class="form-row">
            <label>关联商户类型</label>
            <select v-model="form.party_type">
              <option value="">-- 不关联 --</option>
              <option value="channel">渠道</option>
              <option value="publisher">研发</option>
            </select>
          </div>
          <div class="form-row">
            <label>关联商户名称</label>
            <input v-model="form.party_name" placeholder="输入商户名称" />
          </div>
          <div class="form-row">
            <label>内容</label>
            <textarea v-model="form.content" @input="autoResize" placeholder="备忘内容..."></textarea>
          </div>
          <div class="form-row">
            <label class="checkbox-label">
              <input type="checkbox" v-model="form.is_reminder" />
              设为提醒
            </label>
            <select v-if="form.is_reminder" v-model="form.reminder_cycle" class="input-cycle">
              <option value="none">无周期</option>
              <option value="daily">每天</option>
              <option value="weekly">每周</option>
              <option value="monthly">每月</option>
              <option value="yearly">每年</option>
            </select>
          </div>
          <div class="form-row">
            <label>附件</label>
            <div class="attach-row">
              <input type="file" ref="fileInput" @change="onFileChange" />
              <span v-if="form.attachment_name" class="attach-name">
                {{ form.attachment_name }}
                <a v-if="editingId && form.has_attachment" :href="attachmentUrl(editingId)" target="_blank" class="btn-download">下载</a>
              </span>
            </div>
          </div>
        </div>
      </template>

      <div v-else class="editor-placeholder">
        <p>选择左侧备忘录查看详情，或点击"新建"创建</p>
      </div>
    </div>

    <ReminderDrawer
      :visible="showDrawer"
      :memos="memos"
      @close="showDrawer = false"
      @select-memo="selectFromDrawer"
      @refresh="loadMemos"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import ReminderDrawer from './ReminderDrawer.vue'
import { useToast } from '../components/AppToast/useToast'

const memos = ref([])
const loading = ref(false)
const editingId = ref(null)
const showDrawer = ref(false)

const reminderCount = computed(() => memos.value.filter(m => m.is_reminder).length)
const saving = ref(false)
const fileInput = ref(null)
const selectedFile = ref(null)
function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
  if (selectedFile.value) {
    form.value.attachment_name = selectedFile.value.name
  }
}

function autoResize(e) {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

const form = ref({
  title: '',
  content: '',
  party_type: '',
  party_name: '',
  attachment_name: '',
  has_attachment: false,
  is_reminder: false,
  reminder_cycle: 'none',
})

async function loadMemos() {
  loading.value = true
  try {
    const r = await api.getMemos()
    memos.value = r.data.data
  } catch (e) { /* ignore */ }
  loading.value = false
}

function attachmentUrl(id) {
  return api.getMemoAttachmentUrl(id)
}

function resetForm() {
  form.value = { title: '', content: '', party_type: '', party_name: '', attachment_name: '', has_attachment: false, is_reminder: false, reminder_cycle: 'none' }
  selectedFile.value = null
}

function selectMemo(m) {
  editingId.value = m.id
  form.value = { ...m }
  selectedFile.value = null
}

function selectFromDrawer(m) {
  showDrawer.value = false
  selectMemo(m)
}

function startCreate() {
  editingId.value = '_new'
  resetForm()
}

function cancelEdit() {
  if (editingId.value === '_new') {
    editingId.value = null
  } else {
    const m = memos.value.find(x => x.id === editingId.value)
    if (m) selectMemo(m)
    else editingId.value = null
  }
}

async function saveMemo() {
  if (!form.value.title.trim()) return
  saving.value = true
  try {
    const fd = new FormData()
    fd.append('title', form.value.title.trim())
    fd.append('content', form.value.content || '')
    fd.append('party_type', form.value.party_type || '')
    fd.append('party_name', form.value.party_name || '')
    fd.append('is_reminder', form.value.is_reminder ? 'true' : 'false')
    fd.append('reminder_cycle', form.value.reminder_cycle || 'none')
    if (selectedFile.value) {
      fd.append('file', selectedFile.value)
    }

    if (editingId.value === '_new') {
      const r = await api.createMemo(fd)
      await loadMemos()
      const created = r.data.data
const toast = useToast()
      editingId.value = created.id
      form.value = { ...created }
    } else {
      await api.updateMemo(editingId.value, fd)
      await loadMemos()
      form.value.has_attachment = true
    }
    selectedFile.value = null
  } catch (e) {
    toast.error('保存失败: ' + (e.response?.data?.detail || e.message))
  }
  saving.value = false
}

async function deleteMemo() {
  if (!confirm('确定删除这条备忘录？')) return
  try {
    await api.deleteMemo(editingId.value)
    editingId.value = null
    resetForm()
    await loadMemos()
  } catch (e) {
    toast.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(loadMemos)
</script>

<style scoped>
.memo-page {
  display: flex;
  gap: 16px;
  height: calc(100vh - 56px - 56px); /* header + padding */
  min-height: 400px;
}

/* Sidebar */
.memo-sidebar {
  width: 300px;
  flex-shrink: 0;
  background: var(--bg-card);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border-cell);
}
.sidebar-header h2 { font-size: 16px; }
.sidebar-header-actions { display: flex; align-items: center; gap: 8px; }
.btn-drawer-toggle {
  position: relative; width: 32px; height: 32px; border: 1px solid var(--border-default);
  border-radius: 6px; background: var(--bg-card); cursor: pointer; font-size: 14px;
  display: flex; align-items: center; justify-content: center;
}
.btn-drawer-toggle:hover { background: var(--palette-gray-50); }
.reminder-badge {
  position: absolute; top: -6px; right: -6px;
  min-width: 18px; height: 18px; line-height: 18px; text-align: center;
  background: var(--color-danger); color: var(--bg-card); font-size: 11px; font-weight: 700;
  border-radius: 9px; padding: 0 4px;
}
.reminder-indicator { font-size: 11px; }
.btn-add {
  padding: 4px 12px; background: var(--color-primary); color: var(--bg-card);
  border: none; border-radius: 4px; font-size: 13px; cursor: pointer;
}
.btn-add:hover { background: var(--color-primary-dark); }
.memo-list { flex: 1; overflow-y: auto; }
.memo-item {
  padding: 12px 16px; border-bottom: 1px solid var(--border-light);
  cursor: pointer; transition: background 0.1s;
}
.memo-item:hover { background: var(--bg-tag-blue); }
.memo-item.active { background: var(--bg-tag-blue); border-left: 3px solid var(--color-primary); }
.memo-item-title { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.memo-item-meta { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-light); }
.party-tag { background: var(--bg-tag-blue); color: var(--color-info); padding: 1px 6px; border-radius: 3px; }
.attach-indicator { font-size: 12px; }
.memo-date { margin-left: auto; }
.empty { padding: 32px; text-align: center; color: var(--text-light); font-size: 13px; }

/* Editor */
.memo-editor {
  flex: 1;
  background: var(--bg-card);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 24px;
  overflow-y: auto;
}
.editor-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}
.input-title {
  flex: 1;
  font-size: 18px;
  font-weight: 700;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 8px 12px;
  outline: none;
}
.input-title:focus { border-color: var(--color-primary); }
.editor-actions { display: flex; gap: 8px; flex-shrink: 0; }
.btn-save {
  padding: 6px 16px; background: var(--color-success); color: var(--bg-card);
  border: none; border-radius: 4px; font-size: 13px; cursor: pointer;
}
.btn-save:disabled { background: var(--text-light); cursor: not-allowed; }
.btn-discard {
  padding: 6px 14px; background: var(--bg-card); border: 1px solid var(--border-default);
  border-radius: 4px; font-size: 13px; cursor: pointer;
}
.btn-delete {
  padding: 6px 14px; background: var(--bg-card); border: 1px solid var(--color-danger);
  color: var(--color-danger); border-radius: 4px; font-size: 13px; cursor: pointer;
}
.btn-delete:hover { background: var(--color-danger); color: var(--bg-card); }

.editor-body { max-width: 900px; }
.form-row { margin-bottom: 14px; }
.form-row label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; font-weight: 600; }
.form-row select, .form-row input {
  width: 100%; padding: 7px 10px; border: 1px solid var(--border-default);
  border-radius: 4px; font-size: 13px; outline: none;
}
.form-row select:focus, .form-row input:focus { border-color: var(--color-primary); }
.form-row textarea {
  width: 100%; min-height: 100px; padding: 8px 10px; border: 1px solid var(--border-default);
  border-radius: 4px; font-size: 13px; outline: none; resize: vertical; font-family: inherit;
  box-sizing: border-box;
}
.form-row textarea:focus { border-color: var(--color-primary); }
.checkbox-label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 13px; color: var(--text-secondary); }
.checkbox-label input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; margin: 0; }
.input-cycle { width: 120px; padding: 6px 8px; border: 1px solid var(--border-default); border-radius: 4px; font-size: 13px; outline: none; margin-top: 6px; }
.attach-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.attach-name { font-size: 13px; color: var(--text-secondary); display: flex; align-items: center; gap: 8px; }
.btn-download { color: var(--color-info); text-decoration: underline; font-size: 12px; }

.editor-placeholder {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--text-light); font-size: 14px;
}
</style>
