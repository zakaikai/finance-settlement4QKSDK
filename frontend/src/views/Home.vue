<template>
  <div class="home">
    <SummaryCards :summary="summary" :monthLabel="monthLabelComputed" :profitSummary="profitSummary" />
    <RankingGrid
      :blocks="rankingBlocks"
      :monthLabel="monthLabelComputed"
      :availableMonths="availableMonths"
      @add-block="addBlock"
      @remove-block="removeBlock"
      @update-block="updateBlock"
      @update:month="updateBlockMonth"
    />
    <TrendSection
      :isDefault="isDefaultTrend"
      :trendType="trendType"
      :trendName="trendName"
      :trendSub="trendSub"
      :trendNames="trendNames"
      :trendSubOptions="trendSubOptions"
      :chartData="chartData"
      @update:trendType="onTrendTypeChange"
      @update:trendName="onTrendNameChange"
      @update:trendSub="onTrendSubChange"
    />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import SummaryCards from '../components/dashboard/SummaryCards.vue'
import RankingGrid from '../components/dashboard/RankingGrid.vue'
import TrendSection from '../components/dashboard/TrendSection.vue'
import { useDashboard } from '../composables/useDashboard'

const {
  summary, profitSummary, monthLabelComputed, prevMonthLabelComputed,
  rankingBlocks, availableMonths, addBlock, removeBlock, updateBlock, updateBlockMonth,
  trendType, trendName, trendNames, trendSub, trendSubOptions, isDefaultTrend, chartData,
  onTrendTypeChange, onTrendNameChange, onTrendSubChange,
  init,
} = useDashboard()

onMounted(init)
</script>
