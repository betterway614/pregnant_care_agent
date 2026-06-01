/* API 客户端 */
import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// ── 请求/响应日志（仅在开发环境打印） ──
const DEBUG = import.meta.env.DEV || location.hostname === 'localhost'

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
    return res
  },
  (err) => {
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
    const msg = err.response?.data?.detail || err.message || '请求失败'
    console.error('API Error:', msg)
    return Promise.reject(err)
  }
)

export default client
