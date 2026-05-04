import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        /** 传入 X-Forwarded-Host，配合后端 ForwardedHostASGIMiddleware，避免 307 Location 指向直连后端地址 */
        xfwd: true,
        ws: true,
      },
    },
  },
})
