import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

function manualChunks(id: string): string | undefined {
  if (!id.includes('node_modules')) return undefined
  // antd / rc-* / dayjs 打在同一 chunk，避免与 react 互相引用形成 circular chunk
  if (
    id.includes('antd') ||
    id.includes('@ant-design') ||
    id.includes('/rc-') ||
    id.includes('dayjs')
  ) {
    return 'vendor-antd'
  }
  if (
    id.includes('react-dom') ||
    id.includes('/react/') ||
    id.includes('react-router') ||
    id.includes('scheduler/')
  ) {
    return 'vendor-react'
  }
  return undefined
}

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: { manualChunks },
    },
  },
  server: {
    port: 3174,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
