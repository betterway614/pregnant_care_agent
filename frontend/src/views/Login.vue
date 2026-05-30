<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <div class="logo-area">
          <el-icon :size="48" color="var(--primary)"><FirstAidKit /></el-icon>
          <h1 class="platform-title">AI-Care 孕期智能管理平台</h1>
        </div>
        <p class="platform-desc">请输入您的医院ID卡号和密码登录</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="login-form"
        @submit.prevent="handleLogin"
      >
        <el-form-item label="医院ID卡号" prop="hospital_id">
          <el-input
            v-model="form.hospital_id"
            placeholder="孕妇输入卡号(H开头)，护士输nurse，医生输doctor"
            size="large"
            :prefix-icon="UserFilled"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="Demo默认密码：123456"
            size="large"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          :loading="loggingIn"
          class="login-btn"
          @click="handleLogin"
        >
          {{ loggingIn ? '登录中...' : '登 录' }}
        </el-button>
      </el-form>

      <div class="login-hint">
        <p><b>Demo账号：</b></p>
        <p>孕妇：卡号 H202501 ~ H202520，密码 123456</p>
        <p>护士：nurse / nurse123</p>
        <p>医生：doctor / doctor123</p>
        <p>管理员：admin / admin123</p>
      </div>

      <div class="compliance-notice">
        <el-icon><Warning /></el-icon>
        <span>本系统仅用于科研教学辅助，不替代临床诊断。所有AI分析结果需经医生审核确认。</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { UserFilled, Lock, Warning } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { useAppStore } from '@/stores/app'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const appStore = useAppStore()
const formRef = ref<FormInstance>()
const loggingIn = ref(false)

const form = reactive({
  hospital_id: '',
  password: '',
})

const rules: FormRules = {
  hospital_id: [{ required: true, message: '请输入医院ID卡号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loggingIn.value = true
  try {
    const res = await axios.post('/api/v1/auth/login', {
      hospital_id: form.hospital_id.trim(),
      password: form.password.trim(),
    })

    const data = res.data
    if (!data.success) {
      ElMessage.error(data.message || '登录失败')
      return
    }

    // 存储 JWT token
    localStorage.setItem('token', data.token)

    // 登录成功
    if (data.role === 'pregnant') {
      appStore.login('pregnant', data.pregnant_id)
    } else {
      appStore.login(data.role as any)
    }

    ElMessage.success(`欢迎，${data.nickname || data.display_name}！`)

    // 跳转：优先回跳到被拦截的原路径
    const redirect = router.currentRoute.value.query.redirect as string
    if (redirect) {
      router.push(redirect)
    } else {
      const routes: Record<string, string> = {
        nurse: '/nurse/dashboard',
        doctor: '/doctor/dashboard',
        admin: '/admin/dashboard',
        pregnant: '/pregnant/home',
      }
      router.push(routes[data.role] || '/login')
    }
  } catch (err: any) {
    const msg = err.response?.data?.detail || '网络错误，请检查后端是否启动'
    ElMessage.error(msg)
  } finally {
    loggingIn.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #E8F5E9 0%, #F3E5F5 50%, #E3F2FD 100%);
  padding: 20px;
}

.login-card {
  background: #fff;
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  padding: 40px 36px;
  width: 100%;
  max-width: 420px;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.logo-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.platform-title {
  font-family: 'Figtree', sans-serif;
  font-size: 22px;
  font-weight: 800;
  background: linear-gradient(135deg, var(--primary), #AB47BC);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.platform-desc {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: 8px;
}

.login-form {
  margin-top: 8px;
}

.login-btn {
  width: 100%;
  margin-top: 8px;
  height: 44px;
  font-size: 16px;
}

.login-hint {
  margin-top: 24px;
  padding: 14px 16px;
  background: #F8FAFC;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.8;
}

.login-hint b {
  color: var(--text-secondary);
}

.login-hint p {
  margin: 2px 0;
}

.compliance-notice {
  margin-top: 16px;
  padding: 10px 14px;
  background: #FFF3E0;
  border: 1px solid #FFE0B2;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: #E65100;
  display: flex;
  align-items: center;
  gap: 8px;
  line-height: 1.5;
}
</style>
