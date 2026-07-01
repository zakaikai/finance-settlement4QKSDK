<template>
  <div class="search-select-editor">
    <input
      ref="searchInput"
      v-model="inputText"
      class="ss-input"
      placeholder="输入搜索..."
      autocomplete="off"
      @input="onInput"
      @keydown.down.prevent="highlight('down')"
      @keydown.up.prevent="highlight('up')"
      @keydown.enter.prevent="selectHighlighted"
      @keydown.escape.prevent="cancel"
      @blur="onBlur"
    />
    <ul v-if="showDropdown && filtered.length" class="ss-dropdown">
      <li
        v-for="(item, i) in filtered"
        :key="item"
        :class="{ highlighted: i === highlightIdx }"
        @mousedown="select(item)"
      >
        {{ item }}
      </li>
    </ul>
    <div v-if="showDropdown && inputText && !filtered.length" class="ss-no-match">无匹配</div>
  </div>
</template>

<script>
import { ref, computed, nextTick } from 'vue'

export default {
  name: 'SearchSelectCellEditor',
  methods: {
    getValue() {
      return this.finalValue
    },
    isPopup() {
      return true
    },
    afterGuiAttached() {
      nextTick(() => {
        if (this.searchInput) {
          this.searchInput.focus()
          this.searchInput.select()
        }
      })
    },
  },
  setup(props) {
    const params = props.params || {}
    const values = params.values || []
    const initialValue = params.value || ''
    const inputText = ref(initialValue)
    const finalValue = ref(initialValue)
    const highlightIdx = ref(-1)
    const showDropdown = ref(false)
    const searchInput = ref(null)

    const filtered = computed(() => {
      const q = inputText.value.toLowerCase().trim()
      if (!q) return values
      return values.filter(v => v.toLowerCase().includes(q))
    })

    function onInput() {
      showDropdown.value = true
      highlightIdx.value = -1
    }

    let blurTimer = null
    function onBlur() {
      clearTimeout(blurTimer)
      blurTimer = setTimeout(() => { showDropdown.value = false }, 200)
    }

    function select(item) {
      finalValue.value = item
      inputText.value = item
      showDropdown.value = false
      if (params.stopEditing) params.stopEditing()
    }

    function selectHighlighted() {
      if (highlightIdx.value >= 0 && highlightIdx.value < filtered.value.length) {
        select(filtered.value[highlightIdx.value])
      }
    }

    function highlight(dir) {
      const max = filtered.value.length - 1
      if (max < 0) return
      highlightIdx.value = dir === 'down'
        ? (highlightIdx.value < max ? highlightIdx.value + 1 : 0)
        : (highlightIdx.value > 0 ? highlightIdx.value - 1 : max)
    }

    function cancel() {
      finalValue.value = initialValue
      inputText.value = initialValue
      showDropdown.value = false
      if (params.stopEditing) params.stopEditing()
    }

    return {
      inputText, finalValue, highlightIdx, showDropdown,
      filtered, searchInput,
      onInput, onBlur, select, selectHighlighted, highlight, cancel,
    }
  },
}
</script>

<style scoped>
.search-select-editor {
  position: relative;
  width: 100%;
  font-size: var(--text-base);
}

.ss-input {
  width: 100%;
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-family: inherit;
  color: var(--text-primary);
  background: var(--bg-card);
  outline: none;
  box-sizing: border-box;
  transition: border-color var(--transition-fast);
}

.ss-input:focus {
  border-color: var(--border-input-focus);
  background: var(--bg-input-focus);
}

.ss-input::placeholder {
  color: var(--text-light);
}

.ss-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  z-index: 1000;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-elevated);
  max-height: 200px;
  overflow-y: auto;
  list-style: none;
  margin: var(--space-xs) 0 0 0;
  padding: var(--space-xs) 0;
}

.ss-dropdown li {
  padding: var(--space-sm) var(--space-md);
  cursor: pointer;
  color: var(--text-primary);
  font-size: var(--text-base);
  transition: background var(--transition-fast);
}

.ss-dropdown li:hover {
  background: var(--bg-row-alt);
}

.ss-dropdown li.highlighted {
  background: var(--bg-input-focus);
  color: var(--color-primary);
  font-weight: var(--weight-medium);
}

.ss-no-match {
  padding: var(--space-md);
  color: var(--text-light);
  font-size: var(--text-sm);
  font-style: italic;
}
</style>
