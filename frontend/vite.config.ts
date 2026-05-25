import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import fs from 'fs'

// 自签名证书路径（用于局域网开发环境，支持 getUserMedia 等安全上下文 API）
const certDir = path.resolve(import.meta.dirname, '.cert')
const keyPath = path.join(certDir, 'key.pem')
const certPath = path.join(certDir, 'cert.pem')

const httpsConfig = fs.existsSync(keyPath)
  ? {
      key: fs.readFileSync(keyPath),
      cert: fs.readFileSync(certPath),
    }
  : undefined

export default defineConfig({
  plugins: [
    vue(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    https: httpsConfig,
    proxy: {
      '/api': {
        target: 'http://localhost:9999',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://localhost:9999',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
