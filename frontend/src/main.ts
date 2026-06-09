/* 应用入口 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import { checkBackendHealth, getAccessInfo } from './api/client'
import './echarts' // 注册 ECharts 渲染器和组件
import './styles/global.css'
import './styles/patient-theme.css'
import './styles/markdown.css'

const app = createApp(App)

// 注册所有Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, {
  locale: zhCn,
})
app.mount('#app')

// ── 启动时检查后端连接 ──
checkBackendHealth().then((ok) => {
  if (!ok) {
    const info = getAccessInfo()
    console.warn(
      `%c[AI-Care] 后端不可达%c\n` +
      `访问地址: ${info.url}\n` +
      `本机回环: ${info.isLoopback ? '是' : '否 (局域网 IP)'}\n` +
      `可能原因:\n` +
      `  1. 后端服务未启动 (端口 9999)\n` +
      `  2. vite proxy 目标地址不匹配\n` +
      `     → 设置环境变量: VITE_API_TARGET=http://<后端IP>:9999\n` +
      `  3. 防火墙拦截了端口\n` +
      `  4. IP 地址已变化 (DHCP 重分配)`,
      'color: #E6A23C; font-weight: bold',
      'color: inherit'
    )
  }
})
