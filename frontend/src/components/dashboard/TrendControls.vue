<template>
  <div class="block-controls">
    <label>类型</label>
    <select :value="trendType" @change="$emit('update:trendType', $event.target.value)">
      <option value="">全渠道汇总</option>
      <option value="channel">渠道</option>
      <option value="publisher">研发商</option>
    </select>
    <label>名称</label>
    <select :value="trendName" @change="$emit('update:trendName', $event.target.value)" :disabled="!trendType">
      <option value="">请选择</option>
      <option v-for="n in trendNames" :key="n" :value="n">{{ n }}</option>
    </select>
    <label>子项</label>
    <select :value="trendSub" @change="$emit('update:trendSub', $event.target.value)" :disabled="!trendSubOptions.length">
      <option value="">全部</option>
      <option v-for="o in trendSubOptions" :key="o" :value="o">{{ o }}</option>
    </select>
  </div>
</template>

<script setup>
defineProps({
  trendType: { type: String, default: '' },
  trendName: { type: String, default: '' },
  trendSub: { type: String, default: '' },
  trendNames: { type: Array, default: () => [] },
  trendSubOptions: { type: Array, default: () => [] },
})

defineEmits(['update:trendType', 'update:trendName', 'update:trendSub'])
</script>

<style scoped>
.block-controls { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.block-controls label { font-size: 12px; color: #666; }
.block-controls select {
  padding: 3px 8px; border: 1px solid var(--border-default); border-radius: 4px;
  font-size: 13px; margin-right: 12px;
}
</style>
