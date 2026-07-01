import { ref, watch } from 'vue'

const STORAGE_KEY = 'dashboard_prefs'

const DEFAULTS = {
  rankingBlocks: [
    { dimension: 'channel', metric: 'settlement_amount' },
    { dimension: 'game', metric: 'real_revenue' },
    { dimension: 'publisher', metric: 'settlement_amount' },
  ],
  trend: {
    type: '',
    name: '',
    sub: '',
  },
}

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore corrupt data */ }
  return JSON.parse(JSON.stringify(DEFAULTS))
}

export function useDashboardPrefs() {
  const prefs = ref(load())

  let timer = null
  function save() {
    clearTimeout(timer)
    timer = setTimeout(() => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs.value))
    }, 300)
  }

  watch(prefs, save, { deep: true })

  function resetToDefaults() {
    prefs.value = JSON.parse(JSON.stringify(DEFAULTS))
  }

  function addRankingBlock(dimension, metric) {
    prefs.value.rankingBlocks.push({ dimension: dimension || 'channel', metric: metric || 'settlement_amount' })
  }

  function removeRankingBlock(index) {
    prefs.value.rankingBlocks.splice(index, 1)
  }

  function updateRankingBlock(index, changes) {
    Object.assign(prefs.value.rankingBlocks[index], changes)
  }

  function updateTrend(changes) {
    Object.assign(prefs.value.trend, changes)
  }

  return { prefs, save, resetToDefaults, addRankingBlock, removeRankingBlock, updateRankingBlock, updateTrend }
}
