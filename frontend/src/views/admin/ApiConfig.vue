<template>
  <div class="api-config">
    <!-- 模式切换 -->
    <el-card shadow="never" class="mode-card">
      <div class="mode-header">
        <div class="mode-header__info">
          <h3>API 接入模式</h3>
          <p class="mode-desc">选择 LLM 服务的接入方式</p>
        </div>
        <el-radio-group v-model="config.llm_mode" size="large" @change="onModeChange">
          <el-radio-button value="cloud">
            <el-icon><Cloudy /></el-icon>
            <span>云端 API</span>
          </el-radio-button>
          <el-radio-button value="local">
            <el-icon><Monitor /></el-icon>
            <span>本地服务</span>
          </el-radio-button>
          <el-radio-button value="mixed">
            <el-icon><Connection /></el-icon>
            <span>混合模式</span>
          </el-radio-button>
          <el-radio-button value="mock">
            <el-icon><DataBoard /></el-icon>
            <span>Mock</span>
          </el-radio-button>
        </el-radio-group>
      </div>
    </el-card>

    <!-- 云端 API 配置 -->
    <el-card v-if="config.llm_mode === 'cloud' || config.llm_mode === 'mixed'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <div>
            <h3>云端 API 配置</h3>
            <p class="section-desc">配置云端大模型供应商</p>
          </div>
          <el-button type="primary" plain size="small" :loading="testing" @click="testConnection('cloud')">
            <el-icon><Connection /></el-icon>
            测试连接
          </el-button>
        </div>
      </template>

      <!-- 供应商选择 -->
      <div class="provider-grid">
        <div
          v-for="p in config.available_providers"
          :key="p.id"
          class="provider-card"
          :class="{ active: selectedProvider === p.id }"
          @click="selectProvider(p.id)"
        >
          <div class="provider-card__header">
            <el-icon :size="20" :color="selectedProvider === p.id ? '#3b82f6' : '#94a3b8'">
              <component :is="getProviderIcon(p.id)" />
            </el-icon>
            <span class="provider-card__name">{{ p.name }}</span>
            <el-icon v-if="selectedProvider === p.id" :size="16" color="#3b82f6"><CircleCheck /></el-icon>
          </div>
          <p class="provider-card__desc">{{ p.description }}</p>
        </div>
      </div>

      <!-- 供应商详细配置 -->
      <el-form label-width="120px" label-position="left" class="config-form" style="margin-top: 20px;">
        <el-form-item label="API Key">
          <el-input
            v-model="config.cloud_api_key"
            type="password"
            show-password
            placeholder="输入 API Key"
            @change="markDirty"
          />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input
            v-model="config.cloud_base_url"
            placeholder="API 基础地址"
            @change="markDirty"
          >
            <template #prepend>HTTPS://</template>
          </el-input>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="主模型">
              <el-select v-model="config.cloud_model" filterable allow-create placeholder="选择模型" @change="markDirty" style="width: 100%;">
                <el-option
                  v-for="m in currentProviderModels"
                  :key="m"
                  :label="m"
                  :value="m"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="视觉模型">
              <el-select v-model="config.cloud_vision_model" filterable allow-create placeholder="选择视觉模型" @change="markDirty" style="width: 100%;">
                <el-option
                  v-for="m in currentProviderModels"
                  :key="m"
                  :label="m"
                  :value="m"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 本地服务配置 -->
    <el-card v-if="config.llm_mode === 'local' || config.llm_mode === 'mixed'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <div>
            <h3>本地服务配置</h3>
            <p class="section-desc">配置本地 Ollama / vLLM / SGLang 推理服务</p>
          </div>
          <el-button type="primary" plain size="small" :loading="testing" @click="testConnection('local')">
            <el-icon><Connection /></el-icon>
            测试连接
          </el-button>
        </div>
      </template>

      <el-form label-width="120px" label-position="left" class="config-form">
        <el-form-item label="Ollama 地址">
          <el-input
            v-model="config.ollama_host"
            placeholder="http://localhost:11434"
            @change="markDirty"
          >
            <template #prepend>
              <el-icon><Monitor /></el-icon>
            </template>
          </el-input>
          <span class="form-tip">Ollama 服务的基础地址</span>
        </el-form-item>
        <el-form-item label="兼容 API 地址">
          <el-input
            v-model="config.local_base_url"
            placeholder="留空则自动使用 Ollama 地址"
            @change="markDirty"
          >
            <template #prepend>
              <el-icon><Connection /></el-icon>
            </template>
          </el-input>
          <span class="form-tip">vLLM / SGLang 等 OpenAI 兼容服务地址（优先级高于 Ollama）</span>
        </el-form-item>
        <el-form-item label="本地模型">
          <el-input
            v-model="config.local_model"
            placeholder="Qwen3.6-35B-A3B"
            @change="markDirty"
          >
            <template #prepend>
              <el-icon><Cpu /></el-icon>
            </template>
          </el-input>
          <span class="form-tip">本地部署的模型名称</span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Mock 模式提示 -->
    <el-card v-if="config.llm_mode === 'mock'" shadow="never" class="section-card mock-card">
      <el-result icon="info" title="Mock 模式" sub-title="当前使用模拟数据，不调用真实 LLM 服务。适用于开发调试场景。">
        <template #icon>
          <el-icon :size="64" color="#909399"><DataBoard /></el-icon>
        </template>
      </el-result>
    </el-card>

    <!-- 角色专属配置 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <div>
            <h3>角色专属配置</h3>
            <p class="section-desc">为不同角色设置独立的 LLM 模式和模型（留空则使用全局配置）</p>
          </div>
        </div>
      </template>

      <el-table :data="roleConfigs" stripe>
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <div class="role-cell">
              <el-icon :size="16" :color="row.color"><component :is="row.icon" /></el-icon>
              <span>{{ row.label }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="独立模式" width="160">
          <template #default="{ row }">
            <el-select v-model="row.mode" placeholder="跟随全局" clearable @change="markDirty" size="small">
              <el-option label="云端" value="cloud" />
              <el-option label="本地" value="local" />
              <el-option label="Mock" value="mock" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="独立模型">
          <template #default="{ row }">
            <el-input v-model="row.model" placeholder="跟随全局" clearable @change="markDirty" size="small" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 测试结果 -->
    <el-card v-if="testResult" shadow="never" class="section-card" :class="testResult.success ? 'test-success' : 'test-fail'">
      <el-alert
        :title="testResult.success ? '连接成功' : '连接失败'"
        :type="testResult.success ? 'success' : 'error'"
        :description="testResultMessage"
        show-icon
        :closable="true"
        @close="testResult = null"
      />
    </el-card>

    <!-- 保存按钮 -->
    <div class="save-bar">
      <el-button @click="resetConfig" :disabled="!isDirty">
        <el-icon><RefreshLeft /></el-icon>
        重置
      </el-button>
      <el-button type="primary" :loading="saving" :disabled="!isDirty" @click="saveConfig">
        <el-icon><Check /></el-icon>
        保存配置
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Cloudy, Monitor, Connection, DataBoard, CircleCheck,
  RefreshLeft, Check, Cpu, User, FirstAidKit, Van,
} from '@element-plus/icons-vue'
import { adminApi } from '@/api/admin'
import type { ApiConfig, ApiTestResult, CloudProvider } from '@/types'

const config = ref<ApiConfig>({
  llm_mode: 'cloud',
  local_base_url: '',
  ollama_host: 'http://localhost:11434',
  local_model: 'Qwen3.6-35B-A3B',
  cloud_provider: 'dashscope',
  cloud_api_key: '',
  cloud_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  cloud_model: 'qwen-plus',
  cloud_vision_model: 'qwen-vl-max',
  available_providers: [],
  llm_pregnant_mode: '',
  llm_nurse_mode: '',
  llm_doctor_mode: '',
  llm_pregnant_model: '',
  llm_nurse_model: '',
  llm_doctor_model: '',
})

const selectedProvider = ref('dashscope')
const isDirty = ref(false)
const saving = ref(false)
const testing = ref(false)
const testResult = ref<ApiTestResult | null>(null)

const roleConfigs = computed(() => [
  {
    key: 'pregnant',
    label: '孕妇端',
    icon: 'User',
    color: '#f97316',
    mode: config.value.llm_pregnant_mode,
    model: config.value.llm_pregnant_model,
  },
  {
    key: 'nurse',
    label: '护士端',
    icon: 'FirstAidKit',
    color: '#10b981',
    mode: config.value.llm_nurse_mode,
    model: config.value.llm_nurse_model,
  },
  {
    key: 'doctor',
    label: '医生端',
    icon: 'Van',
    color: '#3b82f6',
    mode: config.value.llm_doctor_mode,
    model: config.value.llm_doctor_model,
  },
])

const currentProviderModels = computed(() => {
  const provider = config.value.available_providers.find(p => p.id === selectedProvider.value)
  return provider?.available_models || []
})

const testResultMessage = computed(() => {
  if (!testResult.value) return ''
  let msg = testResult.value.message
  if (testResult.value.latency_ms) {
    msg += ` (延迟: ${testResult.value.latency_ms}ms)`
  }
  if (testResult.value.model) {
    msg += ` | 模型: ${testResult.value.model}`
  }
  return msg
})

function getProviderIcon(id: string) {
  if (id === 'dashscope') return 'Cloudy'
  if (id === 'deepseek') return 'Cpu'
  return 'Connection'
}

function markDirty() {
  isDirty.value = true
}

function onModeChange() {
  markDirty()
}

function selectProvider(id: string) {
  selectedProvider.value = id
  const provider = config.value.available_providers.find(p => p.id === id)
  if (provider) {
    config.value.cloud_base_url = provider.base_url
    if (provider.api_key) {
      config.value.cloud_api_key = provider.api_key
    }
    config.value.cloud_model = provider.default_model
  }
  markDirty()
}

async function testConnection(mode: 'local' | 'cloud') {
  testing.value = true
  testResult.value = null
  try {
    const res = await adminApi.testApiConnection(mode, mode === 'cloud' ? selectedProvider.value : undefined)
    testResult.value = res.data
  } catch (err: any) {
    testResult.value = {
      success: false,
      message: err.response?.data?.detail || err.message || '测试失败',
    }
  } finally {
    testing.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    // 同步角色配置回 config
    for (const rc of roleConfigs.value) {
      const modeKey = `llm_${rc.key}_mode` as keyof ApiConfig
      const modelKey = `llm_${rc.key}_model` as keyof ApiConfig
      ;(config.value as any)[modeKey] = rc.mode
      ;(config.value as any)[modelKey] = rc.model
    }

    const payload = {
      llm_mode: config.value.llm_mode,
      local_base_url: config.value.local_base_url,
      ollama_host: config.value.ollama_host,
      local_model: config.value.local_model,
      cloud_provider: selectedProvider.value,
      cloud_api_key: config.value.cloud_api_key,
      cloud_base_url: config.value.cloud_base_url,
      cloud_model: config.value.cloud_model,
      cloud_vision_model: config.value.cloud_vision_model,
      llm_pregnant_mode: config.value.llm_pregnant_mode,
      llm_nurse_mode: config.value.llm_nurse_mode,
      llm_doctor_mode: config.value.llm_doctor_mode,
      llm_pregnant_model: config.value.llm_pregnant_model,
      llm_nurse_model: config.value.llm_nurse_model,
      llm_doctor_model: config.value.llm_doctor_model,
    }

    await adminApi.updateApiConfig(payload)
    ElMessage.success('配置已保存')
    isDirty.value = false
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function resetConfig() {
  await fetchConfig()
  isDirty.value = false
  ElMessage.info('已重置为服务端配置')
}

async function fetchConfig() {
  try {
    const res = await adminApi.getApiConfig()
    config.value = res.data
    selectedProvider.value = res.data.cloud_provider || 'dashscope'
  } catch (err: any) {
    ElMessage.error('加载配置失败')
    console.error('fetchConfig error:', err)
  }
}

onMounted(fetchConfig)
</script>

<style scoped>
.api-config {
  max-width: 900px;
}

.mode-card {
  margin-bottom: 16px;
}

.mode-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mode-header h3 {
  margin: 0 0 4px 0;
  font-size: 15px;
  color: #0f172a;
}

.mode-desc {
  margin: 0;
  font-size: 13px;
  color: #94a3b8;
}

.section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-header h3 {
  margin: 0 0 4px 0;
  font-size: 15px;
  color: #0f172a;
}

.section-desc {
  margin: 0;
  font-size: 13px;
  color: #94a3b8;
}

/* 供应商卡片网格 */
.provider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.provider-card {
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: all 0.2s;
  background: #fff;
}

.provider-card:hover {
  border-color: #93c5fd;
  background: #f8fafc;
}

.provider-card.active {
  border-color: #3b82f6;
  background: #eff6ff;
}

.provider-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.provider-card__name {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.provider-card__desc {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

/* 表单 */
.config-form {
  max-width: 600px;
}

.form-tip {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}

/* 角色表格 */
.role-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Mock 模式 */
.mock-card :deep(.el-result) {
  padding: 24px 0;
}

/* 测试结果 */
.test-success :deep(.el-card__body) {
  padding: 0;
}

.test-fail :deep(.el-card__body) {
  padding: 0;
}

.test-success {
  border-color: #67c23a;
}

.test-fail {
  border-color: #f56c6c;
}

/* 保存栏 */
.save-bar {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 0;
  position: sticky;
  bottom: 0;
  background: #f1f5f9;
  z-index: 10;
}
</style>
