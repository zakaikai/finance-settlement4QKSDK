<template>
  <div class="trend-block">
    <div class="block-header">
      <span>近6月趋势</span>
      <span v-if="isDefault" class="default-badge">汇总</span>
    </div>
    <TrendControls
      :trendType="trendType"
      :trendName="trendName"
      :trendSub="trendSub"
      :trendNames="trendNames"
      :trendSubOptions="trendSubOptions"
      @update:trendType="$emit('update:trendType', $event)"
      @update:trendName="$emit('update:trendName', $event)"
      @update:trendSub="$emit('update:trendSub', $event)"
    />
    <TrendChart :data="chartData" />
  </div>
</template>

<script setup>
import TrendControls from './TrendControls.vue'
import TrendChart from './TrendChart.vue'

defineProps({
  isDefault: { type: Boolean, default: true },
  trendType: { type: String, default: '' },
  trendName: { type: String, default: '' },
  trendSub: { type: String, default: '' },
  trendNames: { type: Array, default: () => [] },
  trendSubOptions: { type: Array, default: () => [] },
  chartData: { type: Array, required: true },
})

defineEmits(['update:trendType', 'update:trendName', 'update:trendSub'])
</script>

<style scoped>
.trend-block {
  background: var(--bg-card); border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 16px; margin-bottom: 16px;
}
.block-header {
  display: flex; align-items: center; justify-content: space-between;
  font-weight: 600; font-size: 14px; margin-bottom: 12px;
}
.default-badge { font-size: 11px; background: #e3f2fd; color: #1565c0; padding: 2px 8px; border-radius: 10px; font-weight: 400; }
</style>
