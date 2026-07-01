<template>
  <div class="rank-card">
    <div class="card-head">
      <span class="card-title">{{ DIM_LABEL[block.dimension] || block.dimension }}排名</span>
      <div class="card-controls">
        <select class="ctl-select ctl-month" :value="block.month || ''" @change="$emit('update:month', $event.target.value)">
          <option v-for="m in availableMonths" :key="m" :value="m">{{ m }}</option>
        </select>
        <select class="ctl-select" :value="block.dimension" @change="$emit('update:dimension', $event.target.value)">
          <option v-for="(label, key) in DIM_LABEL" :key="key" :value="key">{{ label }}</option>
        </select>
        <select class="ctl-select" :value="block.metric" @change="$emit('update:metric', $event.target.value)">
          <option v-for="(label, key) in METRIC_LABEL" :key="key" :value="key">{{ label }}</option>
        </select>
        <button class="btn-close" @click="$emit('remove')" title="移除">&times;</button>
      </div>
    </div>
    <div class="card-body">
      <div v-if="loading" class="loading-spin">加载中...</div>
      <RankingTable v-else :rows="block.rows" :monthLabel="blockMonthLabel" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import RankingTable from './RankingTable.vue'
import { DIM_LABEL, METRIC_LABEL } from '../../composables/useDashboard'

const props = defineProps({
  block: { type: Object, required: true },
  loading: { type: Boolean, default: false },
  monthLabel: { type: String, required: true },
  availableMonths: { type: Array, default: () => [] },
})

defineEmits(['remove', 'update:dimension', 'update:metric', 'update:month'])

const blockMonthLabel = computed(() => {
  const m = props.block.month
  if (!m) return ''
  return parseInt(m.split('-')[1], 10) + '月'
})
</script>

<style scoped>
.rank-card {
  background: var(--bg-card); border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06); overflow: hidden;
  display: flex; flex-direction: column;
}
.card-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; border-bottom: 1px solid var(--bg-page);
}
.card-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
.card-controls { display: flex; align-items: center; gap: 6px; }
.ctl-select {
  padding: 2px 6px; font-size: 12px; border: 1px solid var(--border-default);
  border-radius: 4px; background: var(--bg-card); color: var(--text-primary);
  cursor: pointer;
}
.btn-close {
  width: 20px; height: 20px; border: none; border-radius: 4px;
  background: transparent; cursor: pointer; font-size: 14px; line-height: 1;
  color: var(--text-muted); opacity: 0; transition: opacity 0.15s;
  display: flex; align-items: center; justify-content: center; margin-left: 2px;
}
.rank-card:hover .btn-close { opacity: 1; }
.btn-close:hover { background: var(--color-danger); color: var(--text-on-primary); }
.card-body { flex: 1; padding: 4px 0; min-height: 0; }
.loading-spin { padding: 24px; text-align: center; color: var(--text-muted); font-size: 12px; }
</style>
