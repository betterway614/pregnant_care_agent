/* Vue Router 配置 */
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

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
  },
  // 护士端
  {
    path: '/nurse',
    component: () => import('@/components/layout/NurseLayout.vue'),
    children: [
      { path: 'dashboard', name: 'NurseDashboard', component: () => import('@/views/nurse/NurseDashboard.vue'), meta: { title: '工作台' } },
      { path: 'followup', name: 'FollowUpList', component: () => import('@/views/nurse/FollowUpList.vue'), meta: { title: '随访管理' } },
      { path: 'schedule', name: 'ScheduleManage', component: () => import('@/views/nurse/ScheduleManage.vue'), meta: { title: '排期管理' } },
      { path: 'alerts', name: 'AlertList', component: () => import('@/views/nurse/AlertList.vue'), meta: { title: '预警管理' } },
    ],
  },
  // 医生端
  {
    path: '/doctor',
    component: () => import('@/components/layout/DoctorLayout.vue'),
    children: [
      { path: 'dashboard', name: 'DoctorDashboard', component: () => import('@/views/doctor/DoctorDashboard.vue'), meta: { title: '工作台' } },
      { path: 'fgr-board', name: 'FGRBoard', component: () => import('@/views/doctor/FGRBoard.vue'), meta: { title: 'FGR看板' } },
      { path: 'review/:alertId?', name: 'ReviewWorkbench', component: () => import('@/views/doctor/ReviewWorkbench.vue'), meta: { title: '审核工作台' } },
      { path: 'orders', name: 'OrderManage', component: () => import('@/views/doctor/OrderManage.vue'), meta: { title: '医嘱管理' } },
    ],
  },
  // 孕妇端
  {
    path: '/pregnant',
    component: () => import('@/components/layout/PregnantLayout.vue'),
    redirect: '/pregnant/home',
    children: [
      { path: 'home', name: 'PregnantHome', component: () => import('@/views/pregnant/PregnantHome.vue'), meta: { title: '孕期首页' } },
      { path: 'chat', name: 'PregnantChat', component: () => import('@/views/pregnant/PregnantChat.vue'), meta: { title: '百科知识' } },
      { path: 'schedule', name: 'PregnantSchedule', component: () => import('@/views/pregnant/PregnantSchedule.vue'), meta: { title: '推荐' } },
      { path: 'tools', name: 'PregnantTools', component: () => import('@/views/pregnant/PregnantTools.vue'), meta: { title: '工具' } },
      { path: 'profile', name: 'PregnantProfile', component: () => import('@/views/pregnant/PregnantProfile.vue'), meta: { title: '我的' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/* ============ 路由导航守卫（轻量） ============ */
router.beforeEach((to, _from, next) => {
  // /login 始终放行
  if (to.path === '/login') {
    next()
    return
  }

  // 开发模式：未登录时不强制跳转，各页面自行处理未登录状态
  const isLoggedIn = localStorage.getItem('isLoggedIn')
  if (!isLoggedIn) {
    // 仅 /pregnant/profile 需要登录（页面内会显示登录表单）
    // 其他页面允许直接浏览（dev friendly）
    next()
    return
  }

  // 已登录用户：角色不匹配时给出提示但不拦截
  const currentRole = localStorage.getItem('currentRole')
  if (to.path.startsWith('/pregnant') && currentRole !== 'pregnant') {
    next()
    return
  }
  if (to.path.startsWith('/nurse') && currentRole !== 'nurse') {
    next()
    return
  }
  if (to.path.startsWith('/doctor') && currentRole !== 'doctor') {
    next()
    return
  }

  next()
})

export default router
