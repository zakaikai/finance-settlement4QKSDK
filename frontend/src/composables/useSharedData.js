import { ref, computed } from 'vue'
import api from '../api/index.js'

/** Module-level cache — shared across all views that use these composables. */

const _games = ref([])
const _gamesLoaded = ref(false)
let _gamesPromise = null

export function useGames() {
  const gamesMap = computed(() => {
    const map = {}
    _games.value.forEach(g => { map[g.game_id] = g.game_name })
    return map
  })

  async function load() {
    if (_gamesLoaded.value) return
    if (_gamesPromise) {
      await _gamesPromise
      return
    }
    _gamesPromise = (async () => {
      const r = await api.getGames()
      _games.value = r.data.data.map(g => ({ ...g, discount_rate: Number(g.discount_rate) }))
      _gamesLoaded.value = true
      _gamesPromise = null
    })()
    await _gamesPromise
  }

  return { games: _games, gamesMap, load }
}
