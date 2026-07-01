import axios from 'axios'

const TOKEN_KEY = 'finance_auth_token'

const api = axios.create({ baseURL: '/api' })

// ── Token management ──

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
    api.defaults.headers.common['X-Auth-Token'] = token
  } else {
    localStorage.removeItem(TOKEN_KEY)
    delete api.defaults.headers.common['X-Auth-Token']
  }
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
  delete api.defaults.headers.common['X-Auth-Token']
}

// Restore token from localStorage
const saved = getToken()
if (saved) {
  api.defaults.headers.common['X-Auth-Token'] = saved
}

// ── Response interceptor: redirect to login on 401 (except for login itself) ──
api.interceptors.response.use(
  (r) => {
    if (r.headers['x-read-only'] === '1') {
      localStorage.setItem('finance_readonly', '1')
    }
    return r
  },
  (err) => {
    if (err.response?.status === 403) {
      // Read-only mode: just reject, don't redirect
      localStorage.setItem('finance_readonly', '1')
      // Dispatch a custom event so App.vue can show a toast globally.
      // Debounce: multiple 403s in 2s only trigger one toast.
      if (!window._readonlyForbiddenTimer) {
        window._readonlyForbiddenTimer = setTimeout(() => { window._readonlyForbiddenTimer = null }, 2000)
        const detail = err.response?.data?.detail || '只读模式：当前为局域网访问，仅可查看数据'
        window.dispatchEvent(new CustomEvent('readonly-forbidden', { detail }))
      }
      return Promise.reject(err)
    }
    if (err.response?.status === 401) {
      const url = err.config?.url || ''
      if (!url.includes('/auth/login')) {
        clearToken()
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  },
)

export function logError(context, err) {
  console.warn(`[${context}]`, err?.response?.data?.detail || err?.message || err)
}

export default {
  // Token management (re-exported so Login.vue can call api.setToken / api.getToken / api.clearToken)
  setToken,
  getToken,
  clearToken,

  // Auth
  getAuthStatus: () => api.get('/auth/status'),
  login: (password) => api.post('/auth/login', { password }),
  logout: () => api.post('/auth/logout'),
  setupPassword: (password) => api.post('/auth/setup', { password }),
  resetPassword: (oldPassword, newPassword) => api.post('/auth/reset', { old_password: oldPassword, new_password: newPassword }),

  // Health
  health: () => api.get('/health'),

  // Basic data
  getGames: () => api.get('/basic/games'),
  getCompanies: () => api.get('/basic/companies'),
  getPublishers: () => api.get('/basic/publishers'),
  getChannelCategories: () => api.get('/basic/channel-categories'),
  getChannelTree: () => api.get('/basic/channels/tree'),
  batchChannels: (data) => api.post('/basic/channels/batch', data),

  // Project codes (for company-game mapping dropdown)
  getProjectCodes: () => api.get('/basic/project-codes'),

  // Company game mapping
  getCompanyGames: (companyId) => api.get(`/basic/companies/${companyId}/games`),
  batchCompanyGames: (data) => api.post('/basic/companies/games/batch', data),
  deleteCompanyGames: (data) => api.post('/basic/companies/games/delete', data),
  getCompanyProjects: (companyId) => api.get(`/basic/companies/${companyId}/projects`),
  getProjectGames: (companyId, params) => api.get(`/basic/companies/${companyId}/project-games`, { params }),
  upsertCompanyGameOverride: (data) => api.post('/basic/companies/games/override', data),
  removeCompanyGameOverride: (data) => api.delete('/basic/companies/games/override', { data }),
  deleteCompanyGamesByProject: (data) => api.post('/basic/companies/games/delete-by-project', data),

  // Channel-Party mapping
  getChannelPartyMappings: () => api.get('/basic/channel-company-mappings'),
  saveChannelPartyMapping: (data) => api.post('/basic/channel-company-mappings', data),
  deleteChannelPartyMapping: (channelId) => api.delete(`/basic/channel-company-mappings/${channelId}`),

  // Import
  getTemplates: () => api.get('/import/templates'),
  downloadTemplate: (type) => api.get(`/import/templates/${type}/download`, { responseType: 'blob' }),
  previewImport: (templateType, file) => {
    const fd = new FormData()
    fd.append('template_type', templateType)
    fd.append('file', file)
    return api.post('/import/preview', fd)
  },
  confirmImport: (templateType, file, overwrite) => {
    const fd = new FormData()
    fd.append('template_type', templateType)
    fd.append('file', file)
    fd.append('overwrite', overwrite)
    return api.post('/import/confirm', fd)
  },

  // Flexible import
  flexiblePreview: (file, headerRow) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('header_row', headerRow || '1')
    return api.post('/import/flexible/preview', fd)
  },
  flexibleConfirm: (file, headerRow, month, channelId, columnMapping) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('header_row', headerRow || '1')
    fd.append('month', month || '')
    fd.append('channel_id', String(channelId || '0'))
    fd.append('column_mapping', JSON.stringify(columnMapping))
    return api.post('/import/flexible/confirm', fd)
  },
  flexibleImport: (file, headerRow, month, channelId, columnMapping, selectedIndices) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('header_row', headerRow || '1')
    fd.append('month', month || '')
    fd.append('channel_id', String(channelId || '0'))
    fd.append('column_mapping', JSON.stringify(columnMapping))
    fd.append('selected_indices', (selectedIndices || []).join(','))
    return api.post('/import/flexible/import', fd)
  },
  getFieldDefinitions: () => api.get('/import/flexible/field-definitions'),
  exportSynonymDict: () => api.get('/import/flexible/dictionary'),
  importSynonymDict: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/import/flexible/dictionary', fd)
  },

  // Batch save
  batchGames: (data) => api.post('/basic/games/batch', data),
  batchCompanies: (data) => api.post('/basic/companies/batch', data),
  batchPublishers: (data) => api.post('/basic/publishers/batch', data),

  // Publisher game mapping (project info)
  getPublisherGames: (publisherId) => api.get(`/basic/publishers/${publisherId}/games`),
  batchPublisherGames: (data) => api.post('/basic/publishers/games/batch', data),
  deletePublisherGames: (data) => api.post('/basic/publishers/games/delete', data),

  // Settlement
  getSettlementChannels: () => api.get('/settlement/settlement-channels'),
  getChannelSettlements: (params) => api.get('/settlement/channel-settlements', { params }),
  getIncomeSettlement: (params) => api.get('/settlement/income', { params }),
  getPaymentSettlement: (params) => api.get('/settlement/payment', { params }),
  batchDeductions: (data) => api.post('/settlement/deductions/batch', data),
  getIncomeSplitConfigs: () => api.get('/settlement/income-split-configs'),
  getPaymentSplitConfigs: () => api.get('/settlement/payment-split-configs'),
  batchIncomeSplitConfig: (data) => api.post('/settlement/income-split-config/batch', data),
  batchPaymentSplitConfig: (data) => api.post('/settlement/payment-split-config/batch', data),
  exportBill: (data) => api.post('/settlement/bill', data, { responseType: 'blob' }),
  lockSettlement: (data) => api.post('/settlement/lock', data),
  exportCsv: (params) => api.get('/settlement/export-csv', { params, responseType: 'blob' }),
  exportFullCsv: (params) => api.get('/settlement/export-full', { params, responseType: 'blob' }),

  // Party Info
  getPartyInfo: (params) => api.get('/party-info', { params }),
  createPartyInfo: (data) => api.post('/party-info', data),
  updatePartyInfo: (id, data) => api.put(`/party-info/${id}`, data),
  deletePartyInfo: (id) => api.delete(`/party-info/${id}`),

  // Dashboard
  getDashboardInit: () => api.get('/dashboard/init'),
  getDashboardSummary: () => api.get('/dashboard/summary'),
  getDashboardRanking: (params) => api.get('/dashboard/ranking', { params }),
  getDashboardTrend: (params) => api.get('/dashboard/trend', { params }),
  getDashboardLevel2: (params) => api.get('/dashboard/level2-options', { params }),
  getDashboardLevel1Options: (params) => api.get('/dashboard/level1-options', { params }),
  getDashboardTrendSummary: () => api.get('/dashboard/trend-summary'),
  getAvailableMonths: () => api.get('/dashboard/available-months'),

  // System
  getSystemStatus: () => api.get('/system/status'),
  createBackup: (password) => api.post('/system/backup', null, { params: password ? { password } : {} }),
  listBackups: () => api.get('/system/backups'),
  restoreBackup: (backupPath, password) => api.post('/system/restore', null, { params: { backup_path: backupPath, ...(password ? { password } : {}) } }),
  resetDatabase: (password) => api.post('/system/reset', null, { params: { confirm: 'RESET', ...(password ? { password } : {}) } }),
  getPatches: () => api.get('/system/patches'),
  runPatches: () => api.post('/system/patches/run'),
  getLogs: (params) => api.get('/system/logs', { params }),
  restoreBackupFromFile: (file, password) => {
    const fd = new FormData()
    fd.append('file', file)
    const params = {}
    if (password) params.password = password
    return api.post('/system/restore-file', fd, { params })
  },

  syncChannelSettlements: () => api.post('/system/sync-channel-settlements'),

  // Version / Update
  getVersion: () => api.get('/system/version'),
  checkUpdate: () => api.get('/system/check-update'),
  getLanStatus: () => api.get('/system/lan-status'),
  setLanEnabled: (enabled) => api.post('/system/lan-toggle', { enabled }),
  applyPatch: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/system/apply-patch', fd)
  },

  // ARAP maintenance (system)
  getArapMonths: () => api.get('/system/arap-months'),
  clearArapData: (month) => api.post('/system/arap-clear', null, { params: { month } }),

  // Memos
  getMemos: () => api.get('/memos'),
  getMemo: (id) => api.get(`/memos/${id}`),
  createMemo: (data) => api.post('/memos', data, { headers: { 'Content-Type': 'multipart/form-data' } }),
  updateMemo: (id, data) => api.put(`/memos/${id}`, data, { headers: { 'Content-Type': 'multipart/form-data' } }),
  deleteMemo: (id) => api.delete(`/memos/${id}`),
  getMemoAttachmentUrl: (id) => `/api/memos/${id}/attachment`,

  // QuickSDK
  getQuickSDKStatus: () => api.get('/quicksdk/status'),
  getQuickSDKKeys: () => api.get('/quicksdk/keys'),
  getQuickSDKProducts: (keyIndex = 0) => api.get('/quicksdk/products', { params: { key_index: keyIndex } }),
  previewQuickSDKTotal: (startDate, endDate, productCode, keyIndex = 0) =>
    api.post('/quicksdk/preview-total', { start_date: startDate, end_date: endDate, product_code: productCode, key_index: keyIndex }),
  fetchQuickSDK: (startDate, endDate, productCode, gameId, keyIndex = 0) =>
    api.post('/quicksdk/fetch', { start_date: startDate, end_date: endDate, product_code: productCode, game_id: gameId, key_index: keyIndex }),
  batchImportQuickSDK: (startDate, endDate, keyIndex = 0, overwrite = false) =>
    api.post('/quicksdk/batch-import', { start_date: startDate, end_date: endDate, key_index: keyIndex, overwrite }),
  confirmQuickSDK: (rows, overwrite) => api.post('/quicksdk/confirm', { rows, overwrite }),

  // Ledger (AR/AP)
  getLedgerEntries: (params) => api.get('/settlement/ledger/entries', { params }),
  getOpenItems: (params) => api.get('/settlement/ledger/open-items', { params }),
  getAccountBalances: (params) => api.get('/settlement/ledger/balances', { params }),
  registerPayment: (data, collectionMonth) => api.post('/settlement/ledger/payment', { ...data, note: data.note || null }, { params: { collection_month: collectionMonth } }),
  deletePayment: (id) => api.delete(`/settlement/ledger/payment/${id}`),
  getBreakdown: (params) => api.get('/settlement/arap/breakdown', { params }),
  arapSnapshot: (confirmedMonth) => api.post('/settlement/arap/snapshot', null, { params: { confirmed_month: confirmedMonth } }),
  getARAPPivot: (params) => api.get('/settlement/arap/pivot', { params }),
  monthlyClose: (data) => api.post('/settlement/arap/monthly-close', data),
  getMonthlyCloses: () => api.get('/settlement/arap/monthly-closes'),
  getDashboardBalances: (params) => api.get('/settlement/arap/dashboard-balances', { params }),
  getWorkingMonth: () => api.get('/settlement/arap/working-month'),
  getPendingCount: () => api.get('/settlement/arap/pending-count'),
  deleteMonthlyClose: (month) => api.delete(`/settlement/arap/monthly-close/${month}`),
  arapCompanyOverride: (data) => api.post('/settlement/arap/company-override', data),
  arapCompanyOverrideDelete: (data) => api.delete('/settlement/arap/company-override', { data }),
  getProfitTable: (params) => api.get('/settlement/profit/table', { params }),
  saveExpense: (data) => api.put('/settlement/profit/expense', data),
  getProfitSummary: (params) => api.get('/settlement/profit/summary', { params }),

  // Bill Templates
  getBillTemplates: (params) => api.get('/bill-templates', { params }),
  createBillTemplate: (data) => api.post('/bill-templates', data),  // auto-detect FormData boundary
  updateBillTemplate: (id, data) => api.put(`/bill-templates/${id}`, data),
  updateBillTemplateFile: (id, data) => api.put(`/bill-templates/${id}/file`, data),  // auto-detect FormData boundary
  deleteBillTemplate: (id) => api.delete(`/bill-templates/${id}`),
  getBillTemplateDownloadUrl: (id) => `/api/bill-templates/${id}/download`,
  downloadBillTemplate: (id) => api.get(`/bill-templates/${id}/download`, { responseType: 'blob' }),
}
