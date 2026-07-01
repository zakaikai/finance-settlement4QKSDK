import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/ag-grid')) return 'ag-grid'
          if (id.includes('node_modules/echarts')) return 'echarts'
          if (id.includes('node_modules')) return 'vendor'
        },
      },
    },
  },
  server: {
    port: Number(process.env.VITE_PORT) || 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'https://localhost:8770',
        changeOrigin: true,
      },
    },
  },
})
