<template>
  <div class="dashboard">
    <div class="section-head">
      <span>数据看板</span>
      <button class="btn-add" @click="$emit('add-block')">+ 添加排行块</button>
    </div>
    <div class="rank-grid">
      <RankingBlock
        v-for="(block, i) in blocks"
        :key="i"
        :block="block"
        :loading="block.loading"
        :monthLabel="monthLabel"
        :availableMonths="availableMonths"
        @remove="$emit('remove-block', i)"
        @update:dimension="(v) => $emit('update-block', i, 'dimension', v)"
        @update:metric="(v) => $emit('update-block', i, 'metric', v)"
        @update:month="(v) => $emit('update:month', i, v)"
      />
    </div>
  </div>
</template>

<script setup>
import RankingBlock from './RankingBlock.vue'

defineProps({
  blocks: { type: Array, required: true },
  monthLabel: { type: String, required: true },
  availableMonths: { type: Array, default: () => [] },
})

defineEmits(['add-block', 'remove-block', 'update-block', 'update:month'])
</script>

<style scoped>
.dashboard { margin-top: 4px; }
.section-head {
  display: flex; align-items: center; gap: 12px;
  font-size: 15px; font-weight: 600; margin-bottom: 14px;
}
.btn-add {
  padding: 4px 14px; font-size: 12px; border: 1px solid var(--color-primary);
  border-radius: 6px; background: var(--bg-card); color: var(--color-primary); cursor: pointer;
}
.btn-add:hover { background: var(--color-primary); color: var(--text-on-primary); }
.rank-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px; margin-bottom: 16px;
}
@media (max-width: 1200px) { .rank-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 768px)  { .rank-grid { grid-template-columns: 1fr; } }
</style>
