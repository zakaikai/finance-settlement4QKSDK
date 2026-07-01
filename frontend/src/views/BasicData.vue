<template>
  <div class="basic-data">
    <h2>基础数据管理</h2>

    <div class="tabs">
      <button :class="{ active: tab === 'games' }" @click="tab = 'games'">游戏信息</button>
      <button :class="{ active: tab === 'companies' }" @click="tab = 'companies'">我方公司</button>
      <button :class="{ active: tab === 'publishers' }" @click="tab = 'publishers'">研发商户</button>
      <button :class="{ active: tab === 'channels' }" @click="tab = 'channels'">渠道层级</button>
      <button :class="{ active: tab === 'channel_company' }" @click="tab = 'channel_company'; loadChannelCompanyMappings()">渠道主体</button>
      <button :class="{ active: tab === 'partyinfo' }" @click="tab = 'partyinfo'">主体信息</button>
      <button :class="{ active: tab === 'income_split' }" @click="tab = 'income_split'">收入分成</button>
      <button :class="{ active: tab === 'payment_split' }" @click="tab = 'payment_split'">研发分成</button>
      <button :class="{ active: tab === 'bill_templates' }" @click="tab = 'bill_templates'">对账模板</button>
      <button :class="{ active: tab === 'channel_settlements' }" @click="tab = 'channel_settlements'; loadChannelSettlements()">原始流水表</button>
    </div>

    <!-- Games -->
    <div v-if="tab === 'games'" class="tab-content">
      <div class="toolbar">
        <button class="btn-add" @click="addRow('games')">+ 添加行</button>
        <button class="btn-save" @click="batchSave('games')" :disabled="!hasChanges('games')">
          保存修改
        </button>
        <button v-if="hasChanges('games')" class="btn-discard" @click="discardChanges('games')">撤销修改</button>
        <span v-if="changedCount('games')" class="change-badge">{{ changedCount('games') }} 处修改</span>
      </div>
      <ag-grid-vue
        :rowData="gamesData"
        :columnDefs="gameCols"
        class="ag-theme-quartz grid"
        :defaultColDef="defaultColDef"
        :getRowId="r => String(r.data._tempId ?? r.data.game_id ?? '')"
        @cell-value-changed="onCellChanged('games', $event)"
        @grid-ready="onGamesGridReady"
        :animateRows="true"
        domLayout="autoHeight"
      />
    </div>

    <!-- Companies -->
    <div v-if="tab === 'companies'" class="tab-content publisher-tab">
      <div class="toolbar">
        <button class="btn-add" @click="addRow('companies')">+ 添加公司</button>
        <button class="btn-save" @click="batchSave('companies')" :disabled="!hasChanges('companies')">
          保存修改
        </button>
        <button v-if="hasChanges('companies')" class="btn-discard" @click="discardChanges('companies')">撤销修改</button>
        <span v-if="changedCount('companies')" class="change-badge">{{ changedCount('companies') }} 处修改</span>
      </div>

      <div class="publisher-layout">
        <!-- Left: Company list -->
        <div class="publisher-list-panel">
          <ag-grid-vue
            :rowData="companiesData"
            :columnDefs="companyCols"
            class="ag-theme-quartz grid"
            :defaultColDef="defaultColDef"
            :getRowId="r => String(r.data.company_id ?? r.data._tempId ?? '')"
            @cell-value-changed="onCellChanged('companies', $event)"
            @row-clicked="onCompanySelected"
            @grid-ready="onCompaniesGridReady"
            :animateRows="true"
            domLayout="autoHeight"
            :rowSelection="{ mode: 'singleRow' }"
          />
        </div>

        <!-- Right: Company-project + game detail -->
        <div v-if="selectedCompany" class="detail-panel">
          <div class="detail-header">
            <h4>{{ selectedCompany.company_name }}</h4>
          </div>

          <!-- Project-level associations -->
          <div class="detail-section">
            <div class="detail-header">
              <span class="section-label">项目级关联</span>
              <button class="btn-add" @click="addCompanyProjectRow">+ 添加项目</button>
              <button class="btn-save" :disabled="!projDirty" @click="saveCompanyProjects">保存</button>
              <button v-if="projDirty" class="btn-discard" @click="discardProjChanges">撤销</button>
              <span v-if="projDirty" class="change-badge">有未保存修改</span>
            </div>
            <ag-grid-vue
              :rowData="companyProjects"
              :columnDefs="companyProjectCols"
              class="ag-theme-quartz grid detail-grid"
              :defaultColDef="{ sortable: true, resizable: true, editable: true }"
              :context="{ projectCodes: projectCodes, channelCategories: channelCategories }"
              @cell-value-changed="onProjChanged"
              @row-clicked="onProjRowSelected"
              domLayout="autoHeight"
              :animateRows="true"
              :headerHeight="32"
              :rowHeight="30"
              :rowSelection="{ mode: 'singleRow' }"
            />
          </div>

          <!-- Game-level exceptions (for selected project) -->
          <div v-if="selectedProject" class="detail-section">
            <div class="detail-header">
              <span class="section-label">
                游戏级例外 — {{ selectedProject.project_code || '(新项目)' }}
                <template v-if="selectedProject.channel_name && selectedProject.channel_name !== '全部渠道'">
                  (渠道: {{ selectedProject.channel_name }})
                </template>
              </span>
            </div>
            <ag-grid-vue
              :rowData="projectGamesData"
              :columnDefs="projectGameOverrideCols"
              class="ag-theme-quartz grid detail-grid"
              :defaultColDef="{ sortable: true, resizable: true }"
              :context="{ allCompanies: companiesData }"
              domLayout="autoHeight"
              :animateRows="true"
              :headerHeight="32"
              :rowHeight="30"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Publishers -->
    <div v-if="tab === 'publishers'" class="tab-content publisher-tab">
      <div class="toolbar">
        <button class="btn-add" @click="addRow('publishers')">+ 添加行</button>
        <button class="btn-save" @click="batchSave('publishers')" :disabled="!hasChanges('publishers')">
          保存修改
        </button>
        <button v-if="hasChanges('publishers')" class="btn-discard" @click="discardChanges('publishers')">撤销修改</button>
        <span v-if="changedCount('publishers')" class="change-badge">{{ changedCount('publishers') }} 处修改</span>
      </div>

      <div class="publisher-layout">
        <!-- Left: Publisher list -->
        <div class="publisher-list-panel">
          <ag-grid-vue
            :rowData="publishersData"
            :columnDefs="publisherCols"
            class="ag-theme-quartz grid"
            :defaultColDef="defaultColDef"
            :getRowId="r => String(r.data.publisher_id ?? r.data._tempId ?? '')"
            @cell-value-changed="onCellChanged('publishers', $event)"
            @row-clicked="onPublisherSelected"
            @grid-ready="onPublishersGridReady"
            :animateRows="true"
            domLayout="autoHeight"
            :rowSelection="{ mode: 'singleRow' }"
          />
        </div>

        <!-- Right: Project mapping detail -->
        <div v-if="selectedPublisher" class="detail-panel">
          <div class="detail-header">
            <h4>项目信息 — {{ selectedPublisher.publisher_name }}</h4>
            <button class="btn-add" @click="addPublisherGameRow">+ 添加行</button>
            <button class="btn-save" @click="savePublisherGames" :disabled="!pubGameDirty">
              保存项目信息
            </button>
            <button v-if="pubGameDirty" class="btn-discard" @click="discardPubGameChanges">撤销修改</button>
            <span v-if="pubGameDirty" class="change-badge">有未保存修改</span>
          </div>
          <ag-grid-vue
            :rowData="publisherGamesData"
            :columnDefs="publisherGameCols"
            class="ag-theme-quartz grid detail-grid"
            :defaultColDef="{ sortable: true, resizable: true, editable: true }"
            @cell-value-changed="onPubGameChanged"
            domLayout="autoHeight"
            :animateRows="true"
            :headerHeight="32"
            :rowHeight="30"
          />
        </div>
      </div>
    </div>

    <!-- Channels (editable flat grid) -->
    <div v-if="tab === 'channels'" class="tab-content">
      <div class="toolbar">
        <button class="btn-add" @click="addChannelRow">+ 添加行</button>
        <button class="btn-save" @click="batchSaveChannels" :disabled="!chanDirty">
          保存修改
        </button>
        <button v-if="chanDirty" class="btn-discard" @click="discardChannelChanges">撤销修改</button>
        <span v-if="chanDirty" class="change-badge">{{ chanCount }} 处修改</span>
        <span v-if="channelMsg" class="save-toast toast-error">{{ channelMsg }}</span>
        <span class="toolbar-info">共 <strong>{{ channelsData.length }}</strong> 条渠道记录</span>
      </div>
      <ag-grid-vue
        :rowData="channelsData"
        :columnDefs="channelCols"
        class="ag-theme-quartz grid"
        :defaultColDef="chanDefaultColDef"
        :getRowId="r => r.data._rowId || ''"
        @cell-value-changed="onChanCellChanged"
        @grid-ready="onChannelsGridReady"
        :animateRows="true"
        domLayout="autoHeight"
        :headerHeight="32"
        :rowHeight="30"
      />
    </div>

    <!-- Channel-Company Mapping -->
    <div v-if="tab === 'channel_company'" class="tab-content">
      <div class="toolbar">
        <button class="btn-add" @click="addChanCompRow">+ 添加映射</button>
        <button class="btn-save" @click="saveChannelCompanyMappings"
                :disabled="Object.keys(chanCompChanges).length === 0">保存</button>
        <button class="btn-discard" @click="discardChanCompChanges"
                :disabled="Object.keys(chanCompChanges).length === 0">放弃</button>
        <span class="toolbar-info" style="margin-left:12px;font-size:12px;color:var(--text-light)">
          渠道对应我方主体，全量导出时使用
        </span>
      </div>

      <div class="grid-container">
        <ag-grid-vue
          :rowData="chanCompRows"
          :columnDefs="chanCompCols"
          class="ag-theme-quartz grid"
          :defaultColDef="{ sortable: true, resizable: true }"
          domLayout="autoHeight"
          :animateRows="true"
          :headerHeight="32"
          :rowHeight="30"
          @cell-value-changed="onChanCompChanged"
          @grid-ready="(p) => chanCompGridApi = p.api"
        />
      </div>
    </div>

    <!-- PartyInfo -->
    <div v-if="tab === 'partyinfo'" class="tab-content">
      <div class="toolbar">
        <button class="btn-add" @click="partyInfo.addRow()">+ 添加行</button>
        <button class="btn-save" @click="savePartyInfo" :disabled="!partyInfo.dirty">
          保存修改
        </button>
        <button v-if="partyInfo.dirty" class="btn-discard" @click="partyInfo.discard">撤销修改</button>
        <span v-if="partyInfo.dirty" class="change-badge">{{ partyInfo.changeCount }} 处修改</span>
      </div>
      <ag-grid-vue
        :rowData="partyInfo.data"
        :columnDefs="partyInfoCols"
        class="ag-theme-quartz grid"
        :defaultColDef="{ sortable: true, filter: true, resizable: true, editable: true }"
        :getRowId="r => String(r.data.id ?? r.data._tempId ?? '')"
        @cell-value-changed="e => partyInfo.onCellChanged(e)"
        :animateRows="true"
        domLayout="autoHeight"
        :headerHeight="32"
        :rowHeight="30"
      />
    </div>

    <!-- Income Split Config -->
    <div v-if="tab === 'income_split'" class="tab-content">
      <div class="toolbar">
        <button class="btn-add" @click="incomeSplit.addRow()">+ 添加行</button>
        <button class="btn-save" @click="saveIncomeSplit" :disabled="!incomeSplit.dirty">
          保存修改
        </button>
        <button v-if="incomeSplit.dirty" class="btn-discard" @click="incomeSplit.discard">撤销修改</button>
        <span v-if="incomeSplit.dirty" class="change-badge">{{ incomeSplit.changeCount }} 处修改</span>
        <span v-if="incomeSplitMsg" class="save-toast toast-success">{{ incomeSplitMsg }}</span>
      </div>
      <ag-grid-vue
        :rowData="incomeSplit.data"
        :columnDefs="incomeSplitCols"
        class="ag-theme-quartz grid"
        :defaultColDef="{ sortable: true, filter: true, resizable: true, editable: true }"
        :getRowId="r => String(r.data.id ?? r.data._tempId ?? '')"
        @cell-value-changed="e => incomeSplit.onCellChanged(e, (row, field) => {
          if (field === 'game_id' && row.game_id) {
            const name = gamesMap[row.game_id]
            if (name) row.game_name = name
          }
        })"
        :animateRows="true"
        domLayout="autoHeight"
        :headerHeight="32"
        :rowHeight="30"
      />
    </div>

    <!-- Payment Split Config -->
    <div v-if="tab === 'payment_split'" class="tab-content">
      <div class="toolbar">
        <button class="btn-add" @click="paymentSplit.addRow()">+ 添加行</button>
        <button class="btn-save" @click="savePaymentSplit" :disabled="!paymentSplit.dirty">
          保存修改
        </button>
        <button v-if="paymentSplit.dirty" class="btn-discard" @click="paymentSplit.discard">撤销修改</button>
        <span v-if="paymentSplit.dirty" class="change-badge">{{ paymentSplit.changeCount }} 处修改</span>
        <span v-if="paymentSplitMsg" class="save-toast toast-success">{{ paymentSplitMsg }}</span>
      </div>
      <ag-grid-vue
        :rowData="paymentSplit.data"
        :columnDefs="paymentSplitCols"
        class="ag-theme-quartz grid"
        :defaultColDef="{ sortable: true, filter: true, resizable: true, editable: true }"
        :getRowId="r => String(r.data.id ?? r.data._tempId ?? '')"
        @cell-value-changed="e => paymentSplit.onCellChanged(e, (row, field) => {
          if (field === 'game_id' && row.game_id) {
            const name = gamesMap[row.game_id]
            if (name) row.game_name = name
          }
        })"
        :animateRows="true"
        domLayout="autoHeight"
        :headerHeight="32"
        :rowHeight="30"
      />
    </div>
    <!-- Bill Templates -->
    <div v-if="tab === 'bill_templates'" class="tab-content">
      <BillTemplateManager />
    </div>

    <!-- 原始流水表 — ChannelSettlement 聚合视图，只读 -->
    <div v-if="tab === 'channel_settlements'" class="tab-content">
      <div class="toolbar">
        <span class="toolbar-title">原始流水汇总：从 Excel 导入后按 渠道×游戏×月份 聚合，共 {{ channelSettlementTotal }} 条</span>
        <span class="toolbar-sep"></span>
        <span class="toolbar-hint">只读 · 数据由模板导入自动同步</span>
      </div>
      <ag-grid-vue
        :rowData="channelSettlementData"
        :columnDefs="channelSettlementCols"
        class="ag-theme-quartz grid"
        :defaultColDef="{ ...defaultColDef, editable: false }"
        domLayout="autoHeight"
        :animateRows="true"
        @grid-ready="onChannelSettlementGridReady"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import api, { logError } from '../api'
import { useEditableGrid } from '../composables/useEditableGrid.js'
import { rowNoCol, rateCol, dateCol, deleteCol, copyDeleteCol } from '../composables/gridColumns.js'
import BillTemplateManager from '../components/BillTemplateManager.vue'
import { useGames } from '../composables/useSharedData.js'
import { useToast } from '../components/AppToast/useToast'
import SearchSelectCellEditor from '../components/SearchSelectCellEditor.vue'

const toast = useToast()
const tab = ref('games')

const { games: gamesData, gamesMap, load: loadGames } = useGames()

// ── Data ──
const companiesData = ref([])
const publishersData = ref([])
const channelCategories = ref([])

// ── Channel editing ──
const channelsData = ref([])
const channelChanges = reactive({})
const channelMsg = ref('')
const chanDirty = computed(() => Object.keys(channelChanges).length > 0)
const chanCount = computed(() => Object.keys(channelChanges).length)
let chanTempIdCounter = 0

const chanDefaultColDef = {
  sortable: true, filter: true, resizable: true, editable: true,
}

const channelCols = [
  rowNoCol(),
  { field: 'channel_name', headerName: '一级渠道', width: 140, pinned: 'left', editable: true },
  { field: 'backend_channel_name', headerName: '二级渠道', width: 160, editable: true },
  { field: 'sub_channel_name', headerName: '三级渠道', width: 180, editable: true },
  {
    headerName: '操作', width: 80, editable: false, sortable: false, filter: false,
    cellRenderer: () => '<button class="btn-del-row" data-action="delete">删除</button>',
    onCellClicked: p => { if (p.event.target.dataset.action === 'delete') deleteChannelRow(p) },
  },
]

function _chanRowId(row) {
  return `${row.channel_name}|${row.backend_channel_name}|${row.sub_channel_name}`
}

function loadChannelsData() {
  const rows = []
  channelCategories.value.forEach(cat => {
    const backends = cat.backend_channels || []
    backends.forEach(bk => {
      const subs = bk.sub_channels || []
      subs.forEach(sub => {
        const r = {
          channel_name: cat.channel_name,
          backend_channel_name: bk.backend_channel_name,
          sub_channel_name: sub.sub_channel_name,
          _rowId: '',
          _origChannelName: cat.channel_name,
          _origBackendName: bk.backend_channel_name,
          _origSubName: sub.sub_channel_name,
        }
        r._rowId = _chanRowId(r)
        rows.push(r)
      })
    })
  })
  channelsData.value = rows
}

function addChannelRow() {
  chanTempIdCounter++
  const r = {
    _rowId: `_new_${chanTempIdCounter}`,
    _isNew: true,
    channel_name: '',
    backend_channel_name: '',
    sub_channel_name: '',
  }
  channelsData.value = [...channelsData.value, r]
  channelChanges[r._rowId] = { action: 'create', data: { ...r } }
  scrollGridToEnd(channelsGridApi)
}

function deleteChannelRow(params) {
  const row = params.node.data
  if (row._isNew) {
    channelsData.value = channelsData.value.filter(r => r._rowId !== row._rowId)
    delete channelChanges[row._rowId]
  } else {
    channelChanges[row._rowId] = { action: 'delete', data: { ...row } }
    channelsData.value = channelsData.value.filter(r => r._rowId !== row._rowId)
  }
}

function onChanCellChanged(params) {
  const row = params.node.data
  if (row._isNew) {
    channelChanges[row._rowId] = { action: 'create', data: { ...row } }
  } else if (!channelChanges[row._rowId]) {
    channelChanges[row._rowId] = { action: 'update', data: { ...row } }
  } else {
    // Update data in-place for already-tracked rows
    channelChanges[row._rowId].data = { ...row }
  }
}

async function batchSaveChannels() {
  const items = Object.entries(channelChanges).map(([key, ch]) => ({
    row_key: key,
    action: ch.action,
    channel_name: ch.data.channel_name || '',
    backend_channel_name: ch.data.backend_channel_name || '',
    sub_channel_name: ch.data.sub_channel_name || '',
    // Use nullish coalescing so empty string '' is preserved as original value
    orig_channel_name: ch.data._origChannelName ?? ch.data.channel_name ?? '',
    orig_backend_channel_name: ch.data._origBackendName ?? ch.data.backend_channel_name ?? '',
    orig_sub_channel_name: ch.data._origSubName ?? ch.data.sub_channel_name ?? '',
  }))
  try {
    await api.batchChannels(items)
    Object.keys(channelChanges).forEach(k => delete channelChanges[k])
    await loadChannelTree()
    loadChannelsData()
    channelMsg.value = ''
  } catch (e) {
    channelMsg.value = '保存失败: ' + (e.response?.data?.detail || e.message)
    setTimeout(() => { channelMsg.value = '' }, 5000)
  }
}

// ── PartyInfo editing ──
const partyInfo = useEditableGrid({
  load: async () => { const r = await api.getPartyInfo(); return r.data.data },
  createEmpty: () => ({ party_type: 'our_company', name: '', address: '', phone: '',
    bank_name: '', bank_account: '', tax_id: '', notes: '' }),
  save: async (items) => {
    for (const ch of items) {
      const p = { party_type: ch.data.party_type || 'our_company', name: ch.data.name || '',
        address: ch.data.address || '', phone: ch.data.phone || '',
        bank_name: ch.data.bank_name || '', bank_account: ch.data.bank_account || '',
        tax_id: ch.data.tax_id || '', notes: ch.data.notes || '' }
      if (ch.action === 'create') await api.createPartyInfo(p)
      else if (ch.action === 'update') await api.updatePartyInfo(ch.data.id, p)
      else if (ch.action === 'delete') await api.deletePartyInfo(ch.data.id)
    }
  },
})

const PARTY_TYPE_MAP = { our_company: '我方公司', channel: '渠道', publisher: '研发' }

const partyInfoCols = [
  rowNoCol(),
  { field: 'party_type', headerName: '类型', width: 110, editable: true,
    cellEditor: 'agSelectCellEditor',
    cellEditorParams: { values: ['our_company', 'channel', 'publisher'] },
    valueFormatter: p => PARTY_TYPE_MAP[p.value] || p.value },
  { field: 'name', headerName: '主体名称', width: 180, editable: true },
  { field: 'address', headerName: '地址', width: 260, editable: true },
  { field: 'phone', headerName: '联系电话', width: 140, editable: true },
  { field: 'bank_name', headerName: '开户银行', width: 200, editable: true },
  { field: 'bank_account', headerName: '银行账号', width: 180, editable: true },
  { field: 'tax_id', headerName: '税号', width: 160, editable: true },
  { field: 'notes', headerName: '备注', width: 200, editable: true },
  {
    headerName: '操作', width: 80, editable: false, sortable: false, filter: false,
    cellRenderer: () => '<button class="btn-del-row" data-action="delete">删除</button>',
    onCellClicked: p => { if (p.event.target.dataset.action === 'delete') partyInfo.removeRow(p.node.data) },
  },
]

// ── Income Split Config ──
const incomeSplitMsg = ref('')
const incomeSplit = useEditableGrid({
  load: async () => { const r = await api.getIncomeSplitConfigs(); return r.data.data },
  createEmpty: () => ({ channel_name: '', game_id: '', game_name: '',
    split_rate: 0, channel_fee_rate: 0, tax_rate: 0, effective_from: '', effective_to: null }),
  save: async (items) => {
    const payload = []
    let deleteCount = 0
    for (const ch of items) {
      if (ch.action === 'delete') {
        payload.push({
          id: ch.data.id, action: 'delete',
          channel_name: ch.data.channel_name || '', game_id: ch.data.game_id || '',
        })
        deleteCount++
        continue
      }
      payload.push({
        channel_name: ch.data.channel_name || '', game_id: ch.data.game_id || '',
        split_rate: Number(ch.data.split_rate) || 0,
        channel_fee_rate: Number(ch.data.channel_fee_rate) || 0,
        tax_rate: Number(ch.data.tax_rate) || 0,
        effective_from: ch.data.effective_from || '', effective_to: ch.data.effective_to || null,
      })
    }
    if (payload.length) await api.batchIncomeSplitConfig(payload)
    if (deleteCount) incomeSplitMsg.value = `已删除 ${deleteCount} 条`
    setTimeout(() => { incomeSplitMsg.value = '' }, 3000)
  },
})

function copyIncomeSplitRow(params) {
  const row = params.node.data
  const result = incomeSplit.copyRow(row, {
    channel_name: row.channel_name || '', game_id: row.game_id || '',
    game_name: row.game_name || '', split_rate: row.split_rate ?? 0,
    channel_fee_rate: row.channel_fee_rate ?? 0, tax_rate: row.tax_rate ?? 0,
    effective_from: '', effective_to: null,
  })
  if (result) {
    nextTick(() => {
      const api = incomeSplitGridApi.value
      if (api) api.ensureIndexVisible(result.idx + 1, 'top')
    })
  }
}

const incomeSplitCols = [
  rowNoCol(),
  { field: 'channel_name', headerName: '渠道名称', width: 140, editable: true },
  { field: 'game_id', headerName: '游戏编号', width: 120, editable: true },
  { field: 'game_name', headerName: '游戏名称', width: 160, editable: false },
  rateCol('split_rate', '分成比例'),
  rateCol('channel_fee_rate', '渠道费率'),
  rateCol('tax_rate', '税率', 100),
  dateCol('effective_from', '生效日期'),
  dateCol('effective_to', '失效日期'),
  { headerName: '操作', width: 110, editable: false, sortable: false, filter: false,
    cellRenderer: () => '<button class="btn-copy-row" data-action="copy">复制</button><button class="btn-del-row" data-action="delete">删除</button>',
    onCellClicked: p => {
      if (p.event.target.dataset.action === 'copy') copyIncomeSplitRow(p)
      else if (p.event.target.dataset.action === 'delete') incomeSplit.removeRow(p.node.data)
    } },
]
// ── Payment Split Config ──
// ── Payment Split Config ──
const paymentSplitMsg = ref('')
const paymentSplit = useEditableGrid({
  load: async () => { const r = await api.getPaymentSplitConfigs(); return r.data.data },
  createEmpty: () => ({ publisher_name: '', game_id: '', game_name: '',
    split_rate: 0, channel_fee_rate: 0, tax_rate: 0, fixed_fee: 0,
    effective_from: '', effective_to: null }),
  save: async (items) => {
    const payload = []
    let deleteCount = 0
    for (const ch of items) {
      if (ch.action === 'delete') {
        payload.push({
          id: ch.data.id, action: 'delete',
          publisher_name: ch.data.publisher_name || '', game_id: ch.data.game_id || '',
        })
        deleteCount++
        continue
      }
      payload.push({
        publisher_name: ch.data.publisher_name || '', game_id: ch.data.game_id || '',
        split_rate: Number(ch.data.split_rate) || 0,
        channel_fee_rate: Number(ch.data.channel_fee_rate) || 0,
        tax_rate: Number(ch.data.tax_rate) || 0,
        fixed_fee: Number(ch.data.fixed_fee) || 0,
        effective_from: ch.data.effective_from || '', effective_to: ch.data.effective_to || null,
      })
    }
    if (payload.length) await api.batchPaymentSplitConfig(payload)
    if (deleteCount) paymentSplitMsg.value = `已删除 ${deleteCount} 条`
    setTimeout(() => { paymentSplitMsg.value = '' }, 3000)
  },
})

function copyPaymentSplitRow(params) {
  const row = params.node.data
  const result = paymentSplit.copyRow(row, {
    publisher_name: row.publisher_name || '', game_id: row.game_id || '',
    game_name: row.game_name || '', split_rate: row.split_rate ?? 0,
    channel_fee_rate: row.channel_fee_rate ?? 0, tax_rate: row.tax_rate ?? 0,
    fixed_fee: row.fixed_fee ?? 0, effective_from: '', effective_to: null,
  })
  if (result) {
    nextTick(() => {
      const api = paymentSplitGridApi.value
      if (api) api.ensureIndexVisible(result.idx + 1, 'top')
    })
  }
}

const paymentSplitCols = [
  rowNoCol(),
  { field: 'publisher_name', headerName: '研发商户', width: 140, editable: true },
  { field: 'game_id', headerName: '游戏编号', width: 120, editable: true },
  { field: 'game_name', headerName: '游戏名称', width: 160, editable: false },
  rateCol('split_rate', '分成比例'),
  rateCol('channel_fee_rate', '渠道费率'),
  rateCol('tax_rate', '税率', 100),
  { field: 'fixed_fee', headerName: '固定费用', width: 120, editable: true,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '0',
    cellStyle: { textAlign: 'right' },
    valueParser: p => { const v = parseFloat(p.newValue); return isNaN(v) ? 0 : v } },
  dateCol('effective_from', '生效日期'),
  dateCol('effective_to', '失效日期'),
  { headerName: '操作', width: 110, editable: false, sortable: false, filter: false,
    cellRenderer: () => '<button class="btn-copy-row" data-action="copy">复制</button><button class="btn-del-row" data-action="delete">删除</button>',
    onCellClicked: p => {
      if (p.event.target.dataset.action === 'copy') copyPaymentSplitRow(p)
      else if (p.event.target.dataset.action === 'delete') paymentSplit.removeRow(p.node.data)
    } },
]
// ── Grid API refs for auto-scroll ──
const gamesGridApi = ref(null)
const companiesGridApi = ref(null)
const publishersGridApi = ref(null)
const channelsGridApi = ref(null)
const partyInfoGridApi = ref(null)
const incomeSplitGridApi = ref(null)
const paymentSplitGridApi = ref(null)

function onGamesGridReady(params) { gamesGridApi.value = params.api }
function onCompaniesGridReady(params) { companiesGridApi.value = params.api }
function onPublishersGridReady(params) { publishersGridApi.value = params.api }
function onChannelsGridReady(params) { channelsGridApi.value = params.api }
function onPartyInfoGridReady(params) { partyInfoGridApi.value = params.api }
function onIncomeSplitGridReady(params) { incomeSplitGridApi.value = params.api }
function onPaymentSplitGridReady(params) { paymentSplitGridApi.value = params.api }
function scrollGridToEnd(apiRef) {
  nextTick(() => {
    const api = apiRef.value
    if (!api) return
    const count = api.getDisplayedRowCount()
    if (count > 0) {
      api.ensureIndexVisible(count - 1, 'top')
      setTimeout(() => {
        const cols = api.getColumns()
        if (cols.length > 1) api.startEditingCell({ rowIndex: count - 1, colKey: cols[1].getColId() })
      }, 150)
    }
  })
}

// ── Change tracking ──
const changes = reactive({
  games: {},
  companies: {},
  publishers: {},
})
let tempIdCounter = 0

const defaultColDef = {
  sortable: true,
  filter: true,
  resizable: true,
  editable: true,
}

// ── Column defs with delete column ──

const gameCols = [
  { field: 'game_id', headerName: '游戏编号', editable: true, width: 120 },
  { field: 'game_name', headerName: '游戏名称', editable: true, width: 180 },
  { field: 'game_backend_name', headerName: '游戏后台名称', editable: true, width: 180 },
  {
    field: 'discount_rate', headerName: '折扣率', width: 140,
    editable: true,
    valueFormatter: p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '',
    valueParser: p => {
      const v = parseFloat(p.newValue)
      return isNaN(v) ? 0 : v / 100
    },
    cellEditorParams: { useFormatter: true },
  },
  {
    headerName: '操作', width: 80, editable: false, sortable: false, filter: false,
    cellRenderer: () => '<button class="btn-del-row" data-action="delete">删除</button>',
    onCellClicked: p => { if (p.event.target.dataset.action === 'delete') deleteRow('games', p) },
  },
]

const companyCols = [
  { field: 'company_id', headerName: 'ID', width: 80, editable: false },
  { field: 'company_name', headerName: '公司名称', editable: true, width: 300 },
  {
    headerName: '操作', width: 80, editable: false, sortable: false, filter: false,
    cellRenderer: () => '<button class="btn-del-row" data-action="delete">删除</button>',
    onCellClicked: p => { if (p.event.target.dataset.action === 'delete') deleteRow('companies', p) },
  },
]

const publisherCols = [
  { field: 'publisher_id', headerName: 'ID', width: 80, editable: false },
  { field: 'publisher_name', headerName: '商户名称', editable: true, width: 300 },
  {
    headerName: '操作', width: 80, editable: false, sortable: false, filter: false,
    cellRenderer: () => '<button class="btn-del-row" data-action="delete">删除</button>',
    onCellClicked: p => { if (p.event.target.dataset.action === 'delete') deleteRow('publishers', p) },
  },
]

// ── Helpers ──

function getRowId(entity, row) {
  if (entity === 'games') return String(row._tempId ?? row.game_id ?? '')
  return String(row.company_id ?? row.publisher_id ?? row._tempId ?? '')
}

function hasChanges(entity) {
  return Object.keys(changes[entity]).length > 0
}

function changedCount(entity) {
  return Object.keys(changes[entity]).length
}

// ── Cell change tracking ──

function onCellChanged(entity, params) {
  const row = params.node.data
  const rowId = getRowId(entity, row)
  if (row._isNew) {
    changes[entity][rowId] = { action: 'create', data: { ...row } }
  } else if (!changes[entity][rowId] || changes[entity][rowId].action !== 'create') {
    changes[entity][rowId] = { action: 'update', data: { ...row } }
  }
}

// ── Add row ──

function addRow(entity) {
  tempIdCounter++
  const tempId = `_new_${tempIdCounter}`
  const emptyRow = { _isNew: true, _tempId: tempId }

  if (entity === 'games') {
    emptyRow.game_id = ''
    emptyRow.game_name = ''
    emptyRow.game_backend_name = ''
    emptyRow.discount_rate = 0
    gamesData.value = [...gamesData.value, emptyRow]
    changes.games[tempId] = { action: 'create', data: { ...emptyRow } }
    scrollGridToEnd(gamesGridApi)
  } else if (entity === 'companies') {
    emptyRow.company_name = ''
    companiesData.value = [...companiesData.value, emptyRow]
    changes.companies[tempId] = { action: 'create', data: { ...emptyRow } }
    scrollGridToEnd(companiesGridApi)
  } else if (entity === 'publishers') {
    emptyRow.publisher_name = ''
    publishersData.value = [...publishersData.value, emptyRow]
    changes.publishers[tempId] = { action: 'create', data: { ...emptyRow } }
    scrollGridToEnd(publishersGridApi)
  }
}

// ── Delete row ──

function deleteRow(entity, params) {
  const row = params.node.data
  const rowId = getRowId(entity, row)
  const dataRef = entity === 'games' ? gamesData : entity === 'companies' ? companiesData : publishersData

  if (row._isNew) {
    dataRef.value = dataRef.value.filter(r => getRowId(entity, r) !== rowId)
    delete changes[entity][rowId]
  } else {
    changes[entity][rowId] = { action: 'delete', data: { ...row } }
    dataRef.value = dataRef.value.filter(r => getRowId(entity, r) !== rowId)
  }
}

// ── Batch save ──

async function batchSave(entity) {
  const ch = changes[entity]
  const created = []
  const updated = []
  const deleted = []

  for (const [rowId, change] of Object.entries(ch)) {
    if (change.action === 'create') {
      if (entity === 'games') {
        created.push({
          game_id: change.data.game_id || '',
          game_name: change.data.game_name || '',
          game_backend_name: change.data.game_backend_name || null,
          discount_rate: Number(change.data.discount_rate) || 0,
        })
      } else if (entity === 'companies') {
        created.push({ company_name: change.data.company_name || '' })
      } else if (entity === 'publishers') {
        created.push({ publisher_name: change.data.publisher_name || '' })
      }
    } else if (change.action === 'update') {
      if (entity === 'games') {
        updated.push({
          game_id: change.data.game_id,
          game_name: change.data.game_name || '',
          game_backend_name: change.data.game_backend_name || null,
          discount_rate: Number(change.data.discount_rate) || 0,
        })
      } else if (entity === 'companies') {
        updated.push({
          company_id: Number(change.data.company_id),
          company_name: change.data.company_name || '',
        })
      } else if (entity === 'publishers') {
        updated.push({
          publisher_id: Number(change.data.publisher_id),
          publisher_name: change.data.publisher_name || '',
        })
      }
    } else if (change.action === 'delete') {
      if (entity === 'games') {
        deleted.push(change.data.game_id)
      } else if (entity === 'companies') {
        deleted.push(Number(change.data.company_id))
      } else if (entity === 'publishers') {
        deleted.push(Number(change.data.publisher_id))
      }
    }
  }

  try {
    const apiMethod = `batch${entity.charAt(0).toUpperCase() + entity.slice(1)}`
    await api[apiMethod]({ created, updated, deleted })
    changes[entity] = {}
    if (entity === 'games') await loadGames()
    else if (entity === 'companies') await loadCompanies()
    else if (entity === 'publishers') await loadPublishers()
  } catch (e) {
    alert('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

// ── Discard changes ──

async function discardChanges(entity) {
  changes[entity] = {}
  if (entity === 'games') await loadGames()
  else if (entity === 'companies') await loadCompanies()
  else if (entity === 'publishers') await loadPublishers()
}

function discardChannelChanges() {
  Object.keys(channelChanges).forEach(k => delete channelChanges[k])
  loadChannelTree().then(() => loadChannelsData())
}

function discardPubGameChanges() {
  Object.keys(pubGameChanges).forEach(k => delete pubGameChanges[k])
  pubGameDeletions.value = []
  if (selectedPublisher.value) {
    loadPublisherGames(selectedPublisher.value.publisher_id)
  }
}

// ── Company detail: project-level + game-level override ──

const selectedCompany = ref(null)
const projectCodes = ref([])

// Project-level grid
const companyProjects = ref([])
const projChanges = reactive({})
const projDeletions = ref([])
const projDirty = computed(() => Object.keys(projChanges).length > 0 || projDeletions.value.length > 0)
let projTempIdCounter = 0

// Game-level exceptions grid
const selectedProject = ref(null)
const projectGamesData = ref([])  // raw data from API

// Custom cell editor: searchable input + datalist for project_code
class CompGameProjectEditor {
  init(params) {
    this.params = params
    this.input = document.createElement('input')
    this.input.type = 'text'
    this.input.style.width = '100%'
    this.input.style.height = '100%'
    this.input.style.border = 'none'
    this.input.style.outline = 'none'
    this.input.style.padding = '0 8px'
    this.input.style.background = 'transparent'

    this.datalist = document.createElement('datalist')
    this.datalist.id = `_compGameDL_${Math.random().toString(36).slice(2)}`
    this.input.setAttribute('list', this.datalist.id)

    this.input.value = params.value || ''
  }

  getGui() {
    const container = document.createElement('div')
    container.style.width = '100%'
    container.style.height = '100%'
    container.appendChild(this.input)
    container.appendChild(this.datalist)
    const codes = this.params.context?.projectCodes || []
    codes.forEach(c => {
      const opt = document.createElement('option')
      opt.value = c.project_code
      opt.textContent = `${c.project_code} — ${c.project_name}`
      this.datalist.appendChild(opt)
    })
    setTimeout(() => {
      this.input.focus()
      this.input.select()
    }, 0)
    return container
  }

  getValue() { return this.input.value }
  isPopup() { return false }
}

// Custom cell editor for game override: dropdown to select company
class GameCompanyOverrideEditor {
  init(params) {
    this.params = params
    this.select = document.createElement('select')
    this.select.style.width = '100%'
    this.select.style.height = '100%'
    this.select.style.border = 'none'
    this.select.style.outline = 'none'
    this.select.style.background = 'transparent'
    this.select.style.fontSize = '13px'
    // Empty option = inherit (value: '' means reset to project default)
    const empty = document.createElement('option')
    empty.value = ''
    const projectComp = params.data.project_company_name || '项目默认'
    empty.textContent = `继承 (${projectComp})`
    this.select.appendChild(empty)
    // Other companies
    const allCompanies = params.context?.allCompanies || []
    allCompanies.forEach(c => {
      const opt = document.createElement('option')
      opt.value = String(c.company_id)
      opt.textContent = c.company_name
      if (c.company_id === params.data.effective_company_id && params.data.is_override) {
        opt.selected = true
      }
      this.select.appendChild(opt)
    })
    // Commit immediately on selection change
    this.select.addEventListener('change', () => {
      params.stopEditing()
    })
  }

  getGui() { return this.select }

  getValue() {
    const v = this.select.value
    return v ? parseInt(v) : ''  // '' = reset to inherit
  }

  isPopup() { return false }
}

const companyProjectCols = computed(() => [
  { field: 'project_code', headerName: '项目编号', width: 140, editable: true,
    cellEditor: CompGameProjectEditor,
  },
  { field: 'channel_name', headerName: '渠道（可选）', width: 120, editable: true,
    cellEditor: 'agSelectCellEditor',
    cellEditorParams: {
      values: ['全部渠道', ...channelCategories.value.map(c => c.channel_name)],
    },
    valueFormatter: p => p.value || '全部渠道',
  },
  { field: 'project_name', headerName: '项目名称', width: 150, editable: false },
  { field: 'game_count', headerName: '游戏数', width: 70, editable: false,
    cellStyle: { textAlign: 'center' },
  },
  {
    headerName: '操作', width: 70, editable: false, sortable: false, filter: false,
    cellRenderer: params => {
      const btn = document.createElement('button')
      btn.className = 'btn-del-row'
      btn.textContent = '删除'
      btn.onclick = () => deleteCompanyProjectRow(params)
      return btn
    },
  },
])

const projectGameOverrideCols = computed(() => [
  { field: 'game_id', headerName: '游戏编号', width: 100 },
  { field: 'game_name', headerName: '游戏名称', width: 140 },
  { field: 'project_code', headerName: '所属项目', width: 100 },
  {
    headerName: '生效公司', width: 220, editable: true,
    cellEditor: GameCompanyOverrideEditor,
    cellEditorParams: {},
    valueGetter: p => {
      if (!p.data) return ''
      if (p.data.is_override) return p.data.effective_company_id
      return ''  // inherit → empty
    },
    valueSetter: p => {
      if (!p.data) return false
      const newVal = p.newValue
      if (newVal === '' || newVal === null || newVal === undefined) {
        handleResetOverride(p.data)
      } else {
        handleGameOverride(p.data, parseInt(newVal))
      }
      return false  // don't update grid directly — backend reload refreshes data
    },
    cellStyle: p => {
      if (p.data?.is_override) {
        return { fontWeight: 700, color: 'var(--color-primary)' }
      }
      return { color: 'var(--text-light)' }
    },
    valueFormatter: p => {
      if (!p.data) return ''
      if (p.data.is_override) {
        return p.data.effective_company_name
      }
      return `继承 (${p.data.project_company_name || '项目默认'})`
    },
    cellClassRules: {
      'cell-locked': p => p.data && p.data.is_override,
    },
  },
  {
    headerName: '操作', width: 70, editable: false, sortable: false, filter: false,
    cellRenderer: params => {
      if (!params.data) return ''
      if (!params.data.is_override) {
        return '<span style="color:var(--text-light);font-size:12px">—</span>'
      }
      const btn = document.createElement('button')
      btn.className = 'btn-sm'
      btn.textContent = '重置'
      btn.style.cssText = 'font-size:12px;padding:2px 6px;border:1px solid var(--border-default);border-radius:4px;background:var(--bg-card);color:var(--text-primary);cursor:pointer'
      btn.onclick = () => handleResetOverride(params.data)
      return btn
    },
  },
])

async function onCompanySelected(event) {
  selectedCompany.value = event.data
  Object.keys(projChanges).forEach(k => delete projChanges[k])
  projDeletions.value = []
  selectedProject.value = null
  projectGamesData.value = []
  await Promise.all([
    loadCompanyProjects(event.data.company_id),
    loadProjectCodes(),
  ])
}

async function loadProjectCodes() {
  try {
    const r = await api.getProjectCodes()
    projectCodes.value = r.data.data || []
  } catch (e) { logError('loadProjectCodes', e) }
}

async function loadCompanyProjects(companyId) {
  try {
    const r = await api.getCompanyProjects(companyId)
    companyProjects.value = (r.data.data || []).map(p => ({
      ...p,
      _key: `${p.project_code || '_none'}::${p.channel_id ?? 0}`,
    }))
  } catch (e) { logError('loadCompanyProjects', e) }
}

// ── Project-level operations ──

function addCompanyProjectRow() {
  projTempIdCounter++
  const tempId = `_newProj_${projTempIdCounter}`
  const row = {
    _isNew: true,
    _tempId: tempId,
    project_code: '',
    channel_id: null,
    channel_name: '',
    project_name: '',
    game_count: '-',
  }
  companyProjects.value = [...companyProjects.value, row]
  projChanges[tempId] = { ...row }
}

function onProjChanged(event) {
  const row = event.data
  const field = event.colDef.field
  const key = row._isNew ? row._tempId : row._key

  if (field === 'project_code' && row.project_code) {
    const found = projectCodes.value.find(p => p.project_code === row.project_code)
    if (found) {
      row.project_name = found.project_name
      event.api.refreshCells({ rowNodes: [event.node], columns: ['project_name'] })
    }
  }

  if (field === 'channel_name') {
    const chName = row.channel_name
    if (chName && chName !== '全部渠道') {
      const ch = channelCategories.value.find(c => c.channel_name === chName)
      row.channel_id = ch ? ch.channel_id : null
    } else {
      row.channel_id = null
    }
  }

  projChanges[key] = { ...row }
}

async function saveCompanyProjects() {
  const cid = selectedCompany.value?.company_id
  if (!cid) return
  try {
    // Deletions — delete by project_code
    for (const del of projDeletions.value) {
      await api.deleteCompanyGamesByProject({
        company_id: del.company_id,
        project_code: del.project_code,
        channel_id: del.channel_id,
      })
    }
    projDeletions.value = []
    // New/updated project rows
    const newRows = Object.values(projChanges).filter(r => r.project_code)
    if (newRows.length) {
      const items = newRows.map(r => ({
        company_id: cid,
        project_code: r.project_code,
        channel_id: r.channel_id || null,
      }))
      const r = await api.batchCompanyGames(items)
      alert(`已关联 ${r.data.game_count} 个游戏`)
    }
    Object.keys(projChanges).forEach(k => delete projChanges[k])
    selectedProject.value = null
    projectGamesData.value = []
    await loadCompanyProjects(cid)
  } catch (e) {
    alert('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

function discardProjChanges() {
  Object.keys(projChanges).forEach(k => delete projChanges[k])
  projDeletions.value = []
  selectedProject.value = null
  projectGamesData.value = []
  if (selectedCompany.value) {
    loadCompanyProjects(selectedCompany.value.company_id)
  }
}

function deleteCompanyProjectRow(params) {
  const row = params.node.data
  if (row._isNew) {
    companyProjects.value = companyProjects.value.filter(r => r._tempId !== row._tempId)
    delete projChanges[row._tempId]
  } else {
    // Mark for deletion by project_code
    projDeletions.value.push({
      company_id: selectedCompany.value?.company_id,
      project_code: row.project_code,
      channel_id: row.channel_id ?? null,
    })
    companyProjects.value = companyProjects.value.filter(r => r._key !== row._key)
  }
}

// ── Game-level overrides ──

async function onProjRowSelected(event) {
  const row = event.data
  if (!row || row._isNew) {
    selectedProject.value = null
    projectGamesData.value = []
    return
  }
  selectedProject.value = row
  await loadProjectGames(row)
}

async function loadProjectGames(projRow) {
  try {
    const params = { project_code: projRow.project_code }
    if (projRow.channel_id != null) {
      params.channel_id = projRow.channel_id
    }
    const r = await api.getProjectGames(selectedCompany.value.company_id, params)
    projectGamesData.value = r.data.data || []
  } catch (e) { logError('loadProjectGames', e) }
}

async function handleGameOverride(row, newCompanyId) {
  if (!newCompanyId || !selectedCompany.value) return
  try {
    await api.upsertCompanyGameOverride({
      company_id: newCompanyId,
      game_id: row.game_id,
      channel_id: selectedProject.value?.channel_id ?? null,
    })
    // Refresh the project games list
    if (selectedProject.value) {
      await loadProjectGames(selectedProject.value)
    }
    // Refresh projects (game_count may change or new project grouping)
    await loadCompanyProjects(selectedCompany.value.company_id)
  } catch (e) {
    alert('覆盖失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function handleResetOverride(row) {
  if (!selectedCompany.value) return
  // Reset = delete the game-level override, back to project default
  // If the effective company is different from the project company_id,
  // we need to delete the override entry.
  const projCompId = row.project_company_id
  try {
    // Delete override — the backend deletes the mapping for (game_id, channel_id)
    await api.removeCompanyGameOverride({
      company_id: row.effective_company_id || projCompId,
      game_id: row.game_id,
      channel_id: selectedProject.value?.channel_id ?? null,
    })
    // Add back project-level mapping
    if (projCompId) {
      await api.upsertCompanyGameOverride({
        company_id: projCompId,
        game_id: row.game_id,
        channel_id: selectedProject.value?.channel_id ?? null,
      })
    }
    if (selectedProject.value) {
      await loadProjectGames(selectedProject.value)
    }
    await loadCompanyProjects(selectedCompany.value.company_id)
  } catch (e) {
    alert('重置失败: ' + (e.response?.data?.detail || e.message))
  }
}

// ── Load data ──

async function loadCompanies() {
  const r = await api.getCompanies()
  companiesData.value = r.data.data
}
async function loadPublishers() {
  const r = await api.getPublishers()
  publishersData.value = r.data.data
}
async function loadChannelTree() {
  const r = await api.getChannelTree()
  channelCategories.value = r.data.data
}

// ── Publisher detail: games / project mapping ──

const selectedPublisher = ref(null)
const publisherGamesData = ref([])
const pubGameChanges = reactive({})
const pubGameDeletions = ref([])

const pubGameDirty = computed(() => Object.keys(pubGameChanges).length > 0 || pubGameDeletions.value.length > 0)
let pubGameTempIdCounter = 0

const publisherGameCols = [
  { field: 'game_id', headerName: '游戏编号', editable: true, width: 120 },
  { field: 'game_name', headerName: '游戏名称', editable: false, width: 150 },
  { field: 'project_code', headerName: '项目编号', editable: true, width: 130 },
  { field: 'project_name', headerName: '项目名称', editable: true, width: 200 },
  {
    headerName: '操作', width: 70, editable: false, sortable: false, filter: false,
    cellRenderer: params => {
      const btn = document.createElement('button')
      btn.className = 'btn-del-row'
      btn.textContent = '删除'
      btn.onclick = () => deletePublisherGameRow(params)
      return btn
    },
  },
]

async function onPublisherSelected(event) {
  // 跳过未保存的新行（无 publisher_id），避免 422 错误
  if (!event.data?.publisher_id) return
  selectedPublisher.value = event.data
  await loadPublisherGames(event.data.publisher_id)
}

async function loadPublisherGames(publisherId) {
  if (!publisherId) return
  const r = await api.getPublisherGames(publisherId)
  const gameMap = {}
  gamesData.value.forEach(g => { gameMap[g.game_id] = g.game_name })
  const rows = r.data.data.map(item => ({
    ...item,
    game_name: gameMap[item.game_id] || '',
  }))
  publisherGamesData.value = rows
  Object.keys(pubGameChanges).forEach(k => delete pubGameChanges[k])
  pubGameDeletions.value = []
}

function addPublisherGameRow() {
  pubGameTempIdCounter++
  const tempId = `_new_${pubGameTempIdCounter}`
  const row = {
    _isNew: true,
    _tempId: tempId,
    publisher_id: selectedPublisher.value?.publisher_id,
    game_id: '',
    game_name: '',
    project_code: '',
    project_name: '',
  }
  publisherGamesData.value = [...publisherGamesData.value, row]
  pubGameChanges[tempId] = { ...row }
}

function deletePublisherGameRow(params) {
  const row = params.node.data
  if (row._isNew) {
    publisherGamesData.value = publisherGamesData.value.filter(r => r._tempId !== row._tempId)
    delete pubGameChanges[row._tempId]
  } else {
    publisherGamesData.value = publisherGamesData.value.filter(r => r.id !== row.id)
    pubGameDeletions.value = [...pubGameDeletions.value, { publisher_id: row.publisher_id, game_id: row.game_id }]
  }
}

function onPubGameChanged(event) {
  const row = event.data
  const field = event.colDef.field
  const key = row._isNew ? row._tempId : `${row.publisher_id}_${row.game_id}`

  // Auto-fill game_name when game_id is entered
  if (field === 'game_id' && row.game_id) {
    const map = {}
    gamesData.value.forEach(g => { map[g.game_id] = g.game_name })
    if (map[row.game_id]) {
      row.game_name = map[row.game_id]
      event.api.refreshCells({ rowNodes: [event.node], columns: ['game_name'] })
    }
  }

  // Auto-fill project_name when project_code is entered
  if (field === 'project_code' && row.project_code && !row.project_name) {
    const found = publisherGamesData.value.find(
      r => r.project_code === row.project_code && r.project_name
    )
    if (found) {
      row.project_name = found.project_name
      event.api.refreshCells({ rowNodes: [event.node], columns: ['project_name'] })
    }
  }

  pubGameChanges[key] = { ...row }
}

async function savePublisherGames() {
  try {
    // 1. Process deletions first
    if (pubGameDeletions.value.length) {
      await api.deletePublisherGames(pubGameDeletions.value)
      pubGameDeletions.value = []
    }
    // 2. Process upserts
    const updates = Object.values(pubGameChanges).map(row => {
      const pid = row.publisher_id ?? selectedPublisher.value?.publisher_id
      return {
        publisher_id: pid,
        game_id: row.game_id || '',
        project_code: row.project_code || null,
        project_name: row.project_name || null,
      }
    })
    if (updates.length) {
      await api.batchPublisherGames(updates)
    }
    Object.keys(pubGameChanges).forEach(k => delete pubGameChanges[k])
    if (selectedPublisher.value) {
      await loadPublisherGames(selectedPublisher.value.publisher_id)
    }
  } catch (e) {
    alert('保存项目信息失败: ' + (e.response?.data?.detail || e.message))
  }
}

// ── Clean selection when switching tabs ──
watch(tab, () => { selectedPublisher.value = null; selectedCompany.value = null })

function onKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    const t = tab.value
    if (t === 'games' && hasChanges('games')) batchSave('games')
    else if (t === 'companies' && hasChanges('companies')) batchSave('companies')
    else if (t === 'publishers' && hasChanges('publishers')) batchSave('publishers')
    else if (t === 'channels' && chanDirty.value) batchSaveChannels()
    else if (t === 'partyinfo' && partyInfo.dirty) savePartyInfo()
    else if (t === 'income_split' && incomeSplit.dirty) saveIncomeSplit()
    else if (t === 'payment_split' && paymentSplit.dirty) savePaymentSplit()
  }
}

// ── 原始流水表 (ChannelSettlement) ──
const channelSettlementData = ref([])
const channelSettlementTotal = ref(0)
const channelSettlementGridApi = ref(null)

const channelSettlementCols = [
  { field: 'rowNo', headerName: '#', width: 50, pinned: 'left', sortable: false, filter: false,
    valueFormatter: p => (p.node?.rowIndex ?? 0) + 1,
    cellStyle: { color: 'var(--text-light)', backgroundColor: 'var(--palette-gray-50)', textAlign: 'center' } },
  { field: 'channel_id', headerName: '渠道ID', width: 80, pinned: 'left' },
  { field: 'channel_name', headerName: '渠道名称', width: 160, pinned: 'left' },
  { field: 'game_id', headerName: '游戏编号', width: 110 },
  { field: 'game_name', headerName: '游戏名称', width: 220 },
  { field: 'month', headerName: '月份', width: 100 },
  { field: 'raw_revenue', headerName: '原始流水', width: 150,
    valueFormatter: p => p.value != null ? Number(p.value).toLocaleString('zh-CN', { minimumFractionDigits: 2 }) : '-',
    cellStyle: { textAlign: 'right', fontWeight: 600 } },
]

function onChannelSettlementGridReady(params) {
  channelSettlementGridApi.value = params.api
}

async function loadChannelSettlements() {
  try {
    const r = await api.getChannelSettlements()
    channelSettlementData.value = r.data.data
    channelSettlementTotal.value = r.data.total
  } catch (e) {
    logError('loadChannelSettlements', e)
    channelSettlementData.value = []
    channelSettlementTotal.value = 0
  }
}

// ── Channel-Party Mapping ──

const chanCompRows = ref([])
const chanCompChanges = reactive({})
const chanCompGridApi = ref(null)

const chanCompCols = computed(() => [
  { field: 'channel_name', headerName: '渠道', width: 200, editable: true,
    cellEditor: SearchSelectCellEditor,
    cellEditorParams: {
      values: channelCategories.value.map(c => c.channel_name),
    },
  },
  { field: 'party_name', headerName: '主体名称', width: 240, editable: true,
    cellEditor: SearchSelectCellEditor,
    cellEditorParams: {
      values: partyInfo.data.map(p => p.name),
    },
  },
  {
    headerName: '操作', width: 70, editable: false, sortable: false, filter: false,
    cellRenderer: params => {
      const btn = document.createElement('button')
      btn.className = 'btn-del-row'
      btn.textContent = '删除'
      btn.onclick = () => deleteChanCompRow(params)
      return btn
    },
  },
])

async function loadChannelCompanyMappings() {
  try {
    const r = await api.getChannelPartyMappings()
    chanCompRows.value = (r.data.data || []).map(m => ({ ...m, _key: m.channel_id }))
  } catch (e) { logError('loadChannelCompanyMappings', e) }
}

function addChanCompRow() {
  const row = { _isNew: true, _tempId: `_cc_${Date.now()}`, channel_name: '', party_name: '', channel_id: null, party_info_id: null }
  chanCompRows.value = [...chanCompRows.value, row]
  chanCompChanges[row._tempId] = { ...row }
}

function onChanCompChanged(event) {
  const row = event.data
  const field = event.colDef.field
  const key = row._isNew ? row._tempId : row._key

  if (field === 'channel_name') {
    const ch = channelCategories.value.find(c => c.channel_name === row.channel_name)
    row.channel_id = ch ? ch.channel_id : null
  }
  if (field === 'party_name') {
    const pi = partyInfo.data.find(p => p.name === row.party_name)
    row.party_info_id = pi ? pi.id : null
  }

  chanCompChanges[key] = { ...row }
}

async function saveChannelCompanyMappings() {
  const changes = Object.values(chanCompChanges)
  if (!changes.length) return

  // Validate that all values exist in reference lists
  const chanNames = channelCategories.value.map(c => c.channel_name)
  const partyNames = partyInfo.data.map(p => p.name)
  for (const r of changes) {
    if (!r.channel_name || !chanNames.includes(r.channel_name)) {
      alert(`保存失败: "${r.channel_name || '(空)'}" 不是有效的渠道名称，请从下拉匹配列表中选择`)
      return
    }
    if (!r.party_name || !partyNames.includes(r.party_name)) {
      alert(`保存失败: "${r.party_name || '(空)'}" 不是有效的主体名称，请从下拉匹配列表中选择`)
      return
    }
  }

  try {
    for (const r of changes) {
      await api.saveChannelPartyMapping({ channel_id: r.channel_id, party_info_id: r.party_info_id })
    }
    Object.keys(chanCompChanges).forEach(k => delete chanCompChanges[k])
    await loadChannelCompanyMappings()
  } catch (e) {
    alert('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function deleteChanCompRow(params) {
  const row = params.data
  if (row._isNew) {
    chanCompRows.value = chanCompRows.value.filter(r => r._tempId !== row._tempId)
    delete chanCompChanges[row._tempId]
    return
  }
  if (!confirm(`确认删除 ${row.channel_name} -> ${row.party_name} 的映射？`)) return
  try {
    await api.deleteChannelPartyMapping(row.channel_id)
    await loadChannelCompanyMappings()
  } catch (e) {
    alert('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

function discardChanCompChanges() {
  Object.keys(chanCompChanges).forEach(k => delete chanCompChanges[k])
  chanCompRows.value = chanCompRows.value.filter(r => !r._isNew)
}

// ── Read-only-safe save wrappers ──
// These catch 403 (LAN read-only mode) and show a toast instead of silent failure.

async function savePartyInfo() {
  if (!partyInfo.dirty) return
  try {
    await partyInfo.saveAll()
  } catch (e) {
    const msg = e.response?.data?.detail || e.message || '保存失败'
    toast.error('保存失败: ' + msg)
  }
}

async function saveIncomeSplit() {
  if (!incomeSplit.dirty) return
  try {
    await incomeSplit.saveAll()
  } catch (e) {
    const msg = e.response?.data?.detail || e.message || '保存失败'
    toast.error('保存失败: ' + msg)
  }
}

async function savePaymentSplit() {
  if (!paymentSplit.dirty) return
  try {
    await paymentSplit.saveAll()
  } catch (e) {
    const msg = e.response?.data?.detail || e.message || '保存失败'
    toast.error('保存失败: ' + msg)
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  Promise.all([
    loadGames(),
    loadCompanies(),
    loadPublishers(),
    loadChannelTree(),
  ]).then(() => {
    loadChannelsData()
  })
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
h2 { margin-bottom: 16px; font-size: 20px; }
.tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tabs button {
  padding: 6px 16px; border: 1px solid var(--border-default); border-radius: 6px;
  background: var(--bg-card); cursor: pointer; font-size: 13px; color: var(--text-secondary);
}
.tabs button.active { background: var(--color-primary); color: var(--text-on-primary); border-color: var(--color-primary); }

.tab-content { background: var(--bg-card); padding: 16px; border-radius: 8px; box-shadow: var(--shadow-card); }

.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; position: sticky; top: 0; z-index: 10; background: var(--bg-card); padding: 4px 0; }
.btn-add { padding: 6px 14px; background: var(--bg-tag-blue); border: 1px solid var(--color-info); border-radius: 6px; cursor: pointer; font-size: 13px; color: var(--color-info); }
.btn-save { padding: 6px 16px; background: var(--color-success); color: var(--text-on-primary); border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-save:disabled { background: var(--text-light); cursor: not-allowed; }
.btn-discard { padding: 6px 14px; background: var(--bg-card); border: 1px solid var(--color-warning); color: var(--color-warning); border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-discard:hover { background: var(--color-warning); color: var(--text-on-primary); }
.change-badge { font-size: 12px; color: var(--color-warning); font-weight: 600; }
.toolbar-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.toolbar-sep { width: 1px; height: 20px; background: var(--border-default); }
.toolbar-hint { font-size: 12px; color: var(--text-muted); margin-left: auto; }

.grid { width: 100%; }

:deep(.btn-copy-row) {
  padding: 2px 8px; background: var(--bg-tag-green); color: var(--color-success); border: 1px solid var(--color-success);
  border-radius: 4px; cursor: pointer; font-size: 12px; margin-right: 4px;
}
:deep(.btn-copy-row:hover) { opacity: 0.8; }
:deep(.btn-del-row) {
  padding: 2px 8px; background: var(--bg-badge-error); color: var(--color-danger); border: 1px solid var(--color-danger);
  border-radius: 4px; cursor: pointer; font-size: 12px;
}
:deep(.btn-del-row:hover) { opacity: 0.8; }

:deep(.ag-cell) { border-right: 1px solid var(--border-cell); }
:deep(.ag-header-cell) { border-right: 1px solid var(--border-header-cell); font-weight: 600; }
.toolbar-info { font-size: 13px; color: var(--text-secondary); }

.publisher-tab { padding-bottom: 8px; }

.publisher-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.publisher-list-panel {
  flex: 0 0 800px;
  min-width: 360px;
}

.detail-panel {
  flex: 1;
  min-width: 0;
  background: var(--palette-gray-80);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 12px;
  position: sticky;
  top: 80px;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.detail-header h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-primary);
}

.detail-grid {
  width: 100%;
}

.detail-section {
  margin-bottom: var(--space-lg);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: var(--space-md);
}

.detail-section .detail-header {
  margin-bottom: var(--space-sm);
}

.section-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

/* ── Bill Template styles ── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { font-size: 15px; margin: 0; }
.list-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.list-table th { text-align: left; padding: 8px; border-bottom: 2px solid var(--border-light); font-weight: 600; color: var(--text-secondary); }
.list-table td { padding: 6px 8px; border-bottom: 1px solid var(--border-light); }
.list-table tr:hover td { background: var(--palette-gray-50); }
.muted { color: var(--text-light); font-size: 13px; }
.tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--border-cell); color: var(--text-muted); }
.btn-sm {
  padding: 2px 10px; font-size: 12px; border: 1px solid var(--color-primary); border-radius: 4px;
  background: var(--bg-card); color: var(--color-primary); cursor: pointer;
}
.btn-sm:hover { background: var(--color-primary); color: var(--text-on-primary); }
.btn-sm-danger { border-color: var(--color-danger); color: var(--color-danger); }
.btn-sm-danger:hover { background: var(--color-danger); color: var(--text-on-primary); }
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal {
  background: #fff; border-radius: 10px; padding: 24px; width: 400px; box-shadow: 0 8px 30px rgba(0,0,0,0.15);
}
.modal h3 { font-size: 16px; margin-bottom: 12px; }
.modal p { font-size: 13px; color: #666; margin-bottom: 8px; }
.modal input {
  width: 100%; padding: 8px; border: 1px solid #d0d5dd; border-radius: 4px;
  font-size: 14px; margin: 8px 0; box-sizing: border-box;
}
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.form-group { margin-bottom: 10px; }
.form-group label { display: block; font-size: 13px; color: #555; margin-bottom: 4px; font-weight: 600; }
.form-group input { width: 100%; padding: 8px 12px; border: 1px solid #d0d5dd; border-radius: 4px; font-size: 14px; box-sizing: border-box; }
.error-msg { color: #dc2626; font-size: 13px; }
.btn-primary { border-color: #2563eb; color: #2563eb; }
.btn-primary:hover { background: #2563eb; color: #fff; }
.btn-danger { border-color: #e74c3c; color: #e74c3c; }
.btn-danger:hover { background: #e74c3c; color: #fff; }
</style>
