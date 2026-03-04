import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/admin/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/admin': { target: 'http://localhost:8000', changeOrigin: true },
      '/dev': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
