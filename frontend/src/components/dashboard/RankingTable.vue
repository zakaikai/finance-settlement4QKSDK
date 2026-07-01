<template>
  <table class="rank-table">
    <thead>
      <tr><th class="col-rank">#</th><th>名称</th><th class="col-val">{{ monthLabel }}</th></tr>
    </thead>
    <tbody>
      <tr v-for="(r, ri) in rows" :key="ri">
        <td class="col-rank">{{ ri + 1 }}</td>
        <td class="col-name">{{ r.name }}</td>
        <td class="col-val num">
          <span class="val">{{ formatNum(r.current_value) }}</span>
          <span v-if="r.growth_rate != null" :class="['growth', growthDir(r.growth_rate)]">
            {{ growthArrow(r.growth_rate) }}{{ formatPct(Math.abs(r.growth_rate)) }}
          </span>
          <span v-else class="growth growth-zero">-</span>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<script setup>
defineProps({
  rows: { type: Array, required: true },
  monthLabel: { type: String, required: true },
})

function formatNum(v) {
  if (v == null) return '-'
  return '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}
function formatPct(v) {
  return v.toFixed(2) + '%'
}
function growthDir(v) {
  if (v == null) return 'zero'
  return v > 0 ? 'up' : v < 0 ? 'down' : 'zero'
}
function growthArrow(v) {
  if (v == null) return ''
  return v > 0 ? '↑' : v < 0 ? '↓' : '→'
}
</script>

<style scoped>
.rank-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.rank-table th {
  text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border-light);
  font-weight: 600; font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;
}
.rank-table td { padding: 5px 8px; border-bottom: 1px solid var(--bg-page); }
.rank-table tbody tr:hover td { background: var(--palette-gray-50); }
.col-rank { width: 28px; text-align: center !important; color: var(--text-muted); font-size: 12px; }
.col-val { text-align: right !important; white-space: nowrap; }
.num { font-variant-numeric: tabular-nums; }
.val { font-weight: 500; }
.growth { margin-left: 8px; font-size: 12px; font-weight: 600; }
.growth.up { color: var(--color-danger); }
.growth.down { color: var(--color-success); }
.growth.zero { color: var(--text-muted); }
</style>
