import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({ plugins: [vue()], server: { port: 5180, proxy: { '/api': process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:6480' } }, test: { environment: 'node' } })
