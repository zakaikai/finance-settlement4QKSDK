<template>
  <div class="system">
    <h2>系统管理</h2>

    <div class="tabs">
      <button v-for="t in tabs" :key="t.key" :class="['tab-item', { 'tab-active': activeTab === t.key }]" @click="activeTab = t.key">
        {{ t.label }}
      </button>
    </div>

    <!-- ── Status ── -->
    <div v-if="activeTab === 'status'" class="tab-content">
      <div class="section">
        <h3>数据库状态</h3>
        <table class="info-table">
          <tr><td>路径</td><td><code>{{ status.db_path }}</code></td></tr>
          <tr><td>数据库文件</td><td>{{ status.exists ? '存在' : '不存在' }}</td></tr>
          <tr><td>大小</td><td>{{ status.size_display }}</td></tr>
          <tr><td>修改时间</td><td>{{ status.modified_at || '-' }}</td></tr>
        </table>
      </div>

      <div class="section">
        <h3>表记录数</h3>
        <table class="info-table" v-if="status.table_counts">
          <tr v-for="(cnt, name) in status.table_counts" :key="name">
            <td>{{ name }}</td>
            <td class="num">{{ cnt }}</td>
          </tr>
        </table>
        <p v-else class="muted">加载中...</p>
      </div>

      <div class="actions">
        <AppButton variant="default" size="md" @click="showBackupModal = true">创建备份</AppButton>
        <AppButton variant="danger" size="md" @click="showResetConfirm = true">重置数据库</AppButton>
      </div>

      <div class="section" style="margin-top:24px;border-top:1px solid var(--border-light);padding-top:20px">
        <h3>局域网分享</h3>
        <label class="toggle-row">
          <span>允许局域网其他设备查看数据</span>
          <span class="toggle-wrap">
            <input type="checkbox" v-model="lanEnabled" @change="toggleLan" />
            <span class="toggle-slider"></span>
          </span>
        </label>
        <p class="hint" style="margin-top:6px">
          {{ lanEnabled ? '已开启 — 局域网用户可访问本系统（仅查看）' : '已关闭 — 仅本机可访问' }}
        </p>
        <p v-if="lanEnabled && lanIps.length" class="hint">
          局域网地址：
          <code v-for="ip in lanIps" :key="ip" style="margin-right:8px">http://{{ ip }}:8770</code>
        </p>
      </div>

      <!-- Backup modal -->
      <AppModal v-model="showBackupModal" title="创建数据库备份">
        <p>可选：设置加密密码，带密码的备份可跨机器恢复。</p>
        <input v-model="backupPassword" type="password" class="form-input" placeholder="加密密码（可选，留空为本机加密）" @keyup.enter="doBackup" />
        <p class="hint">不设密码 → 自动密钥加密（仅限本机恢复）</p>
        <p class="hint">设密码 → PBKDF2 派生密钥加密（可跨机恢复）</p>
        <template #footer>
          <AppButton variant="default" @click="showBackupModal = false; backupPassword = ''">取消</AppButton>
          <AppButton variant="primary" :disabled="backingUp" :loading="backingUp" @click="doBackup">确认备份</AppButton>
        </template>
      </AppModal>

      <AppModal v-model="showResetConfirm" title="确认重置数据库">
        <p>此操作将<strong>清除所有数据</strong>并重建表结构。系统将先自动创建备份。</p>
        <p class="hint" style="color:var(--color-warning)">建议设置备份密码以确保备份可跨机器恢复。</p>
        <div style="margin:8px 0">
          <input v-model="resetBackupPassword" type="password" class="form-input" placeholder="备份加密密码（可选，留空为本机加密）" @keyup.enter="doReset" />
        </div>
        <p style="margin-top:12px">输入 <strong>RESET</strong> 确认：</p>
        <input v-model="resetCode" class="form-input" placeholder="RESET" @keyup.enter="doReset" />
        <template #footer>
          <AppButton variant="default" @click="showResetConfirm = false; resetBackupPassword = ''">取消</AppButton>
          <AppButton variant="danger" :disabled="resetCode !== 'RESET'" @click="doReset">确认重置</AppButton>
        </template>
      </AppModal>
    </div>

    <!-- ── Backups ── -->
    <div v-if="activeTab === 'backups'" class="tab-content">
      <div class="section-header">
        <h3>备份文件</h3>
        <AppButton variant="default" size="md" @click="showBackupModal = true">创建备份</AppButton>
      </div>
      <table class="list-table" v-if="backups.length">
        <thead>
          <tr><th>文件名</th><th>加密类型</th><th>大小</th><th>创建时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="b in backups" :key="b.filename">
            <td><code>{{ b.filename }}</code></td>
            <td><span :class="['tag', encTagClass(b.enc_type)]">{{ encTagLabel(b.enc_type) }}</span></td>
            <td class="num">{{ b.size_display }}</td>
            <td>{{ b.created_at }}</td>
            <td>
              <AppButton variant="default" size="sm" @click="confirmRestore(b)">恢复</AppButton>
              <span v-if="restoringPath === b.path" class="muted"> 确认中...</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">暂无备份文件</p>

      <!-- File upload restore (cross-PC) -->
      <div class="section" style="margin-top:24px">
        <h3>从文件恢复</h3>
        <p class="muted">选择本地的备份文件进行恢复，适用于跨机器恢复场景</p>
        <div style="display:flex;align-items:center;gap:12px">
          <input type="file" ref="fileInputRef" accept=".db,.enc.db" style="display:none" @change="onFileSelected" />
          <AppButton variant="default" size="md" @click="$refs.fileInputRef.click()">选择备份文件</AppButton>
          <span v-if="selectedFileName" style="font-size:13px;color:var(--text-primary)">{{ selectedFileName }}</span>
        </div>
        <div v-if="selectedFileName && selectedFileIsEncrypted" style="margin-top:12px">
          <AppButton variant="primary" size="md" @click="showUploadPasswordModal = true">开始恢复</AppButton>
        </div>
      </div>

      <!-- Upload restore password modal -->
      <AppModal v-model="showUploadPasswordModal" title="恢复备份">
        <p>文件: <code>{{ selectedFileName }}</code></p>
        <p class="hint">如果备份使用密码加密，请输入密码。自动密钥加密可留空。</p>
        <input v-model="uploadRestorePassword" type="password" class="form-input" placeholder="加密密码（可选）" @keyup.enter="doRestoreFromFile" />
        <template #footer>
          <AppButton variant="default" @click="showUploadPasswordModal = false; uploadRestorePassword = ''">取消</AppButton>
          <AppButton variant="primary" :disabled="restoring" :loading="restoring" @click="doRestoreFromFile">确认恢复</AppButton>
        </template>
      </AppModal>

      <!-- Restore modal (for password-encrypted backups) -->
      <AppModal v-model="showRestoreModal" title="恢复备份">
        <p>文件: <code>{{ restoreTarget?.filename }}</code></p>
        <p v-if="restoreTarget?.enc_type === 'password'">
          此备份使用密码加密，请输入创建时设置的密码：
        </p>
        <p v-else-if="restoreTarget?.enc_type === 'auto'">
          此备份为本机自动密钥加密，可直接恢复。
        </p>
        <input v-if="restoreTarget?.enc_type === 'password'" v-model="restorePassword" type="password" class="form-input" placeholder="输入加密密码" @keyup.enter="doRestore(restoreTarget?.path)" />
        <template #footer>
          <AppButton variant="default" @click="showRestoreModal = false; restorePassword = ''">取消</AppButton>
          <AppButton variant="primary" :disabled="restoring" :loading="restoring" @click="doRestore(restoreTarget?.path)">确认恢复</AppButton>
        </template>
      </AppModal>
    </div>

    <!-- ── Logs ── -->
    <div v-if="activeTab === 'logs'" class="tab-content">
      <h3>审计日志</h3>
      <table class="list-table" v-if="logs.length">
        <thead>
          <tr><th>#</th><th>操作</th><th>详情</th><th>操作人</th><th>时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="log in logs" :key="log.id">
            <td>{{ log.id }}</td>
            <td><span class="tag">{{ log.action }}</span></td>
            <td>{{ log.detail || '-' }}</td>
            <td>{{ log.user || '-' }}</td>
            <td>{{ log.created_at }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">暂无日志</p>
      <div class="pagination" v-if="logTotal > limit">
        <AppButton variant="default" size="sm" :disabled="offset === 0" @click="offset = Math.max(0, offset - limit); fetchLogs()">上一页</AppButton>
        <span>{{ Math.floor(offset / limit) + 1 }} / {{ Math.ceil(logTotal / limit) }}</span>
        <AppButton variant="default" size="sm" :disabled="offset + limit >= logTotal" @click="offset += limit; fetchLogs()">下一页</AppButton>
      </div>
    </div>

    <!-- ── Patches ── -->
    <div v-if="activeTab === 'patches'" class="tab-content">
      <div class="section-header">
        <h3>数据库迁移</h3>
        <AppButton variant="default" size="md" :disabled="patchesRunning" :loading="patchesRunning" @click="runPatches">运行待处理迁移</AppButton>
      </div>
      <table class="list-table" v-if="patches.length">
        <thead>
          <tr><th>文件名</th><th>版本</th><th>状态</th><th>大小</th></tr>
        </thead>
        <tbody>
          <tr v-for="p in patches" :key="p.version" :class="{ applied: p.applied }">
            <td><code>{{ p.filename }}</code></td>
            <td>{{ p.version }}</td>
            <td>
              <span v-if="p.applied" class="tag tag-ok">已应用</span>
              <span v-else class="tag tag-pending">待处理</span>
            </td>
            <td class="num">{{ p.size_bytes }} B</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">暂无迁移文件</p>
      <div v-if="patchResults.length" class="patch-results">
        <h4>执行结果</h4>
        <ul>
          <li v-for="r in patchResults" :key="r.version" :class="r.status === 'error' ? 'error' : ''">
            {{ r.version }} — {{ r.status }}{{ r.error ? ': ' + r.error : '' }}
          </li>
        </ul>
      </div>
    </div>

    <!-- ── Bill Templates ── -->
    <div v-if="activeTab === 'templates'" class="tab-content">
        <BillTemplateManager />
    </div>

    <!-- ── Data Maintenance / ARAP ── -->
    <div v-if="activeTab === 'maintenance'" class="tab-content">
      <div class="section">
        <h3>ARAP 快照数据管理</h3>
        <p class="hint">清除指定收款月份（确认月）的应收应付（ARAP）快照数据，同时重置对应锁的已快照状态，以便重新执行快照。</p>
        <p class="hint" style="margin-top:4px">已月结关闭的月份不会出现在下拉列表中。</p>

        <div v-if="arapLoading" class="muted" style="margin:12px 0">加载中...</div>

        <div v-else-if="arapMonths.length === 0" style="margin:12px 0">
          <p class="muted">ARAP 表中暂无快照数据。</p>
        </div>

        <div v-else style="display:flex;align-items:center;gap:12px;margin-top:12px">
          <select v-model="selectedArapMonth" class="form-input" style="width:auto;min-width:140px">
            <option value="">-- 选择收款月份 --</option>
            <option v-for="m in arapMonths" :key="m" :value="m">{{ m }}</option>
          </select>
          <AppButton variant="danger" size="md"
            :disabled="!selectedArapMonth || clearing"
            :loading="clearing"
            @click="confirmClearArap">
            清除数据
          </AppButton>
        </div>

        <div v-if="clearResult" :class="['muted', clearResult.success ? 'success-msg' : 'error-msg']" style="margin-top:12px">
          {{ clearResult.msg }}
        </div>
      </div>
    </div>

    <!-- ── About / Update ── -->
    <div v-if="activeTab === 'about'" class="tab-content">
      <div class="section">
        <h3>版本信息</h3>
        <table class="info-table">
          <tr><td>当前版本</td><td><strong>{{ versionInfo.version || '-' }}</strong></td></tr>
          <tr><td>构建号</td><td>{{ versionInfo.build || '-' }}</td></tr>
          <tr><td>发布日期</td><td>{{ versionInfo.release_date || '-' }}</td></tr>
          <tr><td>更新地址</td><td><code>{{ versionInfo.update_url || '未配置' }}</code></td></tr>
        </table>
      </div>

      <div class="section">
        <h3>检查更新</h3>
        <div v-if="!updateChecked">
          <AppButton variant="default" size="md" :disabled="checking" :loading="checking" @click="doCheckUpdate">检查更新</AppButton>
        </div>
        <div v-else>
          <p v-if="updateResult?.has_update" class="update-available">
            发现新版本 <strong>{{ updateResult.latest_version }}</strong>
            <span v-if="updateResult.size"> ({{ (updateResult.size / 1024 / 1024).toFixed(1) }} MB)</span>
          </p>
          <p v-else class="update-current">当前已是最新版本</p>
          <p v-if="updateResult?.error" class="error-msg">{{ updateResult.error }}</p>
          <div v-if="updateResult?.changelog" class="changelog">
            <h4>更新说明</h4>
            <pre>{{ updateResult.changelog }}</pre>
          </div>
          <AppButton variant="default" size="md" style="margin-top:12px" @click="updateChecked = false">重新检查</AppButton>
        </div>
      </div>

      <div class="section">
        <h3>密码管理</h3>
        <div v-if="!showChangePassword">
          <AppButton variant="default" size="md" @click="showChangePassword = true">修改密码</AppButton>
        </div>
        <div v-else>
          <div class="form-group"><input v-model="oldPwd" type="password" placeholder="旧密码" /></div>
          <div class="form-group"><input v-model="newPwd" type="password" placeholder="新密码（至少4位）" /></div>
          <div class="form-group"><input v-model="confirmPwd" type="password" placeholder="确认新密码" /></div>
          <div class="actions">
            <AppButton variant="success" size="md" @click="doChangePassword">保存</AppButton>
            <AppButton variant="default" size="md" @click="showChangePassword = false; oldPwd = ''; newPwd = ''; confirmPwd = ''">取消</AppButton>
          </div>
          <p v-if="pwdError" class="error-msg" style="margin-top:8px">{{ pwdError }}</p>
          <p v-if="pwdSuccess" class="success-msg" style="margin-top:8px">密码修改成功</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api, { logError } from '../api'
import { useToast } from '../components/AppToast/useToast'
import BillTemplateManager from '../components/BillTemplateManager.vue'

const toast = useToast()

const tabs = [
  { key: 'status', label: '数据库状态' },
  { key: 'backups', label: '备份管理' },
  { key: 'templates', label: '对账模板' },
  { key: 'logs', label: '审计日志' },
  { key: 'patches', label: '迁移管理' },
  { key: 'maintenance', label: '数据维护' },
  { key: 'about', label: '关于/更新' },
]
const activeTab = ref('status')

// Status
const status = ref({})
async function fetchStatus() {
  try {
    const r = await api.getSystemStatus()
    status.value = r.data.data
  } catch (e) { logError('fetchStatus', e) }
}

// Backup
const backups = ref([])
const showBackupModal = ref(false)
const backupPassword = ref('')
const backingUp = ref(false)
async function fetchBackups() {
  try {
    const r = await api.listBackups()
    backups.value = r.data.data
  } catch (e) { logError('fetchBackups', e) }
}
async function doBackup() {
  backingUp.value = true
  try {
    const pwd = backupPassword.value || null
    await api.createBackup(pwd)
    toast.info('备份创建成功' + (pwd ? '（密码加密）' : ''))
    showBackupModal.value = false
    backupPassword.value = ''
    fetchStatus()
    fetchBackups()
  } catch (e) {
    toast.error('备份失败: ' + (e.response?.data?.detail || e.message))
    backupPassword.value = ''
  } finally {
    backingUp.value = false
  }
}

// Restore
const showRestoreModal = ref(false)
const restoreTarget = ref(null)
const restorePassword = ref('')
const restoringPath = ref('')   // which backup path is currently being restored (for the "确认中..." indicator)
const restoring = ref(false)    // whether a restore is in progress (disables the confirm button)
function confirmRestore(backup) {
  restoreTarget.value = backup
  restorePassword.value = ''
  if (backup.enc_type === 'password') {
    showRestoreModal.value = true
  } else {
    doRestore(backup.path)
  }
}
async function doRestore(path) {
  if (!path || restoring.value) return
  restoring.value = true
  restoringPath.value = path
  try {
    const pwd = restorePassword.value || null
    await api.restoreBackup(path, pwd)
    toast.info('恢复成功')
    showRestoreModal.value = false
    restorePassword.value = ''
    fetchStatus()
  } catch (e) {
    toast.error('恢复失败: ' + (e.response?.data?.detail || e.message))
    restorePassword.value = ''
  } finally {
    restoring.value = false
    restoringPath.value = ''
  }
}

function encTagLabel(type) {
  const map = { plain: '明文', auto: '本机加密', password: '密码加密' }
  return map[type] || type
}
function encTagClass(type) {
  const map = { plain: '', auto: 'tag-warn', password: 'tag-ok' }
  return map[type] || ''
}

// File upload restore
const fileInputRef = ref(null)
const selectedRestoreFile = ref(null)
const selectedFileName = ref('')
const selectedFileIsEncrypted = ref(false)
const showUploadPasswordModal = ref(false)
const uploadRestorePassword = ref('')

function onFileSelected(e) {
  const file = e.target.files[0]
  if (!file) return
  selectedRestoreFile.value = file
  selectedFileName.value = file.name
  selectedFileIsEncrypted.value = file.name.endsWith('.enc.db')
  if (!selectedFileIsEncrypted.value) {
    doRestoreFromFile()
  }
}

function resetFileSelection() {
  selectedRestoreFile.value = null
  selectedFileName.value = ''
  selectedFileIsEncrypted.value = false
  uploadRestorePassword.value = ''
  if (fileInputRef.value) fileInputRef.value.value = ''
}

async function doRestoreFromFile() {
  if (!selectedRestoreFile.value || restoring.value) return
  restoring.value = true
  try {
    const pwd = uploadRestorePassword.value || null
    await api.restoreBackupFromFile(selectedRestoreFile.value, pwd)
    toast.info('恢复成功')
    showUploadPasswordModal.value = false
    resetFileSelection()
    fetchStatus()
    fetchBackups()
  } catch (e) {
    toast.error('恢复失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    restoring.value = false
  }
}

// Reset
const showResetConfirm = ref(false)
const resetCode = ref('')
const resetBackupPassword = ref('')
async function doReset() {
  try {
    const pwd = resetBackupPassword.value || null
    await api.resetDatabase(pwd)
    toast.success('数据库已重置' + (pwd ? '（密码加密备份）' : '（自动密钥备份）'))
    showResetConfirm.value = false
    resetCode.value = ''
    resetBackupPassword.value = ''
    fetchStatus()
    fetchBackups()
  } catch (e) {
    toast.error('重置失败: ' + (e.response?.data?.detail || e.message))
  }
}

// Logs
const logs = ref([])
const logTotal = ref(0)
const offset = ref(0)
const limit = 50
async function fetchLogs() {
  try {
    const r = await api.getLogs({ limit, offset: offset.value })
    logs.value = r.data.data
    logTotal.value = r.data.total || 0
  } catch (e) { logError('fetchLogs', e) }
}

// Patches
const patches = ref([])
const patchesRunning = ref(false)
const patchResults = ref([])
async function fetchPatches() {
  try {
    const r = await api.getPatches()
    patches.value = r.data.data
  } catch (e) { logError('fetchPatches', e) }
}
async function runPatches() {
  patchesRunning.value = true
  patchResults.value = []
  try {
    const r = await api.runPatches()
    patchResults.value = r.data.data.results
    fetchPatches()
  } catch (e) {
    toast.error('迁移执行失败: ' + (e.response?.data?.detail || e.message))
  }
  patchesRunning.value = false
}

// ── Version / Update ──

const versionInfo = ref({})
async function fetchVersion() {
  try {
    const r = await api.getVersion()
    versionInfo.value = r.data.data
  } catch (e) { logError('fetchVersion', e) }
}

const checking = ref(false)
const updateChecked = ref(false)
const updateResult = ref(null)
async function doCheckUpdate() {
  checking.value = true
  updateChecked.value = false
  updateResult.value = null
  try {
    const r = await api.checkUpdate()
    updateResult.value = r.data.data
    updateChecked.value = true
  } catch (e) {
    updateResult.value = { error: e.response?.data?.detail || e.message }
    updateChecked.value = true
  } finally {
    checking.value = false
  }
}

// ── Password management ──

const showChangePassword = ref(false)
const oldPwd = ref('')
const newPwd = ref('')
const confirmPwd = ref('')
const pwdError = ref('')
const pwdSuccess = ref(false)
async function doChangePassword() {
  pwdError.value = ''
  pwdSuccess.value = false
  if (!oldPwd.value) { pwdError.value = '请输入旧密码'; return }
  if (newPwd.value.length < 4) { pwdError.value = '新密码长度不能少于4位'; return }
  if (newPwd.value !== confirmPwd.value) { pwdError.value = '两次密码输入不一致'; return }
  try {
    await api.resetPassword(oldPwd.value, newPwd.value)
    pwdSuccess.value = true
    showChangePassword.value = false
    oldPwd.value = ''
    newPwd.value = ''
    confirmPwd.value = ''
  } catch (e) {
    pwdError.value = e.response?.data?.detail || '修改失败'
  }
}

// ── Bill Templates ──


// ── Data Maintenance / ARAP ──

const arapMonths = ref([])
const selectedArapMonth = ref('')
const arapLoading = ref(false)
const clearing = ref(false)
const clearResult = ref(null)

async function fetchArapMonths() {
  arapLoading.value = true
  clearResult.value = null
  try {
    const r = await api.getArapMonths()
    arapMonths.value = r.data.data.clearable_months || []
  } catch (e) {
    logError('fetchArapMonths', e)
    arapMonths.value = []
  } finally {
    arapLoading.value = false
  }
}

function confirmClearArap() {
  if (!selectedArapMonth.value) return
  clearResult.value = null
  const m = selectedArapMonth.value
  if (!confirm(`确认清除 ${m} 月份的所有 ARAP 快照数据？\n\n清除后数据不可恢复，需重新执行快照才能生成。`)) return
  doClearArap(m)
}

async function doClearArap(month) {
  clearing.value = true
  try {
    const r = await api.clearArapData(month)
    const d = r.data.data
    const extra = d.channel_locks_reset || d.publisher_locks_reset
      ? `，同时重置渠道锁 ${d.channel_locks_reset || 0} + 研发商锁 ${d.publisher_locks_reset || 0} 的 confirmed_month`
      : ''
    toast.success(`已清除 ${month} 月份 ${d.deleted} 条 ARAP 数据${extra}`)
    selectedArapMonth.value = ''
    clearResult.value = { success: true, msg: `已清除 ${d.deleted} 条记录${extra}，可前往「应收应付」页面重新执行快照。` }
    fetchArapMonths()
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    toast.error('清除失败: ' + msg)
    clearResult.value = { success: false, msg: '清除失败: ' + msg }
  } finally {
    clearing.value = false
  }
}

// ── LAN sharing ──

const lanEnabled = ref(false)
const lanIps = ref([])

async function fetchLanStatus() {
  try {
    const r = await api.getLanStatus()
    lanEnabled.value = r.data.data.lan_enabled
  } catch (e) { logError('fetchLanStatus', e) }
}

async function toggleLan() {
  try {
    await api.setLanEnabled(lanEnabled.value)
  } catch (e) {
    lanEnabled.value = !lanEnabled.value
    toast.error('操作失败: ' + (e.response?.data?.detail || e.message))
  }
}

// Detect LAN IPs for display
function detectLanIps() {
  // Try WebRTC or just common patterns
  const ips = []
  const canvas = document.createElement('canvas')
  // Simple approach: render and check addresses from RTCPeerConnection
  try {
    const pc = new RTCPeerConnection({ iceServers: [] })
    pc.createDataChannel('')
    pc.onicecandidate = (e) => {
      if (e.candidate) {
        const match = e.candidate.candidate.match(/(\d+\.\d+\.\d+\.\d+)/)
        if (match && !match[1].startsWith('127.')) {
          ips.push(match[1])
        }
      }
    }
    pc.createOffer().then((offer) => pc.setLocalDescription(offer))
    setTimeout(() => {
      lanIps.value = [...new Set(ips)]
      pc.close()
    }, 500)
  } catch {
    // Fallback: nothing
  }
}

onMounted(() => {
  fetchStatus()
  fetchBackups()
  fetchLogs()
  fetchPatches()
  fetchVersion()
  fetchLanStatus()
  fetchArapMonths()
  detectLanIps()
})
</script>

<style scoped>
.system { max-width: 960px; }
.system h2 { margin-bottom: 16px; font-size: 20px; }

.tabs { margin-bottom: 20px; }

.tab-content { min-height: 300px; }

.section { margin-bottom: 24px; }
.section h3 { font-size: 15px; margin-bottom: 8px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { font-size: 15px; margin: 0; }

.info-table { width: auto; border-collapse: collapse; font-size: 13px; }
.info-table td { padding: 4px 16px 4px 0; }
.info-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.info-table code { background: var(--palette-gray-50); padding: 2px 6px; border-radius: 3px; font-size: 12px; }

.list-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.list-table th { text-align: left; padding: 8px; border-bottom: 2px solid var(--border-light); font-weight: 600; color: var(--text-secondary); }
.list-table td { padding: 6px 8px; border-bottom: 1px solid var(--border-light); }
.list-table tr:hover td { background: var(--palette-gray-50); }
.list-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.list-table code { font-size: 12px; }

/* ── Toggle switch ── */
.toggle-row { display: flex; align-items: center; justify-content: space-between; font-size: 14px; cursor: pointer; padding: 8px 0; }
.toggle-wrap { position: relative; width: 44px; height: 24px; flex-shrink: 0; }
.toggle-wrap input { opacity: 0; width: 0; height: 0; position: absolute; }
.toggle-slider {
  position: absolute; cursor: pointer; inset: 0; border-radius: 24px;
  background: var(--text-light); transition: background 0.2s;
}
.toggle-slider::before {
  content: ''; position: absolute; width: 18px; height: 18px; left: 3px; bottom: 3px;
  background: var(--bg-card); border-radius: 50%; transition: transform 0.2s;
}
.toggle-wrap input:checked + .toggle-slider { background: var(--palette-blue-dark); }
.toggle-wrap input:checked + .toggle-slider::before { transform: translateX(20px); }

.actions { display: flex; gap: 12px; margin-top: 16px; }

.btn {
  padding: 6px 20px; font-size: 13px; border: 1px solid var(--color-primary); border-radius: 6px;
  background: var(--bg-card); color: var(--color-primary); cursor: pointer;
}
.btn:hover { background: var(--color-primary); color: var(--bg-card); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-danger { border-color: var(--color-danger); color: var(--color-danger); }
.btn-danger:hover { background: var(--color-danger); color: var(--bg-card); }
.btn-primary { border-color: var(--palette-blue-dark); color: var(--palette-blue-dark); }
.btn-primary:hover { background: var(--palette-blue-dark); color: var(--bg-card); }
.btn-sm {
  padding: 2px 10px; font-size: 12px; border: 1px solid var(--color-primary); border-radius: 4px;
  background: var(--bg-card); color: var(--color-primary); cursor: pointer;
}
.btn-sm:hover { background: var(--color-primary); color: var(--bg-card); }
.btn-sm-danger { border-color: var(--color-danger); color: var(--color-danger); }
.btn-sm-danger:hover { background: var(--color-danger); color: var(--bg-card); }

.muted { color: var(--text-light); font-size: 13px; }

.tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--border-cell); color: var(--text-muted); }
.tag-ok { background: var(--bg-badge-ok); color: var(--color-success); }
.tag-pending { background: var(--bg-badge-warn); color: var(--color-warning); }

.pagination { display: flex; align-items: center; gap: 12px; margin-top: 12px; font-size: 13px; }
.pagination button { padding: 4px 12px; border: 1px solid var(--border-default); border-radius: 4px; background: var(--bg-card); cursor: pointer; }
.pagination button:disabled { opacity: 0.4; cursor: default; }

.patch-results { margin-top: 16px; }
.patch-results h4 { font-size: 14px; margin-bottom: 6px; }
.patch-results ul { list-style: none; padding: 0; font-size: 13px; }
.patch-results li { padding: 3px 0; }
.patch-results li.error { color: var(--color-danger); }
.list-table tr.applied { opacity: 0.7; }

.update-available { color: var(--palette-blue-dark); font-size: 14px; }
.update-current { color: var(--color-success); font-size: 14px; }
.changelog { margin-top: 12px; background: var(--palette-gray-80); border-radius: 6px; padding: 12px; }
.changelog h4 { font-size: 13px; margin-bottom: 6px; }
.changelog pre { font-size: 12px; white-space: pre-wrap; color: var(--text-secondary); max-height: 200px; overflow-y: auto; }
.error-msg { color: var(--color-danger); font-size: 13px; }
.success-msg { color: var(--color-success); font-size: 13px; }
.form-group { margin-bottom: 10px; }
.hint { font-size: 12px; color: var(--text-light); margin: 4px 0; }
.tag-warn { background: var(--bg-badge-warn); color: var(--color-warning); }
</style>
