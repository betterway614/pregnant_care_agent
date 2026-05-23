/* Vue Router 配置 */
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { ElMessage } from 'element-plus'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    requiresAuth?: boolean
    role?: 'nurse' | 'doctor' | 'pregnant' | 'admin'
    hideTabBar?: boolean
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/login',
  },
  // 角色选择
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false },
  },
  // 护士端
  {
    path: '/nurse',
    component: () => import('@/components/layout/NurseLayout.vue'),
    meta: { requiresAuth: true, role: 'nurse' },
    children: [
      { path: 'dashboard', name: 'NurseDashboard', component: () => import('@/views/nurse/NurseDashboard.vue'), meta: { title: '工作台' } },
      { path: 'followup', name: 'FollowUpList', component: () => import('@/views/nurse/FollowUpList.vue'), meta: { title: '随访管理' } },
      { path: 'schedule', name: 'ScheduleManage', component: () => import('@/views/nurse/ScheduleManage.vue'), meta: { title: '排期管理' } },
      { path: 'alerts', name: 'AlertList', component: () => import('@/views/nurse/AlertList.vue'), meta: { title: '预警管理' } },
      { path: 'pregnant/:pregnantId', name: 'NursePregnantDetail', component: () => import('@/views/nurse/PregnantDetail.vue'), meta: { title: '孕妇详情' } },
      { path: 'print/followup/:id', name: 'FollowUpPrint', component: () => import('@/views/nurse/FollowUpPrintPage.vue'), meta: { title: '随访记录打印', hideTabBar: true } },
    ],
  },
  // 医生端
  {
    path: '/doctor',
    component: () => import('@/components/layout/DoctorLayout.vue'),
    meta: { requiresAuth: true, role: 'doctor' },
    children: [
      { path: 'dashboard', name: 'DoctorDashboard', component: () => import('@/views/doctor/DoctorDashboard.vue'), meta: { title: '工作台' } },
      { path: 'fgr-board', name: 'FGRBoard', component: () => import('@/views/doctor/FGRBoard.vue'), meta: { title: 'FGR看板' } },
      { path: 'review/:alertId?', name: 'ReviewWorkbench', component: () => import('@/views/doctor/ReviewWorkbench.vue'), meta: { title: '审核工作台' } },
      { path: 'orders', name: 'OrderManage', component: () => import('@/views/doctor/OrderManage.vue'), meta: { title: '医嘱管理' } },
      { path: 'pregnant/:pregnantId', name: 'DoctorPregnantDetail', component: () => import('@/views/doctor/PregnantDetail.vue'), meta: { title: '孕妇详情' } },
      { path: 'orders/:orderId/sign', name: 'OrderSign', component: () => import('@/views/doctor/OrderSignPage.vue'), meta: { title: '医嘱签署', hideTabBar: true } },
    ],
  },
  // 孕妇端
  {
    path: '/pregnant',
    component: () => import('@/components/layout/PregnantLayout.vue'),
    redirect: '/pregnant/home',
    meta: { requiresAuth: true, role: 'pregnant' },
    children: [
      { path: 'home', name: 'PregnantHome', component: () => import('@/views/pregnant/PregnantHome.vue'), meta: { title: '孕期首页' } },
      { path: 'chat', name: 'PregnantChat', component: () => import('@/views/pregnant/PregnantChat.vue'), meta: { title: '百科知识' } },
      { path: 'schedule', name: 'PregnantSchedule', component: () => import('@/views/pregnant/PregnantSchedule.vue'), meta: { title: '推荐' } },
      {
        path: 'tools',
        component: () => import('@/views/pregnant/PregnantTools.vue'),
        children: [
          { path: '', name: 'ToolGrid', component: () => import('@/views/pregnant/tools/ToolGrid.vue'), meta: { title: '健康工具' } },
          { path: 'fetal-movement', name: 'FetalMovement', component: () => import('@/views/pregnant/tools/FetalMovement.vue'), meta: { title: '胎动计数', hideTabBar: true } },
          { path: 'health-record', name: 'HealthRecord', component: () => import('@/views/pregnant/tools/HealthRecord.vue'), meta: { title: '快速录入', hideTabBar: true } },
          { path: 'health-trend', name: 'HealthTrend', component: () => import('@/views/pregnant/tools/HealthTrend.vue'), meta: { title: '健康趋势', hideTabBar: true } },
          { path: 'mental-health', name: 'MentalHealth', component: () => import('@/views/pregnant/tools/MentalHealth.vue'), meta: { title: '心理筛查', hideTabBar: true } },
          { path: 'followup/:recordId', name: 'FollowUpForm', component: () => import('@/views/pregnant/tools/FollowUpForm.vue'), meta: { title: '随访', hideTabBar: true } },
        ],
      },
      { path: 'profile', name: 'PregnantProfile', component: () => import('@/views/pregnant/PregnantProfile.vue'), meta: { title: '我的' } },
      { path: 'orders/:orderId', name: 'OrderDetail', component: () => import('@/views/pregnant/OrderDetail.vue'), meta: { title: '医嘱详情', hideTabBar: true } },
    ],
  },
  // 管理员端
  {
    path: '/admin',
    component: () => import('@/components/layout/AdminLayout.vue'),
    redirect: '/admin/dashboard',
    meta: { requiresAuth: true, role: 'admin' },
    children: [
      { path: 'dashboard', name: 'AdminDashboard', component: () => import('@/views/admin/Dashboard.vue'), meta: { title: '仪表盘' } },
      { path: 'token-analysis', name: 'AdminTokenAnalysis', component: () => import('@/views/admin/TokenAnalysis.vue'), meta: { title: 'Token 消耗分析' } },
      { path: 'audit-trail', name: 'AdminAuditTrail', component: () => import('@/views/admin/AuditTrail.vue'), meta: { title: '对话审计追溯' } },
      { path: 'route-monitor', name: 'AdminRouteMonitor', component: () => import('@/views/admin/RouteMonitor.vue'), meta: { title: '路由监控' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/* ============ 路由导航守卫 ============ */

/** 从 matched 记录中获取第一个显式定义的角色要求（沿继承链向上查找） */
function getRequiredRole(to: { matched: any[] }): string | undefined {
  for (let i = to.matched.length - 1; i >= 0; i--) {
    if (to.matched[i].meta.role) return to.matched[i].meta.role
  }
  return undefined
}

/** 从 matched 记录中判断是否需要认证（默认 true） */
function isRequiresAuth(to: { matched: any[] }): boolean {
  for (let i = to.matched.length - 1; i >= 0; i--) {
    if (to.matched[i].meta.requiresAuth === false) return false
  }
  return true
}

router.beforeEach((to, _from, next) => {
  // 1) 公开页面直接放行
  if (!isRequiresAuth(to)) {
    next()
    return
  }

  // 2) 未登录 → 跳转登录页，并记录原目标路径以便登录后回跳
  const isLoggedIn = localStorage.getItem('isLoggedIn')
  if (!isLoggedIn) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  // 3) 已登录 → 角色匹配检查
  const currentRole = localStorage.getItem('currentRole')
  const requiredRole = getRequiredRole(to)
  if (requiredRole && currentRole !== requiredRole) {
    ElMessage.warning('无权访问该页面')
    const dashboardMap: Record<string, string> = {
      nurse: '/nurse/dashboard',
      doctor: '/doctor/dashboard',
      pregnant: '/pregnant/home',
      admin: '/admin/dashboard',
    }
    next(dashboardMap[currentRole || ''] || '/login')
    return
  }

  // 4) 全部通过
  next()
})

export default router
