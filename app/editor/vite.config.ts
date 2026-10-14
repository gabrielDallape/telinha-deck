import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// O build vai direto para a pasta que o nucleo serve (telinha/api.py).
// `npm run dev` usa o nucleo rodando como API (porta 47800).
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../telinha/web', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:47800' } },
})
