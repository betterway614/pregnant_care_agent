/* 全局状态管理 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserRole, DashboardStats, Pregnant } from '@/types'
import { dashboardApi } from '@/api/endpoints'

export const useAppStore = defineStore('app', () => {
  const currentRole = ref<UserRole>('nurse')
  const sidebarCollapsed = ref(false)
  const stats = ref<DashboardStats>({
    total_pregnant: 0, pending_alerts: 0, today_followups: 0,
    pending_reviews: 0, high_risk_count: 0, weekly_new_pregnant: 0,
  })
  // ===== 认证相关状态 =====
  const currentPregnantId = ref(localStorage.getItem('currentPregnantId') || '')
  const currentPregnant = ref<Pregnant | null>(null)
  const isLoggedIn = ref(!!localStorage.getItem('isLoggedIn'))

  const roleName = computed(() => ({
    nurse: '助孕师小护',
    doctor: 'Dr.智',
    pregnant: '小安',
    admin: '管理员',
  }[currentRole.value] || '未知'))

  const roleIcon = computed(() => ({
    nurse: 'UserFilled',
    doctor: 'FirstAidKit',
    pregnant: 'ChatDotSquare',
    admin: 'Setting',
  }[currentRole.value] || 'User'))

  async function fetchStats() {
    try {
      const res = await dashboardApi.stats()
      stats.value = res.data
    } catch { /* 忽略错误 */ }
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setRole(role: UserRole) {
    currentRole.value = role
  }

  // ===== 认证相关方法 =====

  /** 设置当前孕妇 */
  function setPregnant(pregnantId: string) {
    currentPregnantId.value = pregnantId
    localStorage.setItem('currentPregnantId', pregnantId)
  }

  /** 登录 */
  function login(role: UserRole, pregnantId?: string) {
    currentRole.value = role
    isLoggedIn.value = true
    localStorage.setItem('isLoggedIn', 'true')
    localStorage.setItem('currentRole', role)
    if (pregnantId) {
      setPregnant(pregnantId)
    }
  }

  /** 登出 */
  function logout() {
    isLoggedIn.value = false
    currentPregnantId.value = ''
    currentPregnant.value = null
    localStorage.removeItem('isLoggedIn')
    localStorage.removeItem('currentPregnantId')
    localStorage.removeItem('currentRole')
    localStorage.removeItem('token')
  }

  return {
    // 原有
    currentRole, sidebarCollapsed, stats,
    roleName, roleIcon,
    fetchStats, toggleSidebar, setRole,
    // 新增认证相关
    currentPregnantId, currentPregnant, isLoggedIn,
    setPregnant, login, logout,
  }
})
