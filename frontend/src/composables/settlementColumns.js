/**
 * 结算查询字段映射索引 — 前后端字段契约的唯一真相源
 *
 * 后端数据源：
 *   query_income_settlement()   → GET /api/settlement/income
 *   query_payment_settlement()  → GET /api/settlement/payment
 *   query_channel_settlements() → GET /api/settlement/channel-settlements
 *
 * 核心理念：
 *   实体 = id + name 不可分割的一组。channel_id/channel_name 不是两个独立字段，
 *   而是同一个「渠道实体」的标识符和展示名。列定义由实体展开自动生成。
 *
 * 数据源链路（2026-06 重构后）：
 *   raw_settlements         → 聚合表 (channel_id, game_id, month)              ← 主表
 *   channel_categories      → JOIN channel_name                                ← channel 实体
 *   games                   → JOIN game_id, game_name, discount_rate           ← game 实体
 *   publishers              → JOIN publisher_name                              ← publisher 实体
 *   publisher_game_mapping  → JOIN project_code, project_name
 *   company_game_mapping + companies → 子查询 company_name
 *   deductions              → 预取 (channel_id, game_id, month) 三维键         ← 扣除明细
 *   channel_locks           → 预取 (channel_id, game_id, month) 三维键         ← 锁定权威
 *   publisher_locks         → 预取 (publisher_id, game_id, month) 三维键
 *   income_split_config     → 预取 channel_id + game_id + 生效期               ← 分成配置
 *   payment_split_config    → 预取 publisher_id + game_id + 生效期
 *
 *   raw_transactions 已于 2026-06 废止（DROP TABLE，删模型）。
 *   导入时直接聚合写入 raw_settlements，结算查询从此表读取。
 */

// ═══════════════════════════════════════════════════════════
// 实体定义 — id+name 绑定为不可分割的一组
// ═══════════════════════════════════════════════════════════

/**
 * 每个实体描述一个业务对象，自动展开为 id(hidden) + name(visible) 两列。
 *
 * @typedef {{
 *   idField: string,        // API JSON key → 标识符列（hidden）
 *   nameField: string,      // API JSON key → 展示名列（visible）
 *   label: string,          // 中文标签
 *   sourceTable: string,    // 数据库主表
 *   directions: ('income'|'payment')[],
 *   [direction: string]: {  // 按方向配置展示属性
 *     headerName: string,   // 列头名称
 *     pinned?: 'left',
 *     width?: number,
 *     idWidth?: number,     // id 列宽（默认 0=hidden）
 *     idEditable?: boolean, // id 列是否可编辑
 *   }
 * }} EntityDef
 */

/** @type {Record<string, EntityDef>} */
export const ENTITY = {
  channel: {
    idField: 'channel_id',
    nameField: 'channel_name',
    label: '渠道',
    sourceTable: '原始流水表 → channel_categories',
    directions: ['income'],
    income: { headerName: '收入方名称', pinned: 'left', width: 130 },
  },
  publisher: {
    idField: 'publisher_id',
    nameField: 'publisher_name',
    label: '研发商',
    sourceTable: 'publishers',
    directions: ['payment'],
    payment: { headerName: '付款方名称', pinned: 'left', width: 160 },
  },
  game: {
    idField: 'game_id',
    nameField: 'game_name',
    label: '游戏',
    sourceTable: 'games',
    directions: ['income', 'payment'],
    income:  { headerName: '游戏名称', pinned: 'left', width: 140, idWidth: 100, idEditable: true },
    payment: { headerName: '游戏名称', pinned: 'left', width: 140, idWidth: 100, idEditable: true },
  },
}

// ═══════════════════════════════════════════════════════════
// 字段定义 — 不包含实体 id/name（由实体展开自动生成）
// ═══════════════════════════════════════════════════════════

/**
 * @typedef {'identity'|'amount'|'rate'} FieldKind
 *
 * @typedef {{
 *   field: string,              // API JSON key
 *   headerName: string,         // 列头中文
 *   kind: FieldKind,
 *   direction: 'income'|'payment'|'both',
 *   sourceTable: string,        // 数据库来源表
 *   sourceLine?: string,        // settlement_service.py 关键行号
 *   width?: number,
 *   editable?: boolean,
 *   detail?: boolean,           // "显示明细列" toggle
 *   lockable?: boolean,         // 支持锁定/解锁（cell-locked 样式）
 *   formatter?: 'money',
 *   negativeStyle?: boolean,
 *   note?: string,
 * }} FieldDef
 */

/** @type {FieldDef[]} */
export const FIELD_DEFS = [
  // ── 维度列（子查询，行 40-61）──
  // 来源：company_game_mapping → companies (scalar subquery)
  { field: 'company_name', headerName: '我方公司', kind: 'identity', direction: 'both',
    sourceTable: 'companies', sourceLine: '54-61', width: 140 },
  // 来源：publisher_game_mapping (scalar subquery, LIMIT 1)
  { field: 'project_code', headerName: '项目编号', kind: 'identity', direction: 'both',
    sourceTable: 'publisher_game_mapping', sourceLine: '41-46', width: 120 },
  { field: 'project_name', headerName: '项目名称', kind: 'identity', direction: 'both',
    sourceTable: 'publisher_game_mapping', sourceLine: '47-52', width: 150 },
  // 来源：原始流水表.month (导入时已聚合)
  { field: 'month',        headerName: '月份',     kind: 'identity', direction: 'both',
    sourceTable: '原始流水表', width: 90 },

  // ── 金额列（原始流水表直接读取）──
  { field: 'raw_revenue',       headerName: '原始流水', kind: 'amount', direction: 'both',
    sourceTable: '原始流水表', width: 130, formatter: 'money' },
  { field: 'real_revenue',      headerName: '真实流水', kind: 'amount', direction: 'both',
    sourceTable: '实时计算(raw_revenue * discount_rate)', width: 130, editable: true, lockable: true, formatter: 'money' },
  { field: 'total_deductions',  headerName: '扣除合计', kind: 'amount', direction: 'both',
    sourceTable: 'deductions.SUM(vouchers+test+welfare+bad_debt)', width: 110, formatter: 'money', negativeStyle: true },
  { field: 'settlement_amount', headerName: '结算金额', kind: 'amount', direction: 'both',
    sourceTable: '实时计算(公式)', width: 130, editable: true, lockable: true, formatter: 'money' },

  // ── 扣除明细列（Deduction 表 batch prefetch）──
  { field: 'vouchers',  headerName: '代金券', kind: 'amount', direction: 'both',
    sourceTable: 'deductions', width: 100, editable: true, detail: true, formatter: 'money',
    note: 'payment 方向只读（跨渠道汇总）' },
  { field: 'test',      headerName: '测试',   kind: 'amount', direction: 'both',
    sourceTable: 'deductions', width: 90,  editable: true, detail: true, formatter: 'money' },
  { field: 'welfare',   headerName: '福利币', kind: 'amount', direction: 'both',
    sourceTable: 'deductions', width: 90,  editable: true, detail: true, formatter: 'money' },
  { field: 'bad_debt',  headerName: '坏账',   kind: 'amount', direction: 'both',
    sourceTable: 'deductions', width: 90,  editable: true, detail: true, formatter: 'money' },

  // ── 比率列（income_split_config / payment_split_config 预取生效期匹配）──
  { field: 'split_rate',       headerName: '分成比例', kind: 'rate', direction: 'both',
    sourceTable: 'income/payment_split_config', width: 100, editable: true, detail: true },
  { field: 'channel_fee_rate', headerName: '通道费率', kind: 'rate', direction: 'both',
    sourceTable: 'income/payment_split_config', width: 100, editable: true, detail: true },
  { field: 'tax_rate',         headerName: '税率',     kind: 'rate', direction: 'both',
    sourceTable: 'income/payment_split_config', width: 90,  editable: true, detail: true },

  // ── Payment 独有 ──
  { field: 'fixed_fee', headerName: '固定费用', kind: 'amount', direction: 'payment',
    sourceTable: 'payment_split_config', width: 110, editable: true, formatter: 'money' },

  // ── 锁定列（ChannelLock / PublisherLock 预取，单表权威）──
  // ⚠️ 数据流：查询时 batch prefetch 锁定表，锁定值是最终权威，不依赖任何缓存
  { field: 'locked_real_revenue',      headerName: '锁定真实流水', kind: 'amount', direction: 'both',
    sourceTable: 'channel_locks / publisher_locks', formatter: 'money',
    note: '锁定表是唯一权威源' },
  { field: 'locked_settlement_amount', headerName: '锁定结算金额', kind: 'amount', direction: 'both',
    sourceTable: 'channel_locks / publisher_locks', formatter: 'money',
    note: '锁定表是唯一权威源' },

  // ── Payment 分成配置生效区间（行 387-388）──
  { field: 'effective_from', headerName: '生效起始', kind: 'identity', direction: 'payment',
    sourceTable: 'payment_split_config', sourceLine: '387' },
  { field: 'effective_to',   headerName: '生效结束', kind: 'identity', direction: 'payment',
    sourceTable: 'payment_split_config', sourceLine: '388' },
]

// ═══════════════════════════════════════════════════════════
// 派生查询
// ═══════════════════════════════════════════════════════════

/** 指定方向适用的实体列表 */
export function entitiesFor(direction) {
  return Object.entries(ENTITY)
    .filter(([_, e]) => e.directions.includes(direction))
    .map(([key, e]) => ({ key, ...e }))
}

/** 指定方向适用的字段列表 */
export function fieldsFor(direction) {
  return FIELD_DEFS.filter(f => f.direction === direction || f.direction === 'both')
}

/** "显示明细列" toggle 控制的字段名 */
export const DETAIL_FIELDS = FIELD_DEFS
  .filter(f => f.detail)
  .map(f => f.field)

/** 锁定相关字段（real_revenue + settlement_amount） */
export const LOCKABLE_FIELDS = FIELD_DEFS
  .filter(f => f.lockable)
  .map(f => f.field)

/** Deduction 编辑可触发的字段 */
export const DEDUCTION_FIELDS = ['vouchers', 'test', 'welfare', 'bad_debt']

/** 分成配置编辑可触发的字段 */
export const SPLIT_CONFIG_FIELDS = ['split_rate', 'channel_fee_rate', 'tax_rate']

// ═══════════════════════════════════════════════════════════
// AG Grid columnDefs 生成器
// ═══════════════════════════════════════════════════════════

const FMT_MONEY = p => p.value != null ? Number(p.value).toLocaleString('zh-CN') : '-'
const FMT_PCT   = p => p.value != null ? (Number(p.value) * 100).toFixed(2) + '%' : '-'
const PARSE_MONEY = p => {
  if (!p.newValue || !String(p.newValue).trim()) return null
  const n = parseFloat(String(p.newValue).replace(/,/g, ''))
  return isNaN(n) ? null : n
}
const PARSE_PCT = p => { const v = parseFloat(p.newValue); return isNaN(v) ? 0 : v / 100 }

const ROW_NO_STYLE = { color: 'var(--text-light)', backgroundColor: 'var(--palette-gray-50)', textAlign: 'center' }
const ALIGN_RIGHT  = { textAlign: 'right' }
const LOCKED_CLASS = 'cell-locked'

function _moneyCol(col, editable) {
  col.valueFormatter = FMT_MONEY
  col.cellStyle = ALIGN_RIGHT
  if (editable) col.valueParser = PARSE_MONEY
  return col
}

function _rateCol(col, editable) {
  col.valueFormatter = FMT_PCT
  col.cellStyle = ALIGN_RIGHT
  if (editable) col.valueParser = PARSE_PCT
  return col
}

/**
 * 根据方向 + 选项生成 AG Grid columnDefs
 * @param {'income'|'payment'} direction
 * @param {Object} [opts]
 * @param {boolean} [opts.showDetail=true]
 * @param {boolean} [opts.paymentEditDeductions=false]
 * @param {boolean} [opts.showLockedCols=false]  是否暴露 locked_* 为可见列
 * @param {boolean} [opts.showEffectiveCols=false] 是否暴露 effective_* 为可见列
 * @returns {Array<Object>}
 */
export function buildSettlementColumns(direction, opts = {}) {
  const { showDetail = true, paymentEditDeductions = false,
          showLockedCols = false, showEffectiveCols = false } = opts

  const cols = []

  // 行号
  cols.push({
    field: 'rowNo', headerName: '#', width: 50, pinned: 'left',
    sortable: false, filter: false,
    valueFormatter: p => (p.node?.rowIndex ?? 0) + 1,
    cellStyle: ROW_NO_STYLE,
  })

  // ── 实体展开：id (hidden) + name (visible) ──
  for (const ent of entitiesFor(direction)) {
    const cfg = ent[direction]
    if (!cfg) continue

    // id 列
    const idCol = {
      field: ent.idField,
      headerName: ent.idField,
      width: cfg.idWidth || undefined,
      hide: !cfg.idWidth,   // idWidth 未设置 → 隐藏
      pinned: cfg.pinned,
      editable: cfg.idEditable || false,
    }
    cols.push(idCol)

    // name 列
    const nameCol = {
      field: ent.nameField,
      headerName: cfg.headerName,
      width: cfg.width || 140,
      pinned: cfg.pinned,
      editable: false,
    }
    cols.push(nameCol)
  }

  // ── 字段列 ──
  for (const f of fieldsFor(direction)) {
    const col = {
      field: f.field,
      headerName: f.headerName,
      width: f.width || 100,
      editable: f.editable || false,
    }

    // Payment 方向 deduction 列默认只读
    if (direction === 'payment' && DEDUCTION_FIELDS.includes(f.field)) {
      if (!paymentEditDeductions) col.editable = false
    }

    // 明细列 toggle
    if (f.detail && !showDetail) {
      col.hide = true
    }

    // locked_* 默认隐藏
    if (f.field.startsWith('locked_') && !showLockedCols) {
      col.hide = true
    }

    // effective_* 默认隐藏
    if (f.field.startsWith('effective_') && !showEffectiveCols) {
      col.hide = true
    }

    // 格式化
    if (f.formatter === 'money') {
      _moneyCol(col, col.editable)
    } else if (f.kind === 'rate') {
      _rateCol(col, col.editable)
    }

    // 锁定样式
    if (f.lockable) {
      col.cellClassRules = {
        [LOCKED_CLASS]: p => p.data && p.data['locked_' + f.field] != null,
      }
    }

    // 扣除合计红色
    if (f.negativeStyle) {
      col.cellStyle = p => ({ textAlign: 'right', color: p.value > 0 ? '#c00' : '#999' })
    }

    // 结算金额绿色加粗
    if (f.field === 'settlement_amount') {
      col.cellStyle = p => p.value > 0
        ? { fontWeight: 700, color: '#27ae60', textAlign: 'right' }
        : { textAlign: 'right' }
    }

    cols.push(col)
  }

  // ── 计算列：分成总比 ──
  cols.push({
    headerName: '分成总比',
    width: 100,
    editable: false,
    valueGetter: p => {
      const d = p.data; if (!d) return 0
      return (Number(d.split_rate || 0)) * (1 - Number(d.channel_fee_rate || 0)) * (1 - Number(d.tax_rate || 0))
    },
    valueFormatter: FMT_PCT,
    cellStyle: ALIGN_RIGHT,
  })

  return cols
}

// ═══════════════════════════════════════════════════════════
// CSV 导出列映射
// ═══════════════════════════════════════════════════════════

function _csvCols(direction) {
  const cols = []
  // 实体 name
  for (const ent of entitiesFor(direction)) {
    const cfg = ent[direction]
    if (cfg) cols.push({ field: ent.nameField, label: cfg.headerName })
  }
  // 字段（排除 hidden 类 + entity id字段）
  const hiddenFields = new Set([
    ...Object.values(ENTITY).map(e => e.idField),
    'locked_real_revenue', 'locked_settlement_amount',
    'effective_from', 'effective_to',
  ])
  for (const f of fieldsFor(direction)) {
    if (!hiddenFields.has(f.field)) {
      const fmt = f.kind === 'rate' ? 'pct' : f.formatter === 'money' ? 'num' : null
      cols.push({ field: f.field, label: f.headerName, fmt })
    }
  }
  return cols
}

export const INCOME_CSV_COLS  = _csvCols('income')
export const PAYMENT_CSV_COLS = _csvCols('payment')
