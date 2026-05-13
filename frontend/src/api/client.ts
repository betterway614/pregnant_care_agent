/* API 客户端 */
import axios from 'axios'

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// ── 请求/响应日志（仅在开发环境打印） ──
const DEBUG = import.meta.env.DEV || location.hostname === 'localhost'

client.interceptors.request.use(
  (config) => {
    if (DEBUG) {
      console.groupCollapsed(`[HTTP] → ${config.method?.toUpperCase()} ${config.url}`)
      if (config.data) console.log('请求体:', config.data)
      console.groupEnd()
    }
    return config
  },
  (err) => Promise.reject(err),
)

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
    const msg = err.response?.data?.detail || err.message || '请求失败'
    console.error('API Error:', msg)
    return Promise.reject(err)
  }
)

export default client
