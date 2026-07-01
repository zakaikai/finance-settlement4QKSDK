import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../api'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue') },
  { path: '/', name: 'Home', component: () => import('../views/Home.vue'), meta: { requiresAuth: true } },
  { path: '/basic-data', name: 'BasicData', component: () => import('../views/BasicData.vue'), meta: { requiresAuth: true } },
  { path: '/import', name: 'Import', component: () => import('../views/DataImport.vue'), meta: { requiresAuth: true } },
  { path: '/settlement', name: 'Settlement', component: () => import('../views/Settlement.vue'), meta: { requiresAuth: true } },
  { path: '/arap', name: 'ARAP', component: () => import('../views/ARAP.vue'), meta: { requiresAuth: true } },
  { path: '/profit', name: 'Profit', component: () => import('../views/Profit.vue'), meta: { requiresAuth: true } },
  { path: '/system', name: 'System', component: () => import('../views/System.vue'), meta: { requiresAuth: true } },
  { path: '/memos', name: 'Memos', component: () => import('../views/Memo.vue'), meta: { requiresAuth: true } },
  { path: '/ocr', name: 'OcrImport', component: () => import('../views/OcrImport.vue'), meta: { requiresAuth: true } },
  { path: '/flex-import', name: 'FlexImport', component: () => import('../views/FlexImport.vue'), meta: { requiresAuth: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Navigation guard: check auth token
router.beforeEach(async (to, from, next) => {
  if (to.path === '/login') return next()

  if (to.meta?.requiresAuth) {
    // Check if password is set and token exists
    try {
      const r = await fetch('/api/auth/status')
      const data = await r.json()
      if (!data.password_set || !getToken()) {
        return next('/login')
      }
    } catch {
      // Backend not reachable, allow navigation
    }
  }
  next()
})

export default router
