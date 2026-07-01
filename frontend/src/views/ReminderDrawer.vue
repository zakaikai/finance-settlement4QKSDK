<template>
  <div>
    <div v-if="visible" class="drawer-backdrop" @click="$emit('close')"></div>
    <div :class="['reminder-drawer', { open: visible }]">
      <div class="drawer-header">
        <h3>提醒列表</h3>
        <button class="btn-close" @click="$emit('close')">&#10005;</button>
      </div>

      <div class="drawer-quick-add">
        <input
          v-model="quickTitle"
          class="quick-input"
          placeholder="快速添加提醒..."
          @keyup.enter="quickAdd"
        />
        <select v-model="quickCycle" class="quick-cycle">
          <option value="none">无周期</option>
          <option value="daily">每天</option>
          <option value="weekly">每周</option>
          <option value="monthly">每月</option>
          <option value="yearly">每年</option>
        </select>
        <AppButton variant="primary" size="sm" @click="quickAdd" :disabled="!quickTitle.trim()">添加</AppButton>
      </div>

      <div class="drawer-body">
        <template v-if="grouped.length">
          <div v-for="group in grouped" :key="group.key" class="reminder-group">
            <div class="group-label">{{ group.label }} <span class="group-count">{{ group.items.length }}</span></div>
            <div
              v-for="item in group.items"
              :key="item.id"
              class="reminder-item"
              @click="$emit('select-memo', item)"
            >
              <span class="reminder-title">{{ item.title }}</span>
              <span class="reminder-party" v-if="item.party_name">{{ item.party_name }}</span>
            </div>
          </div>
        </template>
        <div v-else class="drawer-empty">暂无提醒，在备忘录中标记提醒即可在此查看</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import api from '../api'
import { useToast } from '../components/AppToast/useToast'

const props = defineProps({
  visible: Boolean,
  memos: Array,
})

const emit = defineEmits(['close', 'select-memo', 'refresh'])

const quickTitle = ref('')
const quickCycle = ref('none')

const CYCLE_LABELS = { daily: '每天', weekly: '每周', monthly: '每月', yearly: '每年', none: '无周期' }
const GROUP_ORDER = ['daily', 'weekly', 'monthly', 'yearly', 'none']

const grouped = computed(() => {
  const reminders = props.memos.filter(m => m.is_reminder)
  const map = {}
  for (const m of reminders) {
    const cycle = m.reminder_cycle || 'none'
    if (!map[cycle]) map[cycle] = []
    map[cycle].push(m)
  }
  return GROUP_ORDER
    .filter(key => map[key] && map[key].length)
    .map(key => ({ key, label: CYCLE_LABELS[key] || key, items: map[key] }))
})

async function quickAdd() {
  const title = quickTitle.value.trim()
  if (!title) return
  try {
    const fd = new FormData()
const toast = useToast()
    fd.append('title', title)
    fd.append('is_reminder', 'true')
    fd.append('reminder_cycle', quickCycle.value)
    await api.createMemo(fd)
    quickTitle.value = ''
    quickCycle.value = 'none'
    emit('refresh')
  } catch (e) {
    toast.error('添加失败: ' + (e.response?.data?.detail || e.message))
  }
}
</script>

<style scoped>
.drawer-backdrop {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.2); z-index: 999;
}
.reminder-drawer {
  position: fixed; top: 0; right: 0; bottom: 0;
  width: 380px; max-width: 90vw;
  background: var(--bg-card); box-shadow: -4px 0 24px rgba(0,0,0,0.12);
  z-index: 1000;
  display: flex; flex-direction: column;
  transform: translateX(100%);
  transition: transform 0.25s ease;
}
.reminder-drawer.open { transform: translateX(0); }

.drawer-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--border-cell); flex-shrink: 0;
}
.drawer-header h3 { font-size: 16px; }
.btn-close {
  width: 28px; height: 28px; border: none; background: var(--border-cell);
  border-radius: 50%; cursor: pointer; font-size: 14px; color: var(--text-muted);
  display: flex; align-items: center; justify-content: center;
}
.btn-close:hover { background: var(--border-header-cell); }

.drawer-quick-add {
  display: flex; gap: 6px; padding: 12px 16px;
  border-bottom: 1px solid var(--border-cell); flex-shrink: 0;
}
.quick-input {
  flex: 1; padding: 6px 10px; border: 1px solid var(--border-default);
  border-radius: 4px; font-size: 13px; outline: none;
}
.quick-input:focus { border-color: var(--color-primary); }
.quick-cycle {
  width: 80px; padding: 6px 4px; border: 1px solid var(--border-default);
  border-radius: 4px; font-size: 12px; outline: none; flex-shrink: 0;
}
.btn-quick-add {
  padding: 6px 12px; background: var(--color-primary); color: var(--bg-card);
  border: none; border-radius: 4px; font-size: 12px; cursor: pointer; flex-shrink: 0;
}
.btn-quick-add:disabled { background: var(--text-light); cursor: not-allowed; }

.drawer-body { flex: 1; overflow-y: auto; padding: 12px 16px; }

.reminder-group { margin-bottom: 16px; }
.group-label {
  font-size: 12px; color: var(--text-muted); font-weight: 600;
  margin-bottom: 6px; display: flex; align-items: center; gap: 6px;
}
.group-count { color: var(--text-light); font-weight: 400; }

.reminder-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; border-radius: 6px; cursor: pointer;
  transition: background 0.1s; margin-bottom: 2px;
}
.reminder-item:hover { background: var(--bg-tag-blue); }
.reminder-title { font-size: 13px; color: var(--text-primary); }
.reminder-party {
  font-size: 11px; color: var(--text-light); background: var(--border-cell);
  padding: 1px 6px; border-radius: 3px; flex-shrink: 0;
}

.drawer-empty {
  text-align: center; color: var(--text-light); font-size: 13px;
  padding: 48px 24px;
}
</style>
