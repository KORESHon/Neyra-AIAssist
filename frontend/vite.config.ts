import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: API runs separately (python main.py --mode api). Proxy /v1 and OpenAPI to it.
const apiTarget = process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8787'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/v1': { target: apiTarget, changeOrigin: true },
      '/openapi.json': { target: apiTarget, changeOrigin: true },
      '/docs': { target: apiTarget, changeOrigin: true },
      '/redoc': { target: apiTarget, changeOrigin: true },
    },
  },
})
