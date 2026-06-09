import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'path';
import fs from 'fs';
// 自签名证书路径（用于局域网开发环境，支持 getUserMedia 等安全上下文 API）
var certDir = path.resolve(import.meta.dirname, '.cert');
var keyPath = path.join(certDir, 'key.pem');
var certPath = path.join(certDir, 'cert.pem');
var httpsConfig = fs.existsSync(keyPath)
    ? {
        key: fs.readFileSync(keyPath),
        cert: fs.readFileSync(certPath),
    }
    : undefined;
// ── 后端代理目标：支持环境变量覆盖，适配 SSH 远程开发 / 局域网访问 ──
// 用法：
//   VITE_API_TARGET=http://10.67.8.145:9999 npm run dev
//   VITE_API_TARGET=http://192.168.1.100:8000 npm run dev
// 不设置时默认 http://localhost:9999
var apiTarget = process.env.VITE_API_TARGET || 'http://localhost:9999';
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
                target: apiTarget,
                changeOrigin: true,
            },
            '/ws': {
                target: apiTarget,
                ws: true,
                changeOrigin: true,
            },
        },
    },
});
