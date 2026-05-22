import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/** 与 restart.sh 的 NOVEL_LOCAL_BACKEND_PORT 默认一致；勿指向 8000 上无关进程 */
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:9000'

/** 将 node_modules 拆成稳定 vendor chunk，便于缓存与并行加载 */
function manualChunks(id: string): string | undefined {
  if (!id.includes('node_modules')) return undefined
  if (
    id.includes('react-dom') ||
    id.includes('/react/') ||
    id.includes('react-router') ||
    id.includes('scheduler/')
  ) {
    return 'vendor-react'
  }
  // TipTap 仅随 ChapterEditor 懒加载，不单独拆 vendor chunk（避免被挂到入口预加载）
  if (id.includes('three') || id.includes('react-force-graph')) return 'vendor-graph-3d'
  if (id.includes('reactflow') || id.includes('@reactflow')) return 'vendor-reactflow'
  if (id.includes('lucide-react')) return 'vendor-icons'
  if (id.includes('react-query')) return 'vendor-react-query'
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
    port: 3173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        /** 传入 X-Forwarded-Host，配合后端 ForwardedHostASGIMiddleware，避免 307 Location 指向直连后端地址 */
        xfwd: true,
        ws: true,
        /** 复盘 / 门控写作等长耗时 LLM 请求，避免 dev 代理默认过早断开 */
        timeout: 600_000,
        proxyTimeout: 600_000,
      },
    },
  },
})
