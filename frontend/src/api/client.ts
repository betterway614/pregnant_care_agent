/* API 客户端 */
import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// ── 请求/响应日志（仅在开发环境打印） ──
const DEBUG = import.meta.env.DEV || location.hostname === 'localhost'

// ── 后端连接状态缓存 ──
let backendReachable: boolean | null = null
let lastHealthCheck = 0
const HEALTH_CHECK_INTERVAL = 30_000 // 30秒检查一次

/**
 * 检查后端是否可达（带缓存，避免频繁请求）
 * 返回 true/false，不抛异常
 */
export async function checkBackendHealth(): Promise<boolean> {
  const now = Date.now()
  if (backendReachable !== null && now - lastHealthCheck < HEALTH_CHECK_INTERVAL) {
    return backendReachable
  }
  try {
    // 用原生 fetch 绕过 axios 拦截器，避免 401 等干扰
    const resp = await fetch('/health', { method: 'GET', signal: AbortSignal.timeout(5000) })
    backendReachable = resp.ok
  } catch {
    backendReachable = false
  }
  lastHealthCheck = now
  return backendReachable
}

/**
 * 获取当前页面访问地址（用于诊断网络问题）
 */
export function getAccessInfo() {
  const host = location.hostname
  const isLoopback = host === 'localhost' || host === '127.0.0.1'
  return {
    host,
    port: location.port,
    protocol: location.protocol,
    isLoopback,
    isLAN: !isLoopback && /^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)/.test(host),
    url: location.origin,
  }
}

// ── 请求拦截：自动附加 JWT token ──
client.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    if (DEBUG) {
      console.groupCollapsed(`[HTTP] → ${config.method?.toUpperCase()} ${config.url}`)
      if (config.data) console.log('请求体:', config.data)
      console.groupEnd()
    }
    return config
  },
  (err) => Promise.reject(err),
)

// ── 响应拦截：401 时清除 token 并跳转登录页 ──
client.interceptors.response.use(
  (res) => {
    if (DEBUG) {
      console.groupCollapsed(`[HTTP] ← ${res.status} ${res.config.url}`)
      console.log('响应体:', res.data)
      console.groupEnd()
    }
    // 请求成功，标记后端可达
    backendReachable = true
    return res
  },
  async (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('isLoggedIn')
      localStorage.removeItem('currentRole')
      localStorage.removeItem('currentPregnantId')
      // 跳转登录页（避免在登录页本身循环跳转）
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }

    // ── 网络错误诊断 ──
    if (!err.response) {
      // 网络层错误（后端不可达 / proxy 失效 / IP 变化）
      backendReachable = false
      const info = getAccessInfo()
      const hint = info.isLoopback
        ? '后端服务未启动或端口不匹配，请检查后端是否在运行'
        : `通过局域网 IP (${info.host}) 访问，请确认：
1. 后端服务已启动且监听 0.0.0.0
2. vite proxy 目标地址正确（当前: ${location.origin} → proxy → localhost:9999）
3. 防火墙未拦截端口 9999`
      console.error(`[API] 网络错误: ${err.message}\n${hint}`)
      err._diagnostic = hint
    } else {
      const msg = err.response?.data?.detail || err.message || '请求失败'
      console.error('API Error:', msg)
    }
    return Promise.reject(err)
  }
)

export default client
