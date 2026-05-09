<template>
  <div class="patient-profile">
    <div class="page-container profile-container">
      <!-- ===== 未登录状态 ===== -->
      <template v-if="!isLoggedIn">
        <div class="profile-header">
          <h1 class="page-title">登录账号</h1>
          <p class="page-subtitle">请输入您的医院ID卡号和密码</p>
        </div>

        <el-card shadow="hover" class="login-inline-card">
          <el-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            label-position="top"
            @submit.prevent="handleInlineLogin"
          >
            <el-form-item label="医院ID卡号" prop="hospital_id">
              <el-input v-model="loginForm.hospital_id" placeholder="孕妇卡号(H开头) / nurse / doctor" size="large">
                <template #prefix><el-icon><User /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input v-model="loginForm.password" type="password" placeholder="Demo密码: 123456" size="large" show-password @keyup.enter="handleInlineLogin">
                <template #prefix><el-icon><Lock /></el-icon></template>
              </el-input>
            </el-form-item>
            <el-button type="primary" size="large" :loading="loginLoading" class="login-inline-btn" @click="handleInlineLogin">
              {{ loginLoading ? '登录中...' : '登 录' }}
            </el-button>
          </el-form>
        </el-card>
      </template>

      <!-- ===== 已登录状态 ===== -->
      <template v-else>
        <!-- 加载状态 -->
        <div v-if="loading" class="page-loading">
          <el-icon class="loading-icon" :size="36"><Loading /></el-icon>
          <p>正在加载资料...</p>
        </div>

        <template v-else>
        <!-- 头像区（顶部，退出按钮在右上角） -->
        <div class="profile-top-bar">
          <div class="avatar-section">
            <div class="avatar-wrapper" @click="handleAvatarClick">
              <el-avatar :size="72" :src="avatarUrl" class="profile-avatar">
                <span class="avatar-fallback">{{ avatarFallback }}</span>
              </el-avatar>
              <div class="avatar-edit-badge">
                <el-icon :size="14"><Edit /></el-icon>
              </div>
            </div>
            <div class="avatar-info">
              <span class="avatar-name">{{ formData.nickname || formData.display_name || '孕妇' }}</span>
              <span class="avatar-id">{{ formData.hospital_id || '' }}</span>
            </div>
          </div>
          <el-button text type="danger" size="small" @click="handleLogout">退出</el-button>
        </div>

        <!-- 资料表单 -->
        <el-card shadow="hover" class="profile-form-card">
          <template #header>
            <div class="card-header">
              <el-icon color="var(--primary)" :size="18"><User /></el-icon>
              <span>基本信息</span>
            </div>
          </template>

          <el-form
            ref="formRef"
            :model="formData"
            :rules="formRules"
            label-position="top"
            size="large"
            class="profile-form"
          >
            <el-form-item label="显示名" prop="display_name">
              <el-input
                v-model="formData.display_name"
                disabled
                placeholder="系统设定显示名"
              />
            </el-form-item>

            <el-form-item label="昵称" prop="nickname">
              <el-input
                v-model="formData.nickname"
                placeholder="请输入昵称"
                maxlength="20"
                show-word-limit
              />
            </el-form-item>

            <el-form-item label="手机号" prop="phone">
              <el-input
                v-model="formData.phone"
                placeholder="请输入手机号"
                maxlength="11"
                @focus="handlePhoneFocus"
              />
            </el-form-item>

            <el-form-item label="医院ID卡号" prop="hospital_id">
              <el-input
                v-model="formData.hospital_id"
                placeholder="请输入医院就诊卡号"
                maxlength="30"
              />
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 保存按钮 -->
        <div class="save-section">
          <el-button
            type="primary"
            size="large"
            class="save-btn"
            :loading="saving"
            @click="handleSave"
          >
            <el-icon v-if="!saving"><Check /></el-icon>
            {{ saving ? '保存中...' : '保存修改' }}
          </el-button>
        </div>
      </template>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { Loading, Edit, User, Calendar, Check, Lock } from '@element-plus/icons-vue'
import { pregnantApi } from '@/api/endpoints'
import { useAppStore } from '@/stores/app'
import type { Pregnant } from '@/types'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import axios from 'axios'

/* ============ 认证状态 ============ */
const appStore = useAppStore()
const isLoggedIn = computed(() => appStore.isLoggedIn)
const pregnantId = computed(() => appStore.currentPregnantId || localStorage.getItem('currentPregnantId') || '')

/* ============ 登录表单 ============ */
const loginFormRef = ref<FormInstance>()
const loginLoading = ref(false)
const loginForm = reactive({ hospital_id: '', password: '' })
const loginRules: FormRules = {
  hospital_id: [{ required: true, message: '请输入医院ID卡号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleInlineLogin() {
  if (!loginFormRef.value) return
  const valid = await loginFormRef.value.validate().catch(() => false)
  if (!valid) return
  loginLoading.value = true
  try {
    const res = await axios.post('/api/v1/auth/login', {
      hospital_id: loginForm.hospital_id.trim(),
      password: loginForm.password.trim(),
    })
    if (!res.data.success) { ElMessage.error(res.data.message); return }
    appStore.login(res.data.role, res.data.pregnant_id)
    ElMessage.success(`欢迎，${res.data.nickname || res.data.display_name}！`)
    loadProfile()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '网络错误')
  } finally { loginLoading.value = false }
}

function handleLogout() {
  appStore.logout()
  pregnantData.value = null
  ElMessage.info('已退出登录')
}

/* ============ 响应式状态 ============ */
const loading = ref(true)
const saving = ref(false)
const pregnantData = ref<Pregnant | null>(null)
const avatarUrl = ref('')
const phoneVisible = ref(false)
const formRef = ref<FormInstance>()

const formData = reactive({
  display_name: '',
  nickname: '',
  phone: '',
  hospital_id: '',
})

/* ============ 表单校验规则 ============ */
const formRules: FormRules = {
  nickname: [
    { max: 20, message: '昵称不能超过20个字符', trigger: 'blur' },
  ],
  phone: [
    {
      pattern: /^1[3-9]\d{9}$/,
      message: '请输入正确的手机号码',
      trigger: 'blur',
    },
  ],
}

/* ============ 计算属性 ============ */
const avatarFallback = computed(() => {
  const name = pregnantData.value?.nickname || pregnantData.value?.display_name || '孕妇'
  return name.length > 2 ? name.slice(0, 2) : name
})

/* ============ 工具函数 ============ */
function calcGestationalWeek(days?: number): string {
  if (!days && days !== 0) return '--'
  const w = Math.floor(days / 7)
  const d = days % 7
  return d > 0 ? `${w}+${d}` : `${w}`
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '--'
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')}`
}

function formatDateTime(dateStr?: string): string {
  if (!dateStr) return '--'
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function getRiskTagType(tag: string): 'danger' | 'warning' | 'success' | 'info' {
  const lower = tag.toLowerCase()
  if (['red', 'fgr_high_risk', 'high'].includes(lower)) return 'danger'
  if (['orange', 'medium'].includes(lower)) return 'warning'
  if (['green', 'low', 'normal'].includes(lower)) return 'success'
  return 'info'
}

function getRiskTagLabel(tag: string): string {
  const labelMap: Record<string, string> = {
    RED: '高风险',
    ORANGE: '中风险',
    YELLOW: '注意事项',
    GREEN: '低风险',
    fgr_high_risk: 'FGR高风险',
    routine: '常规',
  }
  return labelMap[tag] || tag
}

/* ============ 手机号脱敏 ============ */
function maskPhone(phone?: string): string {
  if (!phone || phone.length < 11) return phone || '--'
  return phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2')
}

function handlePhoneFocus() {
  if (!phoneVisible.value && pregnantData.value?.phone) {
    formData.phone = pregnantData.value.phone
    phoneVisible.value = true
  }
}

/* ============ 操作函数 ============ */
function handleAvatarClick() {
  ElMessage.info('头像上传功能即将上线，敬请期待')
}

async function handleSave() {
  // 表单校验
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const updateData: Partial<Pregnant> = {
      nickname: formData.nickname,
      phone: formData.phone,
      hospital_id: formData.hospital_id,
    }
    await pregnantApi.update(pregnantId.value, updateData)
    ElMessage.success('资料保存成功')
    // 恢复脱敏显示
    phoneVisible.value = false
    formData.phone = maskPhone(formData.phone)
  } catch (err) {
    console.error('保存资料失败:', err)
    ElMessage.error('保存失败，请稍后重试')
  } finally {
    saving.value = false
  }
}

/* ============ 数据加载 ============ */
async function loadProfile() {
  const pid = pregnantId.value
  if (!pid) return
  loading.value = true
  try {
    const res = await pregnantApi.get(pid)
    pregnantData.value = res.data

    formData.display_name = res.data.display_name || ''
    formData.nickname = res.data.nickname || ''
    formData.phone = maskPhone(res.data.phone)
    formData.hospital_id = res.data.hospital_id || ''
  } catch (err) {
    console.error('加载资料失败:', err)
    ElMessage.error('加载资料失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

/* ============ 生命周期 ============ */
onMounted(() => {
  if (isLoggedIn.value) loadProfile()
})
</script>

<style scoped>
.patient-profile {
  min-height: 100vh;
  background: var(--bg-page);
}

.profile-container {
  max-width: 600px;
  margin: 0 auto;
  padding: 28px 20px 60px;
}

/* ========== 页面头部 ========== */
.profile-header {
  margin-bottom: 28px;
}

.profile-header .page-title {
  font-family: 'Figtree', sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

/* ========== 加载状态 ========== */
.page-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  gap: 16px;
  color: var(--text-muted);
}

.loading-icon {
  animation: spin 1.2s linear infinite;
  color: var(--primary);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ========== 顶部头像栏 ========== */
.profile-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  padding: 0 4px;
}

.avatar-section {
  display: flex;
  align-items: center;
  gap: 14px;
}

.avatar-wrapper {
  position: relative;
  cursor: pointer;
  flex-shrink: 0;
}

.avatar-wrapper:hover .avatar-edit-badge {
  opacity: 1;
}

.profile-avatar {
  box-shadow: var(--shadow-md);
  border: 3px solid var(--primary-lighter);
  font-size: 26px;
  font-weight: 700;
  color: var(--primary);
  background: var(--primary-bg) !important;
}

.avatar-fallback {
  font-family: 'Figtree', sans-serif;
}

.avatar-edit-badge {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--primary-gradient);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s;
  box-shadow: var(--shadow-sm);
}

.avatar-info {
  display: flex;
  flex-direction: column;
}

.avatar-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.avatar-id {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* ========== 表单卡片 ========== */
.profile-form-card {
  margin-bottom: 16px;
  border-radius: var(--radius-lg) !important;
  box-shadow: var(--shadow);
  border: 1px solid var(--border) !important;
  transition: var(--transition);
}

.profile-form-card:hover {
  box-shadow: var(--shadow-hover);
}

.profile-form-card :deep(.el-card__header) {
  padding: 16px 20px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
}

.profile-form-card :deep(.el-card__body) {
  padding: 24px 20px 8px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: 'Figtree', sans-serif;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.profile-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: var(--text-secondary);
}

.profile-form :deep(.el-input.is-disabled .el-input__inner) {
  background: var(--bg-surface);
  color: var(--text-muted);
  cursor: not-allowed;
}

/* ========== 保存按钮区 ========== */
.save-section {
  padding: 0 0 40px;
}

.save-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
  font-weight: 600;
  border-radius: var(--radius);
  letter-spacing: 0.3px;
}

.save-btn .el-icon {
  margin-right: 6px;
}

/* ========== 内联登录卡片 ========== */
.login-inline-card {
  border-radius: var(--radius-lg) !important;
  box-shadow: var(--shadow);
  border: 1px solid var(--border) !important;
}

.login-inline-card :deep(.el-card__body) {
  padding: 24px 20px;
}

.login-inline-btn {
  width: 100%;
  margin-top: 8px;
  height: 44px;
}

/* ========== 响应式（移动端适配） ========== */
@media (max-width: 480px) {
  .profile-container {
    padding: 16px 12px 60px;
  }

  .profile-avatar {
    width: 56px !important;
    height: 56px !important;
    font-size: 20px;
  }

  .avatar-name {
    font-size: 15px;
  }

  .save-btn {
    height: 44px;
    font-size: 15px;
  }
}
</style>
