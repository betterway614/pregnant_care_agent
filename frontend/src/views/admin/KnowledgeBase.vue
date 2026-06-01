<template>
  <div class="kb-page">
    <!-- ═══════════════════ 1. STATS CARDS ═══════════════════ -->
    <el-row :gutter="16" class="stat-cards">
      <el-col :xs="12" :sm="6" v-for="card in statCards" :key="card.label">
        <el-card shadow="never" class="stat-card-wrapper">
          <div class="stat-card">
            <div class="stat-card__icon" :style="{ background: card.bg }">
              <el-icon :size="22" :color="card.color">
                <component :is="card.icon" />
              </el-icon>
            </div>
            <div class="stat-card__info">
              <div class="stat-card__label">{{ card.label }}</div>
              <div class="stat-card__value" :class="{ 'stat-card__value--sm': card.small }">
                {{ card.value }}
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══════════════════ 2. RAG CONFIG PANEL ═══════════════════ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <div class="section-header__left">
            <el-icon :size="18" color="#0891b2"><Setting /></el-icon>
            <span>RAG 配置</span>
          </div>
          <el-button
            type="primary"
            size="small"
            :loading="savingConfig"
            @click="handleSaveConfig"
          >
            保存配置
          </el-button>
        </div>
      </template>

      <el-form :model="ragForm" label-width="110px" size="default" class="rag-form">
        <el-row :gutter="24">
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="检索策略">
              <el-segmented v-model="ragForm.search_type" :options="searchTypeOptions" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="分词策略">
              <el-segmented v-model="ragForm.chunking_strategy" :options="chunkingOptions" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="最大结果数">
              <el-slider
                v-model="ragForm.max_results"
                :min="1"
                :max="20"
                :step="1"
                show-input
                input-size="small"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="24">
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="分块大小">
              <el-input-number
                v-model="ragForm.chunk_size"
                :min="100"
                :max="10000"
                :step="100"
                controls-position="right"
              />
              <span class="form-unit">tokens</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="分块重叠">
              <el-input-number
                v-model="ragForm.chunk_overlap"
                :min="0"
                :max="2000"
                :step="50"
                controls-position="right"
              />
              <span class="form-unit">tokens</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="Reranker">
              <el-select v-model="ragForm.reranker_provider" placeholder="不启用" clearable>
                <el-option label="不启用" value="" />
                <el-option label="Cohere" value="cohere" />
                <el-option label="Infinity" value="infinity" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="24" v-if="ragForm.reranker_provider">
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="Reranker 模型">
              <el-input v-model="ragForm.reranker_model" placeholder="如 rerank-v3.5" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8" v-if="ragForm.reranker_provider === 'infinity'">
            <el-form-item label="服务地址">
              <el-input v-model="ragForm.reranker_base_url" placeholder="http://localhost:7997/rerank" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <el-descriptions :column="4" border size="small" class="config-readonly">
        <el-descriptions-item label="Embedding 模型">{{ ragConfig.embedding_model }}</el-descriptions-item>
        <el-descriptions-item label="向量维度">{{ ragConfig.embedding_dimensions }}</el-descriptions-item>
        <el-descriptions-item label="向量表">{{ ragConfig.vector_db_table }}</el-descriptions-item>
        <el-descriptions-item label="RAG 状态">
          <el-tag :type="ragConfig.enabled ? 'success' : 'danger'" size="small">
            {{ ragConfig.enabled ? '已启用' : '未启用' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- ═══════════════════ 3. DOCUMENT TABLE ═══════════════════ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <div class="section-header__left">
            <el-icon :size="18" color="#0891b2"><Document /></el-icon>
            <span>知识库文档</span>
            <el-tag size="small" type="info" class="doc-count-tag">{{ documents.length }} 个</el-tag>
          </div>
          <div class="section-header__actions">
            <el-button :icon="Refresh" @click="loadData" :loading="loading" size="small">刷新</el-button>
            <el-button type="primary" :icon="Upload" @click="openUploadDialog" size="small">上传文档</el-button>
            <el-button type="warning" :icon="RefreshRight" @click="handleIngestAll" :loading="ingesting" size="small">
              全量入库
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="documents"
        v-loading="loading"
        stripe
        highlight-current-row
        style="width: 100%;"
        empty-text="暂无知识库文档，请上传或放入 knowledge_docs/ 目录"
        :header-cell-style="{ background: '#f8fafc', color: '#334155', fontWeight: 600 }"
      >
        <el-table-column prop="name" label="文档名称" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="doc-name">
              <div class="doc-icon-badge" :style="{ background: getFileBg(row.extension) }">
                <el-icon :size="14" :color="getFileColor(row.extension)">
                  <Document />
                </el-icon>
              </div>
              <span class="doc-name-text">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="extension" label="类型" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="getFileTypeTag(row.extension)" effect="plain">
              {{ row.extension.replace('.', '') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="size_human" label="大小" width="90" align="center" />
        <el-table-column label="元数据标签" min-width="200">
          <template #default="{ row }">
            <div class="meta-tags" v-if="row.metadata && Object.keys(filterDisplayMeta(row.metadata)).length > 0">
              <el-tag
                v-for="(val, key) in filterDisplayMeta(row.metadata)"
                :key="key"
                size="small"
                effect="plain"
                class="meta-tag"
              >
                {{ key }}: {{ val }}
              </el-tag>
            </div>
            <span v-else class="no-meta">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="modified_at" label="修改时间" width="150" align="center">
          <template #default="{ row }">
            {{ formatTime(row.modified_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              size="small"
              @click="handleIngestSingle(row.filename)"
              :loading="ingestingFiles.has(row.filename)"
            >
              入库
            </el-button>
            <el-button
              type="danger"
              link
              size="small"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══════════════════ 4. SEARCH TEST PANEL ═══════════════════ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <div class="section-header__left">
            <el-icon :size="18" color="#0891b2"><Search /></el-icon>
            <span>知识库检索测试</span>
          </div>
        </div>
      </template>

      <el-form :inline="true" class="search-form" @submit.prevent="handleSearch">
        <el-form-item label="检索内容" class="search-form__query">
          <el-input
            v-model="searchQuery"
            placeholder="输入问题测试知识库检索效果..."
            clearable
            style="width: 400px;"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="过滤条件">
          <el-select
            v-model="searchFilterKey"
            placeholder="标签"
            clearable
            style="width: 120px;"
          >
            <el-option v-for="tag in predefinedTags" :key="tag" :label="tag" :value="tag" />
          </el-select>
          <el-input
            v-if="searchFilterKey"
            v-model="searchFilterValue"
            placeholder="值"
            clearable
            style="width: 120px; margin-left: 8px;"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :icon="Search"
            @click="handleSearch"
            :loading="searching"
            :disabled="!searchQuery.trim()"
          >
            检索
          </el-button>
        </el-form-item>
      </el-form>

      <div v-if="searchResults.length > 0" class="search-results">
        <div class="search-results__header">
          <span>检索结果 ({{ searchResults.length }} 条)</span>
        </div>
        <div
          v-for="(result, idx) in searchResults"
          :key="idx"
          class="search-result-item"
        >
          <div class="search-result-item__header">
            <el-tag size="small" type="info">#{{ idx + 1 }}</el-tag>
            <el-tag v-if="result.score !== null" size="small" effect="plain" type="success">
              相关度: {{ (result.score * 100).toFixed(1) }}%
            </el-tag>
            <el-tag
              v-for="(val, key) in result.metadata"
              :key="key"
              size="small"
              effect="plain"
              class="meta-tag"
            >
              {{ key }}: {{ val }}
            </el-tag>
          </div>
          <div class="search-result-item__content">
            {{ result.content }}
          </div>
        </div>
      </div>
      <el-empty v-else-if="searchPerformed" description="未检索到相关内容" :image-size="80" />
    </el-card>

    <!-- ═══════════════════ 5. UPLOAD DIALOG ═══════════════════ -->
    <el-dialog
      v-model="showUploadDialog"
      title="上传知识库文档"
      width="600px"
      :close-on-click-modal="false"
      @close="resetUpload"
      destroy-on-close
    >
      <el-form label-width="100px" class="upload-form">
        <el-form-item label="选择文件">
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            accept=".md,.txt,.pdf"
            drag
            class="upload-dragger"
          >
            <div class="upload-dragger__inner">
              <el-icon :size="40" color="#0891b2"><UploadFilled /></el-icon>
              <div class="upload-dragger__text">
                拖拽文件至此，或 <em>点击上传</em>
              </div>
              <div class="upload-dragger__tip">支持 .md / .txt / .pdf，最大 20MB</div>
            </div>
          </el-upload>
        </el-form-item>

        <el-form-item label="文档名称">
          <el-input v-model="uploadName" placeholder="留空则使用文件名" />
        </el-form-item>

        <el-form-item label="自动入库">
          <el-switch v-model="autoIngest" active-text="是" inactive-text="否" />
        </el-form-item>

        <el-form-item label="元数据标签">
          <div class="metadata-editor">
            <div
              v-for="(entry, idx) in metadataEntries"
              :key="idx"
              class="metadata-row"
            >
              <el-select
                v-model="entry.key"
                placeholder="选择标签"
                style="width: 140px;"
                filterable
              >
                <el-option
                  v-for="tag in availableMetaTags(idx)"
                  :key="tag"
                  :label="tag"
                  :value="tag"
                />
              </el-select>
              <el-input
                v-model="entry.value"
                placeholder="标签值"
                style="flex: 1; margin: 0 8px;"
              />
              <el-button
                :icon="Minus"
                circle
                size="small"
                @click="removeMetadataEntry(idx)"
                type="danger"
                plain
              />
            </div>
            <el-button
              :icon="Plus"
              size="small"
              @click="addMetadataEntry"
              :disabled="metadataEntries.length >= predefinedTags.length"
              plain
            >
              添加标签
            </el-button>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button
          type="primary"
          @click="handleUpload"
          :loading="uploading"
          :disabled="!uploadFile"
        >
          上传{{ autoIngest ? '并入库' : '' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Document, Upload, UploadFilled, Refresh, RefreshRight,
  Search, Coin, Cpu, Setting, Plus, Minus, Connection, Grid,
} from '@element-plus/icons-vue'
import { adminApi } from '@/api/admin'
import type { KnowledgeDoc, RagConfig, KnowledgeSearchResult } from '@/types'
import dayjs from 'dayjs'

const loading = ref(false)
const ingesting = ref(false)
const uploading = ref(false)
const savingConfig = ref(false)
const searching = ref(false)
const showUploadDialog = ref(false)
const uploadFile = ref<File | null>(null)
const uploadName = ref('')
const autoIngest = ref(true)
const ingestingFiles = ref(new Set<string>())
const documents = ref<KnowledgeDoc[]>([])

// Chunks state
const loadingChunks = ref(false)
const chunks = ref<any[]>([])
const chunkTotal = ref(0)
const chunkPage = ref(1)
const chunkPageSize = ref(20)
const chunkFilterName = ref('')
const chunkDocStats = ref<Array<{ name: string; chunk_count: number; avg_content_length: number }>>([])

const ragConfig = reactive<RagConfig>({
  enabled: true,
  search_type: 'hybrid',
  chunk_size: 600,
  chunk_overlap: 120,
  chunking_strategy: 'fixed_size',
  max_results: 5,
  embedding_model: '',
  embedding_dimensions: 0,
  embedding_api_url: '',
  reranker_provider: '',
  reranker_model: '',
  reranker_base_url: '',
  vector_db_table: '',
  predefined_tags: [],
  docs_directory: '',
})

const ragForm = reactive({
  search_type: 'hybrid',
  chunk_size: 600,
  chunk_overlap: 120,
  chunking_strategy: 'fixed_size',
  max_results: 5,
  reranker_provider: '',
  reranker_model: '',
  reranker_base_url: '',
})

const metadataEntries = ref<Array<{ key: string; value: string }>>([])
const predefinedTags = ref<string[]>([])

const searchQuery = ref('')
const searchFilterKey = ref('')
const searchFilterValue = ref('')
const searchResults = ref<KnowledgeSearchResult[]>([])
const searchPerformed = ref(false)

const searchTypeOptions = [
  { label: '混合检索', value: 'hybrid' },
  { label: '向量检索', value: 'vector' },
]
const chunkingOptions = [
  { label: '固定分块', value: 'fixed_size' },
  { label: '递归分块', value: 'recursive' },
]

const statCards = computed(() => [
  {
    label: '文档总数',
    value: ragConfig.enabled ? documents.value.length : '-',
    icon: 'Document',
    bg: '#ecfeff',
    color: '#0891b2',
  },
  {
    label: '总大小',
    value: documents.value.reduce((sum, d) => sum + d.size_bytes, 0) > 0
      ? formatBytes(documents.value.reduce((sum, d) => sum + d.size_bytes, 0))
      : '0 B',
    icon: 'Coin',
    bg: '#f0fdf4',
    color: '#059669',
  },
  {
    label: 'Embedding 模型',
    value: ragConfig.embedding_model || '-',
    icon: 'Cpu',
    bg: '#faf5ff',
    color: '#7c3aed',
    small: true,
  },
  {
    label: '检索模式',
    value: ragConfig.search_type === 'hybrid' ? '混合检索' : '向量检索',
    icon: 'Connection',
    bg: '#fff7ed',
    color: '#ea580c',
  },
])

async function loadData() {
  loading.value = true
  try {
    const [configRes, docsRes] = await Promise.all([
      adminApi.getRagConfig(),
      adminApi.getKnowledgeDocs(),
    ])
    Object.assign(ragConfig, configRes.data)
    predefinedTags.value = configRes.data.predefined_tags || []
    ragForm.search_type = ragConfig.search_type
    ragForm.chunk_size = ragConfig.chunk_size
    ragForm.chunk_overlap = ragConfig.chunk_overlap
    ragForm.chunking_strategy = ragConfig.chunking_strategy
    ragForm.max_results = ragConfig.max_results
    ragForm.reranker_provider = ragConfig.reranker_provider
    ragForm.reranker_model = ragConfig.reranker_model
    ragForm.reranker_base_url = ragConfig.reranker_base_url
    documents.value = docsRes.data.data
  } catch (err: any) {
    ElMessage.error('加载失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    loading.value = false
  }
}

async function loadChunks(page?: number) {
  if (page) chunkPage.value = page
  loadingChunks.value = true
  try {
    const [chunksRes, statsRes] = await Promise.all([
      adminApi.getKnowledgeChunks(chunkPage.value, chunkPageSize.value, chunkFilterName.value || undefined),
      adminApi.getChunkStats(),
    ])
    chunks.value = chunksRes.data.data
    chunkTotal.value = chunksRes.data.total
    chunkDocStats.value = statsRes.data.documents
  } catch (err: any) {
    ElMessage.error('加载文本块失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    loadingChunks.value = false
  }
}

async function handleSaveConfig() {
  savingConfig.value = true
  try {
    const updates: Record<string, any> = {}
    if (ragForm.search_type !== ragConfig.search_type) updates.search_type = ragForm.search_type
    if (ragForm.chunk_size !== ragConfig.chunk_size) updates.chunk_size = ragForm.chunk_size
    if (ragForm.chunk_overlap !== ragConfig.chunk_overlap) updates.chunk_overlap = ragForm.chunk_overlap
    if (ragForm.chunking_strategy !== ragConfig.chunking_strategy) updates.chunking_strategy = ragForm.chunking_strategy
    if (ragForm.max_results !== ragConfig.max_results) updates.max_results = ragForm.max_results
    if (ragForm.reranker_provider !== ragConfig.reranker_provider) updates.reranker_provider = ragForm.reranker_provider
    if (ragForm.reranker_model !== ragConfig.reranker_model) updates.reranker_model = ragForm.reranker_model
    if (ragForm.reranker_base_url !== ragConfig.reranker_base_url) updates.reranker_base_url = ragForm.reranker_base_url

    if (Object.keys(updates).length === 0) {
      ElMessage.info('配置未变更')
      return
    }

    const res = await adminApi.updateRagConfig(updates)
    Object.assign(ragConfig, res.data.config)
    ElMessage.success('RAG 配置已更新')
  } catch (err: any) {
    ElMessage.error('保存失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    savingConfig.value = false
  }
}

function openUploadDialog() {
  metadataEntries.value = []
  showUploadDialog.value = true
}

function handleFileChange(file: any) {
  uploadFile.value = file.raw
  if (!uploadName.value) {
    uploadName.value = file.name.replace(/\.[^.]+$/, '')
  }
}

function handleFileRemove() {
  uploadFile.value = null
  uploadName.value = ''
}

function resetUpload() {
  uploadFile.value = null
  uploadName.value = ''
  autoIngest.value = true
  metadataEntries.value = []
}

async function handleUpload() {
  if (!uploadFile.value) return
  uploading.value = true
  try {
    const metadata: Record<string, string> = {}
    for (const entry of metadataEntries.value) {
      if (entry.key && entry.value) metadata[entry.key] = entry.value
    }

    const res = await adminApi.uploadKnowledgeDocWithMeta(
      uploadFile.value,
      uploadName.value || undefined,
      autoIngest.value,
      Object.keys(metadata).length > 0 ? metadata : undefined,
    )
    const data = res.data
    if (data.ingested) {
      ElMessage.success(`"${data.name}" 上传并入库成功`)
    } else if (data.ingest_error) {
      ElMessage.warning(`上传成功，入库失败: ${data.ingest_error}`)
    } else {
      ElMessage.success(`"${data.name}" 上传成功`)
    }
    showUploadDialog.value = false
    loadData()
  } catch (err: any) {
    ElMessage.error('上传失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    uploading.value = false
  }
}

async function handleDelete(doc: KnowledgeDoc) {
  try {
    await ElMessageBox.confirm(
      `确定删除文档 "${doc.name}" 吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await adminApi.deleteKnowledgeDoc(doc.filename)
    ElMessage.success(`"${doc.name}" 已删除`)
    loadData()
  } catch (err: any) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }
}

async function handleIngestSingle(filename: string) {
  ingestingFiles.value.add(filename)
  try {
    const res = await adminApi.ingestSingleDoc(filename, true)
    ElMessage.success(res.data.message)
  } catch (err: any) {
    ElMessage.error('入库失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    ingestingFiles.value.delete(filename)
  }
}

async function handleIngestAll() {
  try {
    await ElMessageBox.confirm(
      '将对所有文档执行全量入库（向量化），已有数据会被覆盖。是否继续？',
      '全量入库确认',
      { type: 'warning', confirmButtonText: '执行', cancelButtonText: '取消' },
    )
  } catch { return }

  ingesting.value = true
  try {
    const res = await adminApi.ingestAllDocs(true)
    if (res.data.failed > 0) {
      ElMessage.warning(`${res.data.message}，${res.data.failed} 个失败`)
    } else {
      ElMessage.success(res.data.message)
    }
  } catch (err: any) {
    ElMessage.error('全量入库失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    ingesting.value = false
  }
}

function addMetadataEntry() {
  metadataEntries.value.push({ key: '', value: '' })
}

function removeMetadataEntry(idx: number) {
  metadataEntries.value.splice(idx, 1)
}

function availableMetaTags(currentIdx: number): string[] {
  const usedKeys = new Set(
    metadataEntries.value
      .filter((_, i) => i !== currentIdx)
      .map(e => e.key)
      .filter(Boolean)
  )
  return predefinedTags.value.filter(t => !usedKeys.has(t))
}

function filterDisplayMeta(meta: Record<string, string>): Record<string, string> {
  const skip = new Set(['source', 'filename', 'uploaded_at'])
  const result: Record<string, string> = {}
  for (const [k, v] of Object.entries(meta)) {
    if (!skip.has(k) && v) result[k] = v
  }
  return result
}

async function handleSearch() {
  if (!searchQuery.value.trim()) return
  searching.value = true
  searchPerformed.value = false
  try {
    const filters: Record<string, string> | undefined =
      searchFilterKey.value && searchFilterValue.value
        ? { [searchFilterKey.value]: searchFilterValue.value }
        : undefined

    const res = await adminApi.searchKnowledge(searchQuery.value, filters)
    searchResults.value = res.data.results
    searchPerformed.value = true
  } catch (err: any) {
    ElMessage.error('检索失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    searching.value = false
  }
}

function formatTime(iso: string) {
  return dayjs(iso).format('MM-DD HH:mm')
}

function formatBytes(bytes: number): string {
  for (const unit of ['B', 'KB', 'MB', 'GB']) {
    if (bytes < 1024) return `${bytes.toFixed(1)} ${unit}`
    bytes /= 1024
  }
  return `${bytes.toFixed(1)} TB`
}

function getFileColor(ext: string) {
  const map: Record<string, string> = { '.md': '#0891b2', '.txt': '#059669', '.pdf': '#dc2626' }
  return map[ext] || '#64748b'
}

function getFileBg(ext: string) {
  const map: Record<string, string> = { '.md': '#ecfeff', '.txt': '#f0fdf4', '.pdf': '#fef2f2' }
  return map[ext] || '#f1f5f9'
}

function getFileTypeTag(ext: string): '' | 'success' | 'danger' | 'warning' {
  const map: Record<string, '' | 'success' | 'danger' | 'warning'> = { '.md': '', '.txt': 'success', '.pdf': 'danger' }
  return map[ext] || 'warning'
}

onMounted(() => {
  loadData()
  loadChunks()
})
</script>

<style scoped>
.kb-page {
  max-width: 1280px;
  font-family: 'Fira Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}

.stat-cards { margin-bottom: 16px; }

.stat-card-wrapper {
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}
.stat-card-wrapper:hover {
  box-shadow: 0 2px 12px rgba(8, 145, 178, 0.08);
  border-color: #0891b2;
}

.stat-card { display: flex; align-items: center; gap: 14px; }
.stat-card__icon {
  width: 44px; height: 44px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.stat-card__info { flex: 1; min-width: 0; }
.stat-card__label { font-size: 12px; color: #64748b; margin-bottom: 2px; }
.stat-card__value { font-size: 22px; font-weight: 700; color: #0f172a; line-height: 1.2; }
.stat-card__value--sm { font-size: 13px; font-weight: 600; word-break: break-all; line-height: 1.4; }

.section-card { border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header__left { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 15px; color: #0f172a; }
.section-header__actions { display: flex; gap: 8px; }
.doc-count-tag { margin-left: 4px; }

.rag-form { padding-top: 4px; }
.form-unit { margin-left: 8px; font-size: 12px; color: #94a3b8; }
.config-readonly { margin-top: 16px; }

.doc-name { display: flex; align-items: center; gap: 10px; }
.doc-icon-badge {
  width: 28px; height: 28px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.doc-name-text { font-weight: 500; color: #1e293b; }
.meta-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.meta-tag { font-size: 11px; }
.no-meta { color: #cbd5e1; font-size: 13px; }

.search-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; }
.search-form__query { flex: 1; min-width: 300px; }
.search-results { margin-top: 16px; border-top: 1px solid #e2e8f0; padding-top: 12px; }
.search-results__header { font-size: 13px; font-weight: 600; color: #475569; margin-bottom: 12px; }
.search-result-item {
  padding: 12px 16px; background: #f8fafc; border-radius: 8px;
  margin-bottom: 8px; border: 1px solid #e2e8f0; transition: border-color 0.2s ease;
}
.search-result-item:hover { border-color: #0891b2; }
.search-result-item__header { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.search-result-item__content {
  font-size: 13px; color: #334155; line-height: 1.6;
  white-space: pre-wrap; word-break: break-word; max-height: 120px; overflow-y: auto;
}

/* ── Chunks Panel ── */
.chunk-stats-row { margin-bottom: 0; }
.chunk-stat-card {
  padding: 10px 14px; background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 8px; cursor: pointer; transition: border-color 0.2s ease, box-shadow 0.2s ease;
  margin-bottom: 8px;
}
.chunk-stat-card:hover { border-color: #0891b2; box-shadow: 0 2px 8px rgba(8,145,178,0.08); }
.chunk-stat-card__name { font-size: 13px; font-weight: 600; color: #1e293b; margin-bottom: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chunk-stat-card__count { font-size: 18px; font-weight: 700; color: #0891b2; }
.chunk-stat-card__len { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.chunk-preview { font-size: 12px; color: #475569; line-height: 1.5; max-height: 60px; overflow: hidden; word-break: break-word; }
.chunk-expand { padding: 12px 16px; background: #fafbfc; }
.chunk-expand__label { font-size: 12px; font-weight: 600; color: #64748b; margin-bottom: 6px; }
.chunk-expand__content { font-size: 13px; color: #334155; line-height: 1.7; white-space: pre-wrap; word-break: break-word; margin-bottom: 12px; }
.chunk-expand__meta { margin-top: 8px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }

.upload-dragger { width: 100%; }
.upload-dragger__inner { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 24px 0; }
.upload-dragger__text { margin-top: 8px; font-size: 14px; color: #475569; }
.upload-dragger__text em { color: #0891b2; font-style: normal; font-weight: 500; }
.upload-dragger__tip { margin-top: 4px; font-size: 12px; color: #94a3b8; }

.metadata-editor { width: 100%; }
.metadata-row { display: flex; align-items: center; margin-bottom: 8px; }

@media (max-width: 768px) {
  .stat-card__value { font-size: 18px; }
  .section-header { flex-direction: column; align-items: flex-start; gap: 8px; }
  .section-header__actions { width: 100%; flex-wrap: wrap; }
  .search-form__query { min-width: 100%; }
  .search-form__query .el-input { width: 100% !important; }
}
</style>
