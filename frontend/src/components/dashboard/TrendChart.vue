<template>
  <div ref="chartRef" class="trend-chart"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, required: true },
})

const chartRef = ref(null)
let chartInstance = null

function render() {
  if (!chartRef.value || !props.data.length) return
  if (!chartInstance) chartInstance = echarts.init(chartRef.value)

  const months = props.data.map(d => d.month)
  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['真实流水', '结算金额'], bottom: 0 },
    grid: { left: 60, right: 20, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: months, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', axisLabel: { fontSize: 11, formatter: v => (v / 10000).toFixed(0) + '万' } },
    series: [
      { name: '真实流水', type: 'line', data: props.data.map(d => d.real_revenue), smooth: true, lineStyle: { width: 2 }, itemStyle: { color: '#5470c6' } },
      { name: '结算金额', type: 'line', data: props.data.map(d => d.settlement_amount), smooth: true, lineStyle: { width: 2 }, itemStyle: { color: '#91cc75' } },
    ],
  })
}

function onResize() {
  chartInstance?.resize()
}

watch(() => props.data, () => render(), { deep: true })

onMounted(() => {
  window.addEventListener('resize', onResize)
  render()
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
})
</script>

<style scoped>
.trend-chart { width: 100%; height: 320px; }
</style>
