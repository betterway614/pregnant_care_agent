<template>
  <div class="api-config">
    <!-- 模式切换 -->
    <el-card shadow="never" class="mode-card">
      <div class="mode-header">
        <div class="mode-header__info">
          <h3>全局接入模式</h3>
          <p class="mode-desc">统一控制 LLM / ASR / TTS / Embedding 的接入方式</p>
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

    <!-- 本地服务状态总览 (local/mixed 模式显示) -->
    <el-card v-if="config.llm_mode === 'local' || config.llm_mode === 'mixed'" shadow="never" class="section-card status-card">
      <template #header>
        <div class="section-header">
          <div>
            <h3>本地服务状态</h3>
            <p class="section-desc">实时检测本地 AI 服务运行状态</p>
          </div>
          <el-button size="small" :loading="checkingServices" @click="checkAllServices">
            <el-icon><Refresh /></el-icon>
            刷新状态
          </el-button>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :span="6" v-for="svc in localServices" :key="svc.key">
          <div class="service-status-card" :class="svc.status">
            <div class="service-status-card__header">
              <el-icon :size="18" :color="svc.status === 'online' ? '#10b981' : svc.status === 'offline' ? '#ef4444' : '#94a3b8'">
                <component :is="svc.icon" />
              </el-icon>
              <span class="service-status-card__name">{{ svc.name }}</span>
              <el-tag :type="svc.status === 'online' ? 'success' : svc.status === 'offline' ? 'danger' : 'info'" size="small" effect="dark">
                {{ svc.status === 'online' ? '运行中' : svc.status === 'offline' ? '未运行' : '检测中' }}
              </el-tag>
            </div>
            <div class="service-status-card__info">
              <div class="info-row"><span class="label">端口</span><span class="value">{{ svc.port }}</span></div>
              <div class="info-row"><span class="label">地址</span><span class="value">{{ svc.url }}</span></div>
              <div v-if="svc.model" class="info-row"><span class="label">模型</span><span class="value">{{ svc.model }}</span></div>
              <div v-if="svc.device" class="info-row"><span class="label">设备</span><span class="value">{{ svc.device }}</span></div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 云端 API 配置 -->
    <el-card v-if="config.llm_mode === 'cloud' || config.llm_mode === 'mixed'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <div>
            <h3>云端 API 配置</h3>
            <p class="section-desc">配置云端大模型供应商 (LLM / ASR / TTS / Embedding)</p>
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
            <el-icon :size="18" :color="selectedProvider === p.id ? '#3b82f6' : '#94a3b8'">
              <component :is="getProviderIcon(p.id)" />
            </el-icon>
            <span class="provider-card__name">{{ p.name }}</span>
            <el-icon v-if="selectedProvider === p.id" :size="14" color="#3b82f6"><CircleCheck /></el-icon>
          </div>
          <p class="provider-card__desc">{{ p.description }}</p>
        </div>
      </div>

      <el-divider />

      <!-- LLM 云端配置 -->
      <h4 class="sub-title">LLM 模型</h4>
      <el-form label-width="120px" label-position="left" class="config-form">
        <el-form-item label="API Key">
          <el-input v-model="config.cloud_api_key" type="password" show-password placeholder="输入 API Key" @change="markDirty" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="config.cloud_base_url" placeholder="API 基础地址" @change="markDirty">
            <template #prepend>HTTPS://</template>
          </el-input>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="主模型">
              <el-select v-model="config.cloud_model" filterable allow-create placeholder="选择模型" @change="markDirty" style="width: 100%;">
                <el-option v-for="m in currentProviderModels" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="视觉模型">
              <el-select v-model="config.cloud_vision_model" filterable allow-create placeholder="选择视觉模型" @change="markDirty" style="width: 100%;">
                <el-option v-for="m in currentProviderModels" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <el-divider />

      <!-- ASR 云端配置 -->
      <h4 class="sub-title">语音识别 (ASR)</h4>
      <el-form label-width="120px" label-position="left" class="config-form">
        <el-form-item label="API Key">
          <el-input v-model="config.asr_cloud_api_key" type="password" show-password placeholder="DashScope API Key (可复用 LLM Key)" @change="markDirty" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="Base URL">
              <el-input v-model="config.asr_cloud_base_url" placeholder="https://dashscope.aliyuncs.com/api/v1" @change="markDirty" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="模型">
              <el-select v-model="config.asr_cloud_model" filterable allow-create @change="markDirty" style="width: 100%;">
                <el-option label="paraformer-v1" value="paraformer-v1" />
                <el-option label="paraformer-v2" value="paraformer-v2" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <el-divider />

      <!-- TTS 云端配置 -->
      <h4 class="sub-title">语音合成 (TTS)</h4>
      <el-form label-width="120px" label-position="left" class="config-form">
        <el-form-item label="API Key">
          <el-input v-model="config.tts_cloud_api_key" type="password" show-password placeholder="DashScope API Key (可复用 LLM Key)" @change="markDirty" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="Base URL">
              <el-input v-model="config.tts_cloud_base_url" placeholder="https://dashscope.aliyuncs.com/api/v1" @change="markDirty" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="模型">
              <el-select v-model="config.tts_cloud_model" filterable allow-create @change="markDirty" style="width: 100%;">
                <el-option label="cosyvoice-v1" value="cosyvoice-v1" />
                <el-option label="cosyvoice-v2" value="cosyvoice-v2" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="音色">
          <el-select v-model="config.tts_cloud_voice" filterable allow-create @change="markDirty" style="width: 300px;">
            <el-option label="龙小春 (女声)" value="longxiaochun" />
            <el-option label="龙小夏 (男声)" value="longxiaoxia" />
          </el-select>
        </el-form-item>
      </el-form>

      <el-divider />

      <!-- Embedding 云端配置 -->
      <h4 class="sub-title">向量嵌入 (Embedding)</h4>
      <el-form label-width="120px" label-position="left" class="config-form">
        <el-form-item label="API Key">
          <el-input v-model="config.embedding_api_key" type="password" show-password placeholder="DashScope API Key (可复用 LLM Key)" @change="markDirty" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="API 地址">
              <el-input v-model="config.embedding_api_url" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" @change="markDirty" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="模型">
              <el-select v-model="config.embedding_model" filterable allow-create @change="markDirty" style="width: 100%;">
                <el-option label="text-embedding-v3" value="text-embedding-v3" />
                <el-option label="text-embedding-v2" value="text-embedding-v2" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="维度">
              <el-input-number v-model="config.embedding_dimensions" :min="128" :max="4096" :step="128" @change="markDirty" style="width: 100%;" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 本地服务配置 (local/mixed 模式显示) -->
    <el-card v-if="config.llm_mode === 'local' || config.llm_mode === 'mixed'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <div>
            <h3>本地服务配置</h3>
            <p class="section-desc">配置本地推理服务地址和参数</p>
          </div>
        </div>
      </template>

      <!-- LLM 本地配置 -->
      <h4 class="sub-title">LLM 推理服务</h4>
      <el-form label-width="120px" label-position="left" class="config-form">
        <el-form-item label="Ollama 地址">
          <el-input v-model="config.ollama_host" placeholder="http://localhost:11434" @change="markDirty">
            <template #prepend><el-icon><Monitor /></el-icon></template>
          </el-input>
          <span class="form-tip">Ollama 服务的基础地址</span>
        </el-form-item>
        <el-form-item label="兼容 API 地址">
          <el-input v-model="config.local_base_url" placeholder="留空则自动使用 Ollama 地址" @change="markDirty">
            <template #prepend><el-icon><Connection /></el-icon></template>
          </el-input>
          <span class="form-tip">vLLM / SGLang / llama-server 等 OpenAI 兼容服务地址（优先级高于 Ollama）</span>
        </el-form-item>
        <el-form-item label="本地模型">
          <el-input v-model="config.local_model" placeholder="Qwen3.6-35B-A3B" @change="markDirty">
            <template #prepend><el-icon><Cpu /></el-icon></template>
          </el-input>
          <span class="form-tip">本地部署的模型名称</span>
        </el-form-item>
      </el-form>

      <el-divider />

      <!-- ASR 本地配置 -->
      <h4 class="sub-title">
        语音识别 (ASR)
        <el-tag v-if="localServices[0].status === 'online'" type="success" size="small" effect="plain" style="margin-left: 8px;">运行中</el-tag>
        <el-tag v-else-if="localServices[0].status === 'offline'" type="danger" size="small" effect="plain" style="margin-left: 8px;">未运行</el-tag>
      </h4>
      <el-form label-width="120px" label-position="left" class="config-form">
        <el-form-item label="后端引擎">
          <el-radio-group v-model="config.asr_local_backend" @change="markDirty">
            <el-radio value="funasr">FunASR</el-radio>
            <el-radio value="whisper">Whisper</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="服务地址">
          <el-input v-model="config.asr_local_base_url" placeholder="http://127.0.0.1:10096" @change="markDirty">
            <template #prepend><el-icon><Connection /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item label="热词">
          <el-input v-model="config.asr_local_hotword" placeholder="可选，用于提高识别准确率" @change="markDirty" />
        </el-form-item>
      </el-form>

      <el-divider />

      <!-- TTS 本地配置 -->
      <h4 class="sub-title">
        语音合成 (TTS)
        <el-tag v-if="localServices[1].status === 'online'" type="success" size="small" effect="plain" style="margin-left: 8px;">运行中</el-tag>
        <el-tag v-else-if="localServices[1].status === 'offline'" type="danger" size="small" effect="plain" style="margin-left: 8px;">未运行</el-tag>
      </h4>
      <el-form label-width="120px" label-position="left" class="config-form">
        <el-form-item label="后端引擎">
          <el-radio-group v-model="config.tts_local_backend" @change="markDirty">
            <el-radio value="cosyvoice">CosyVoice2</el-radio>
            <el-radio value="edge">Edge TTS</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="config.tts_local_backend === 'cosyvoice'">
          <el-form-item label="服务地址">
            <el-input v-model="config.tts_local_cosyvoice_url" placeholder="http://127.0.0.1:9880" @change="markDirty">
              <template #prepend><el-icon><Connection /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item label="发音人">
            <el-select v-model="config.tts_local_cosyvoice_speaker" filterable allow-create @change="markDirty" style="width: 300px;">
              <el-option label="中文女" value="中文女" />
              <el-option label="中文男" value="中文男" />
            </el-select>
          </el-form-item>
        </template>
      </el-form>

      <el-divider />

      <!-- Embedding 本地配置 -->
      <h4 class="sub-title">
        向量嵌入 (Embedding)
        <el-tag v-if="localServices[2].status === 'online'" type="success" size="small" effect="plain" style="margin-left: 8px;">运行中</el-tag>
        <el-tag v-else-if="localServices[2].status === 'offline'" type="danger" size="small" effect="plain" style="margin-left: 8px;">未运行</el-tag>
      </h4>
      <el-form label-width="120px" label-position="left" class="config-form">
        <el-form-item label="服务地址">
          <el-input v-model="config.embedding_api_url" placeholder="http://127.0.0.1:8081/v1" @change="markDirty">
            <template #prepend><el-icon><Connection /></el-icon></template>
          </el-input>
          <span class="form-tip">本地 BGE-M3 嵌入服务地址</span>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="模型">
              <el-select v-model="config.embedding_model" filterable allow-create @change="markDirty" style="width: 100%;">
                <el-option label="bge-m3 (本地)" value="bge-m3" />
                <el-option label="text-embedding-v3" value="text-embedding-v3" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="维度">
              <el-input-number v-model="config.embedding_dimensions" :min="128" :max="4096" :step="128" @change="markDirty" style="width: 100%;" />
            </el-form-item>
          </el-col>
        </el-row>
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
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Cloudy, Monitor, Connection, DataBoard, CircleCheck,
  RefreshLeft, Check, Cpu, User, FirstAidKit, Van, Refresh,
  Microphone, Headset, Document,
} from '@element-plus/icons-vue'
import { adminApi } from '@/api/admin'
import client from '@/api/client'
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
  // ASR
  asr_mode: 'local',
  asr_cloud_api_key: '',
  asr_cloud_base_url: 'https://dashscope.aliyuncs.com/api/v1',
  asr_cloud_model: 'paraformer-v1',
  asr_local_backend: 'funasr',
  asr_local_base_url: 'http://127.0.0.1:10096',
  asr_local_model: 'local-funasr',
  asr_local_hotword: '',
  // TTS
  tts_mode: 'local',
  tts_cloud_api_key: '',
  tts_cloud_base_url: 'https://dashscope.aliyuncs.com/api/v1',
  tts_cloud_model: 'cosyvoice-v1',
  tts_cloud_voice: 'longxiaochun',
  tts_local_backend: 'cosyvoice',
  tts_local_cosyvoice_url: 'http://127.0.0.1:9880',
  tts_local_cosyvoice_speaker: '中文女',
  // Embedding
  embedding_api_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  embedding_api_key: '',
  embedding_model: 'text-embedding-v3',
  embedding_dimensions: 1024,
})

const selectedProvider = ref('dashscope')
const isDirty = ref(false)
const saving = ref(false)
const testing = ref(false)
const checkingServices = ref(false)
const testResult = ref<ApiTestResult | null>(null)

// 本地服务状态
const localServices = reactive([
  { key: 'asr', name: 'ASR (FunASR)', icon: 'Microphone', port: '10096', url: 'http://127.0.0.1:10096', model: '', device: '', status: 'unknown' as 'online' | 'offline' | 'unknown' },
  { key: 'tts', name: 'TTS (CosyVoice2)', icon: 'Headset', port: '9880', url: 'http://127.0.0.1:9880', model: '', device: '', status: 'unknown' as 'online' | 'offline' | 'unknown' },
  { key: 'embedding', name: 'Embedding (BGE-M3)', icon: 'Document', port: '8081', url: 'http://127.0.0.1:8081', model: '', device: '', status: 'unknown' as 'online' | 'offline' | 'unknown' },
  { key: 'llm', name: 'LLM (Qwen3.6)', icon: 'Cpu', port: '8080', url: 'http://127.0.0.1:8080', model: '', device: '', status: 'unknown' as 'online' | 'offline' | 'unknown' },
])

const roleConfigs = computed(() => [
  { key: 'pregnant', label: '孕妇端', icon: 'User', color: '#f97316', mode: config.value.llm_pregnant_mode, model: config.value.llm_pregnant_model },
  { key: 'nurse', label: '护士端', icon: 'FirstAidKit', color: '#10b981', mode: config.value.llm_nurse_mode, model: config.value.llm_nurse_model },
  { key: 'doctor', label: '医生端', icon: 'Van', color: '#3b82f6', mode: config.value.llm_doctor_mode, model: config.value.llm_doctor_model },
])

const currentProviderModels = computed(() => {
  const provider = config.value.available_providers.find(p => p.id === selectedProvider.value)
  return provider?.available_models || []
})

const testResultMessage = computed(() => {
  if (!testResult.value) return ''
  let msg = testResult.value.message
  if (testResult.value.latency_ms) msg += ` (延迟: ${testResult.value.latency_ms}ms)`
  if (testResult.value.model) msg += ` | 模型: ${testResult.value.model}`
  return msg
})

function getProviderIcon(id: string) {
  if (id === 'dashscope') return 'Cloudy'
  if (id === 'deepseek') return 'Cpu'
  return 'Connection'
}

function markDirty() { isDirty.value = true }
function onModeChange() { markDirty() }

function selectProvider(id: string) {
  selectedProvider.value = id
  const provider = config.value.available_providers.find(p => p.id === id)
  if (provider) {
    config.value.cloud_base_url = provider.base_url
    if (provider.api_key) config.value.cloud_api_key = provider.api_key
    config.value.cloud_model = provider.default_model
  }
  markDirty()
}

// 检查本地服务状态（通过后端代理，避免 SSH 端口转发场景下前端无法访问 127.0.0.1）
async function checkAllServices() {
  checkingServices.value = true
  try {
    const res = await client.get(`/admin/resource/services-health`, { timeout: 5000 })
    const servicesData = res.data?.services || {}
    localServices.forEach((svc) => {
      const keyMap: Record<string, string> = {
        asr: 'asr',
        tts: 'tts',
        embedding: 'bge_m3',
        llm: 'llm',
      }
      const backendKey = keyMap[svc.key] || svc.key
      const data = servicesData[backendKey]
      if (data?.online) {
        svc.status = 'online'
        if (data.model) svc.model = data.model
        if (data.device) svc.device = data.device
      } else {
        svc.status = 'offline'
      }
    })
  } catch {
    localServices.forEach((svc) => { svc.status = 'offline' })
  }
  checkingServices.value = false
}

async function testConnection(mode: 'local' | 'cloud') {
  testing.value = true
  testResult.value = null
  try {
    const res = await adminApi.testApiConnection(mode, mode === 'cloud' ? selectedProvider.value : undefined)
    testResult.value = res.data
  } catch (err: any) {
    testResult.value = { success: false, message: err.response?.data?.detail || err.message || '测试失败' }
  } finally {
    testing.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    for (const rc of roleConfigs.value) {
      const modeKey = `llm_${rc.key}_mode` as keyof ApiConfig
      const modelKey = `llm_${rc.key}_model` as keyof ApiConfig
      ;(config.value as any)[modeKey] = rc.mode
      ;(config.value as any)[modelKey] = rc.model
    }
    await adminApi.updateApiConfig(config.value as any)
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
  }
}

onMounted(() => {
  fetchConfig()
  checkAllServices()
})
</script>

<style scoped>
.api-config { max-width: 960px; }
.mode-card { margin-bottom: 16px; }
.mode-header { display: flex; align-items: center; justify-content: space-between; }
.mode-header h3 { margin: 0 0 4px 0; font-size: 15px; color: #0f172a; }
.mode-desc { margin: 0; font-size: 13px; color: #94a3b8; }
.section-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header h3 { margin: 0 0 4px 0; font-size: 15px; color: #0f172a; }
.section-desc { margin: 0; font-size: 13px; color: #94a3b8; }
.sub-title { margin: 0 0 12px 0; font-size: 14px; font-weight: 600; color: #1e293b; }

/* ===== 统一卡牌设计系统 ===== */
/* 共享卡牌基础样式：边框、圆角、padding、过渡 */
.admin-card-base {
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
  box-sizing: border-box;
  transition: all 0.2s;
}

/* 供应商卡片 */
.provider-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.provider-card {
  @apply admin-card-base;
  padding: 14px 16px;
  cursor: pointer;
  min-height: 80px;
  display: flex;
  flex-direction: column;
}
.provider-card:hover { border-color: #93c5fd; background: #f8fafc; }
.provider-card.active { border-color: #3b82f6; background: #eff6ff; }
.provider-card__header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.provider-card__name { flex: 1; font-size: 13px; font-weight: 600; color: #0f172a; line-height: 1.3; }
.provider-card__desc { margin: 0; font-size: 12px; color: #64748b; line-height: 1.5; }

/* ===== 服务状态卡牌 - 统一尺寸和排版 ===== */
.service-status-card {
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  height: 152px;          /* 固定高度，确保4张卡牌完全对齐 */
  display: flex;
  flex-direction: column;
  transition: all 0.2s;
  box-sizing: border-box;
  background: #fff;
}
.service-status-card.online { border-color: #67c23a; background: #f0f9eb; }
.service-status-card.offline { border-color: #f56c6c; background: #fef0f0; }
.service-status-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-shrink: 0;
}
.service-status-card__name {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.service-status-card__info {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 4px;
}
.service-status-card__info .info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  line-height: 1.4;
}
.service-status-card__info .label {
  color: #64748b;
  flex-shrink: 0;
  font-size: 12px;
}
.service-status-card__info .value {
  color: #1e293b;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 65%;
}

/* 表单 */
.config-form { max-width: 700px; }
.form-tip { display: block; font-size: 12px; color: #94a3b8; margin-top: 4px; }

/* 角色表格 */
.role-cell { display: flex; align-items: center; gap: 6px; }

/* Mock 模式 */
.mock-card :deep(.el-result) { padding: 24px 0; }

/* 测试结果 */
.test-success :deep(.el-card__body), .test-fail :deep(.el-card__body) { padding: 0; }
.test-success { border-color: #67c23a; }
.test-fail { border-color: #f56c6c; }

/* 保存栏 */
.save-bar { display: flex; justify-content: flex-end; gap: 12px; padding: 16px 0; position: sticky; bottom: 0; background: #f1f5f9; z-index: 10; }
</style>
