<template>
  <div class="combobox" :class="{ open: dropdownOpen }">
    <input
      v-model="search"
      class="combobox-input"
      :placeholder="placeholder"
      @focus="dropdownOpen = true"
      @blur="delayClose"
      @input="dropdownOpen = true"
    />
    <span v-if="search && modelValue == null" class="combobox-clear" @mousedown.prevent="clear">×</span>
    <ul v-if="dropdownOpen" class="combobox-list">
      <li v-for="ch in filtered" :key="ch.channel_id"
        :class="{ active: modelValue === ch.channel_id }"
        @mousedown.prevent="select(ch)">{{ ch.channel_name }}</li>
      <li v-if="filtered.length === 0" class="no-match">无匹配渠道</li>
    </ul>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const props = defineProps({
  modelValue: { type: Number, default: null },
  placeholder: { type: String, default: '输入渠道名称搜索…' },
})
const emit = defineEmits(['update:modelValue'])

const search = ref('')
const dropdownOpen = ref(false)
const channels = ref([])

const filtered = computed(() => {
  if (!search.value) return channels.value
  const q = search.value.toLowerCase()
  return channels.value.filter(c => c.channel_name.toLowerCase().includes(q))
})

function select(ch) {
  emit('update:modelValue', ch.channel_id)
  search.value = ch.channel_name
  dropdownOpen.value = false
}

function clear() {
  emit('update:modelValue', null)
  search.value = ''
}

function delayClose() {
  setTimeout(() => { dropdownOpen.value = false }, 200)
}

onMounted(async () => {
  try {
    const r = await api.getSettlementChannels()
    channels.value = r.data.data || []
  } catch { /* ignore */ }
})
</script>

<style scoped>
.combobox { position: relative; }
.combobox-input {
  width: 100%; padding: 8px 10px; border: 1px solid var(--border-default); border-radius: 6px; font-size: 14px;
}
.combobox-input:focus { border-color: var(--color-info); outline: none; }
.combobox-clear { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); cursor: pointer; color: var(--text-light); }
.combobox-list {
  position: absolute; top: 100%; left: 0; right: 0; max-height: 200px; overflow-y: auto;
  background: var(--bg-card); border: 1px solid var(--border-default); border-radius: 6px; z-index: 10;
  list-style: none; padding: 4px 0; margin: 4px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.combobox-list li { padding: 8px 12px; cursor: pointer; font-size: 14px; }
.combobox-list li:hover, .combobox-list li.active { background: var(--bg-tag-blue); color: var(--color-primary); }
.no-match { color: var(--text-light); font-style: italic; }
</style>
