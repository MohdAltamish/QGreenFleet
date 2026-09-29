import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The QGreenFleet FastAPI backend (uvicorn src.api.main:app) is proxied so the
// browser sees a single origin and no CORS preflight in development.
const API_TARGET = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'

// The captured API snapshot is only used by the static demo build
// (VITE_STATIC_SNAPSHOT=1). The live app aliases it to an empty stub so the
// 1.3 MB of baked data never reaches a bundle that talks to a real backend.
const IS_STATIC = process.env.VITE_STATIC_SNAPSHOT === '1'
const snapshotModule = fileURLToPath(
  new URL(IS_STATIC ? './src/api/snapshot.json' : './src/api/snapshot.empty.json', import.meta.url),
)

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { 'qgf-snapshot': snapshotModule },
  },
  // The single-file demo cannot fetch sibling assets, so its fonts are inlined.
  build: IS_STATIC ? { assetsInlineLimit: Number.MAX_SAFE_INTEGER } : undefined,
  server: {
    port: 5173,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
})
