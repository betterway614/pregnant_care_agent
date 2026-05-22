<template>
  <div class="patient-profile">
    <div class="page-container profile-container">
      <!-- 未登录状态：路由守卫已拦截，此处保留防御性提示 -->
      <template v-if="!isLoggedIn">
        <div class="profile-header">
          <h1 class="page-title">请先登录</h1>
          <p class="page-subtitle">正在跳转到登录页面...</p>
        </div>
      </template>

      <!-- 已登录状态 -->
      <template v-else>
        <!-- 加载状态 -->
        <div v-if="loading" class="page-loading">
          <el-icon class="is-loading" :size="36" color="#FB7185"><Loading /></el-icon>
          <p>正在加载资料...</p>
        </div>

        <template v-else>
          <!-- 头像区 -->
          <div class="profile-top-bar">
            <div class="avatar-section">
              <div class="avatar-wrapper interactive-card" @click="handleAvatarClick">
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
            <el-button text type="danger" size="large" class="logout-btn interactive-card" @click="handleLogout">退出</el-button>
          </div>

          <!-- 资料表单 -->
          <div class="soft-card form-card">
            <div class="card-header">
              <el-icon color="#FB7185" :size="20"><User /></el-icon>
              <span>基本信息</span>
            </div>

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
          </div>

          <!-- 保存按钮 -->
          <div class="save-section">
            <el-button
              type="primary"
              size="large"
              class="save-btn interactive-card"
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
import { Loading, Edit, User, Check } from '@element-plus/icons-vue'
import { pregnantApi } from '@/api/endpoints'
import { useAppStore } from '@/stores/app'
import type { Pregnant } from '@/types'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'

/* ============ 认证状态 ============ */
const appStore = useAppStore()
const isLoggedIn = computed(() => appStore.isLoggedIn)
const pregnantId = computed(() => appStore.currentPregnantId || localStorage.getItem('currentPregnantId') || '')

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
/* ========== 全局变量 (Soft UI Colors) ========== */
.patient-profile {
  --c-rose: #FB7185;
  --c-rose-light: #FFF1F2;
  --c-sky: #38BDF8;
  --c-slate-800: #1E293B;
  --c-slate-600: #475569;
  --c-slate-400: #94A3B8;
  --c-bg: #F8FAFC;
  --card-shadow: 0 4px 16px rgba(148, 163, 184, 0.1);

  background: var(--c-bg);
  min-height: 100vh;
  font-family: 'Nunito Sans', 'PingFang SC', sans-serif;
}

.profile-container {
  max-width: 480px;
  margin: 0 auto;
  padding: 32px 16px 60px;
}

/* ========== 交互动画基础 ========== */
.interactive-card {
  cursor: pointer;
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  -webkit-tap-highlight-color: transparent;
}
.interactive-card:active {
  transform: scale(0.96);
}

/* ========== 页面头部 ========== */
.profile-header {
  margin-bottom: 28px;
  text-align: center;
}
.profile-header .page-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--c-slate-800);
  margin-bottom: 8px;
}
.page-subtitle {
  font-size: 14px;
  color: var(--c-slate-600);
}

/* ========== 加载状态 ========== */
.page-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  gap: 16px;
  color: var(--c-slate-600);
}

/* ========== 通用软卡片 ========== */
.soft-card {
  background: white;
  border-radius: 20px;
  box-shadow: var(--card-shadow);
  margin-bottom: 24px;
  padding: 24px 20px;
}

/* ========== 顶部头像栏 ========== */
.profile-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 32px;
  padding: 0 8px;
}
.avatar-section {
  display: flex;
  align-items: center;
  gap: 16px;
}
.avatar-wrapper {
  position: relative;
}
.profile-avatar {
  background: var(--c-rose-light) !important;
  color: var(--c-rose);
  font-weight: 700;
  font-size: 24px;
  border: 4px solid white;
  box-shadow: var(--card-shadow);
}
.avatar-edit-badge {
  position: absolute;
  bottom: 0;
  right: -4px;
  width: 28px;
  height: 28px;
  background: var(--c-rose);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid white;
}
.avatar-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.avatar-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--c-slate-800);
}
.avatar-id {
  font-size: 13px;
  color: var(--c-slate-600);
}
.logout-btn {
  border-radius: 12px;
}

/* ========== 表单卡片 ========== */
.form-card {
  padding: 0;
  overflow: hidden;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px;
  background: var(--c-bg);
  border-bottom: 1px solid white;
  font-size: 16px;
  font-weight: 700;
  color: var(--c-slate-800);
}
.profile-form {
  padding: 24px 20px 8px;
}

/* 覆盖 Element Plus 样式为圆润风格 */
:deep(.el-input__wrapper) {
  border-radius: 12px;
  box-shadow: 0 0 0 1px var(--c-slate-400) inset;
}
:deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px var(--c-rose) inset;
}
:deep(.el-form-item__label) {
  font-weight: 600;
  color: var(--c-slate-800);
}

/* ========== 按钮区 ========== */
.save-section {
  padding-top: 16px;
}
.save-btn {
  width: 100%;
  height: 52px;
  border-radius: 16px;
  font-size: 16px;
  font-weight: 700;
  background-color: var(--c-rose);
  border-color: var(--c-rose);
}
.save-btn:hover {
  background-color: #f43f5e; /* rose-500 */
  border-color: #f43f5e;
}
</style>
