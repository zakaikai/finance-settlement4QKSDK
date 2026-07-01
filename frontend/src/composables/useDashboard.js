/**
 * Dashboard module — isolated state, API, and logic.
 *
 * Home.vue stays thin: only template + wiring to this composable.
 * All API calls, data transforms, and ranking-block management live here.
 * Safe to refactor internally without touching Home.vue.
 */

import { ref, reactive, computed } from 'vue'
import api, { logError } from '../api'
import { useDashboardPrefs } from './useDashboardPrefs'

// ── Dimension / metric labels ──
export const DIM_LABEL = { channel: '渠道', game: '游戏', project: '项目', publisher: '研发' }
export const METRIC_LABEL = { real_revenue: '真实流水', settlement_amount: '结算金额' }

// ── Month helpers ──
function monthLabel(ym) {
  if (!ym) return ''
  return parseInt(ym.split('-')[1], 10) + '月'
}
function prevMonthLabel(ym) {
  if (!ym) return ''
  const [y, m] = ym.split('-').map(Number)
  const d = new Date(y, m - 2, 1)
  return (d.getMonth() + 1) + '月'
}

export function useDashboard() {
  const { prefs, addRankingBlock: saveBlock, removeRankingBlock: saveRemoveBlock, updateRankingBlock: saveUpdateBlock, updateTrend } = useDashboardPrefs()

  // ── Summary + profit ──
  const summary = ref({})
  const profitSummary = ref({})
  const currentMonth = computed(() => summary.value.current_month || '')
  const monthLabelComputed = computed(() => monthLabel(currentMonth.value))
  const prevMonthLabelComputed = computed(() => prevMonthLabel(currentMonth.value))

  // ── Ranking blocks ──
  const rankingBlocks = reactive([])
  const availableMonths = ref([])

  async function fetchRanking(i) {
    const block = rankingBlocks[i]
    if (!block) return
    block.loading = true
    try {
      const params = { dimension: block.dimension, metric: block.metric, count: 20 }
      if (block.month) params.month = block.month
      const r = await api.getDashboardRanking(params)
      block.rows = r.data.data.rows || []
    } catch (e) { block.rows = []; logError('fetchRanking', e) }
    block.loading = false
  }

  function addBlock() {
    const dim = 'channel'; const met = 'settlement_amount'
    const defaultMonth = availableMonths.value[0] || null
    rankingBlocks.push({ dimension: dim, metric: met, month: defaultMonth, rows: [], loading: false })
    saveBlock(dim, met)
    fetchRanking(rankingBlocks.length - 1)
  }

  function removeBlock(i) {
    rankingBlocks.splice(i, 1)
    saveRemoveBlock(i)
  }

  function updateBlock(i, field, value) {
    rankingBlocks[i][field] = value
    saveUpdateBlock(i, { [field]: value })
    fetchRanking(i)
  }

  function updateBlockMonth(i, month) {
    rankingBlocks[i].month = month
    fetchRanking(i)
  }

  // ── Trend ──
  const trendType = ref('')
  const trendName = ref('')
  const trendNames = ref([])
  const trendSub = ref('')
  const trendSubOptions = ref([])
  const isDefaultTrend = ref(true)
  const chartData = ref([])
  let _trendSummaryCache = null

  function loadDefaultTrend() {
    isDefaultTrend.value = true
    if (_trendSummaryCache) { chartData.value = _trendSummaryCache; return }
    api.getDashboardTrendSummary().then(r => {
      _trendSummaryCache = r.data.data
      chartData.value = _trendSummaryCache
    }).catch(e => logError('loadDefaultTrend', e))
  }

  async function onTrendTypeChange(val) {
    trendType.value = val; trendName.value = ''; trendNames.value = []; trendSub.value = ''; trendSubOptions.value = []
    isDefaultTrend.value = false
    updateTrend({ type: val, name: '', sub: '' })
    if (!val) { loadDefaultTrend(); return }
    try { const r = await api.getDashboardLevel1Options({ level1_type: val }); trendNames.value = r.data.data } catch (e) { logError('onTrendTypeChange', e) }
    chartData.value = []
  }

  async function onTrendNameChange(val) {
    trendName.value = val; trendSub.value = ''; trendSubOptions.value = []
    updateTrend({ name: val, sub: '' })
    if (!val) { chartData.value = []; return }
    try { const r = await api.getDashboardLevel2({ level1_type: trendType.value, level1_value: val }); trendSubOptions.value = r.data.data } catch (e) { logError('onTrendNameChange', e) }
    fetchTrend()
  }

  async function onTrendSubChange(val) {
    trendSub.value = val; updateTrend({ sub: val }); fetchTrend()
  }

  async function fetchTrend() {
    isDefaultTrend.value = false
    if (!trendType.value || !trendName.value) return
    try {
      const r = await api.getDashboardTrend({ level1_type: trendType.value, level1_value: trendName.value, level2_value: trendSub.value || undefined })
      chartData.value = r.data.data
    } catch (e) { chartData.value = []; logError('fetchTrend', e) }
  }

  // ── Init ──
  async function init() {
    const saved = prefs.value
    try {
      const [initR, monthsR] = await Promise.all([
        api.getDashboardInit(),
        api.getAvailableMonths(),
      ])
      const d = initR.data.data
      availableMonths.value = monthsR.data.months || []
      const latestMonth = availableMonths.value[0] || null

      summary.value = d.summary
      profitSummary.value = d.profit_summary || {}
      _trendSummaryCache = d.trend_summary
      chartData.value = d.trend_summary

      const blockConfigs = saved.rankingBlocks.length ? saved.rankingBlocks : [
        { dimension: 'channel', metric: 'settlement_amount' },
        { dimension: 'game', metric: 'real_revenue' },
        { dimension: 'publisher', metric: 'settlement_amount' },
      ]
      blockConfigs.forEach((cfg, i) => {
        const match = d.rankings.find(r => r.dimension === cfg.dimension && r.metric === cfg.metric)
        rankingBlocks.push({
          dimension: cfg.dimension, metric: cfg.metric,
          month: latestMonth,
          rows: match ? match.rows : [],
          loading: false,
        })
        if (!match) fetchRanking(i)
      })
    } catch (e) { logError('loadInit', e) }

    if (saved.trend.type) {
      trendType.value = saved.trend.type; isDefaultTrend.value = false
      try { const r1 = await api.getDashboardLevel1Options({ level1_type: saved.trend.type }); trendNames.value = r1.data.data } catch (e) { /* ignore */ }
      if (saved.trend.name) {
        trendName.value = saved.trend.name
        try { const r2 = await api.getDashboardLevel2({ level1_type: saved.trend.type, level1_value: saved.trend.name }); trendSubOptions.value = r2.data.data } catch (e) { /* ignore */ }
        if (saved.trend.sub) { trendSub.value = saved.trend.sub }
        fetchTrend()
      }
    }
  }

  return {
    // Summary
    summary, profitSummary, monthLabelComputed, prevMonthLabelComputed,
    // Ranking
    rankingBlocks, availableMonths, addBlock, removeBlock, updateBlock, updateBlockMonth, fetchRanking,
    // Trend
    trendType, trendName, trendNames, trendSub, trendSubOptions, isDefaultTrend, chartData,
    onTrendTypeChange, onTrendNameChange, onTrendSubChange, loadDefaultTrend,
    // Init
    init,
  }
}
