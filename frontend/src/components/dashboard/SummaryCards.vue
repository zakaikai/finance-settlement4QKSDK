<template>
  <div class="summary-cards">
    <div class="stat-card">
      <div class="stat-label">{{ monthLabel }}流水</div>
      <div class="stat-value">{{ formatNum(summary.total_real_revenue) }}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">结算金额</div>
      <div class="stat-value">{{ formatNum(summary.total_settlement_amount) }}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">数据规模</div>
      <div class="stat-value">
        <span class="stat-tag">渠道 {{ summary.channel_count ?? '-' }}</span>
        <span class="stat-tag">游戏 {{ summary.game_count ?? '-' }}</span>
        <span class="stat-tag">研发 {{ summary.publisher_count ?? '-' }}</span>
      </div>
    </div>
    <div class="stat-card">
      <div class="stat-label">结算环比</div>
      <div class="stat-value" :class="growthClass(summary.mom_growth)">
        {{ summary.mom_growth != null ? formatPct(summary.mom_growth) : '-' }}
      </div>
    </div>
    <div class="stat-card profit-card">
      <div class="stat-label">营业毛利</div>
      <div class="stat-value profit-value">{{ formatNum(profitSummary.gross_profit) }}</div>
    </div>
    <div class="stat-card profit-card">
      <div class="stat-label">营业利润</div>
      <div class="stat-value profit-value" :class="profitClass(profitSummary.net_profit)">
        {{ formatNum(profitSummary.net_profit) }}
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  summary: { type: Object, required: true },
  monthLabel: { type: String, required: true },
  profitSummary: { type: Object, default: () => ({}) },
})

function formatNum(v) {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}
function formatPct(v) {
  return (v > 0 ? '+' : '') + v.toFixed(2) + '%'
}
function growthClass(v) {
  if (v == null) return ''
  return v > 0 ? 'up' : v < 0 ? 'down' : ''
}
function profitClass(v) {
  if (v == null) return ''
  return v > 0 ? 'up' : v < 0 ? 'down' : ''
}
</script>

<style scoped>
.summary-cards {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 16px;
  margin-bottom: 28px;
}
.stat-card {
  background: var(--bg-card);
  border-radius: 8px;
  padding: 20px 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.stat-label {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 8px;
}
.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-primary);
}
.stat-tag {
  display: inline-block;
  font-size: 12px;
  font-weight: 400;
  background: var(--bg-page);
  color: var(--text-secondary);
  padding: 2px 8px;
  border-radius: 4px;
  margin-right: 6px;
  margin-top: 2px;
}
.stat-value.up { color: var(--color-danger); }
.stat-value.down { color: var(--color-success); }

@media (max-width: 900px) {
  .summary-cards { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 500px) {
  .summary-cards { grid-template-columns: 1fr; }
}
</style>
