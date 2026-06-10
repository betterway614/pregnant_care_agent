<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">孕妇管理</h1>
      <span class="page-subtitle">共 {{ total }} 人</span>
    </div>

    <!-- 搜索与筛选 -->
    <div class="search-bar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索孕妇姓名/昵称..."
        clearable
        :prefix-icon="Search"
        class="search-input"
        @input="debouncedSearch"
      />
      <el-select v-model="filterRiskTag" placeholder="风险标签" clearable class="filter-select" @change="loadPatients">
        <el-option label="全部" value="" />
        <el-option label="高龄" value="高龄" />
        <el-option label="高血压" value="高血压" />
        <el-option label="糖尿病" value="糖尿病" />
        <el-option label="双胎" value="双胎" />
        <el-option label="FGR" value="FGR" />
      </el-select>
      <el-checkbox v-model="filterHasAlert" @change="loadPatients">仅显示有预警</el-checkbox>
      <el-button :icon="Refresh" @click="loadPatients" :loading="loading" circle />
    </div>

    <!-- 孕妇表格 -->
    <div class="content-card">
      <div class="content-card__body" v-loading="loading">
        <el-table :data="patients" stripe style="width: 100%" @row-click="goDetail">
          <el-table-column prop="display_name" label="姓名" min-width="90" />
          <el-table-column label="昵称" width="80">
            <template #default="{ row }">
              {{ row.nickname || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="孕周" width="90" align="center">
            <template #default="{ row }">
              {{ formatGestWeek(row.gestational_age_days) }}
            </template>
          </el-table-column>
          <el-table-column label="风险标签" min-width="140">
            <template #default="{ row }">
              <el-tag
                v-for="tag in (row.risk_tags || [])"
                :key="tag"
                size="small"
                type="warning"
                style="margin-right: 4px; margin-bottom: 2px"
              >
                {{ tag }}
              </el-tag>
              <span v-if="!row.risk_tags?.length" class="text-muted">无</span>
            </template>
          </el-table-column>
          <el-table-column label="活跃预警" width="90" align="center">
            <template #default="{ row }">
              <el-badge :value="row.active_alert_count" :hidden="!row.active_alert_count" type="danger">
                <el-icon v-if="!row.active_alert_count" color="var(--text-muted)"><CircleCheck /></el-icon>
              </el-badge>
            </template>
          </el-table-column>
          <el-table-column label="最近随访" width="110" align="center">
            <template #default="{ row }">
              {{ row.latest_followup_date ? formatDate(row.latest_followup_date) : '无记录' }}
            </template>
          </el-table-column>
          <el-table-column label="预产期" width="110" align="center">
            <template #default="{ row }">
              {{ row.edd || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click.stop="goDetail(row)">
                详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="!patients.length && !loading" class="empty-state">
          <el-icon :size="40" color="var(--text-light)"><User /></el-icon>
          <p>{{ searchQuery ? '未找到匹配的孕妇' : '暂无孕妇数据' }}</p>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination-wrap" v-if="total > pageSize">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="loadPatients"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh, CircleCheck, User } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import { dashboardApi } from '@/api/endpoints'

const router = useRouter()
const appStore = useAppStore()
const loading = ref(false)
const patients = ref<any[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchQuery = ref('')
const filterRiskTag = ref('')
const filterHasAlert = ref(false)

/** 防抖搜索 */
let searchTimer: ReturnType<typeof setTimeout> | null = null
function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    currentPage.value = 1
    loadPatients()
  }, 300)
}

/** 加载孕妇列表 */
async function loadPatients() {
  loading.value = true
  try {
    const res = await dashboardApi.pregnant({
      search: searchQuery.value || undefined,
      risk_tag: filterRiskTag.value || undefined,
      has_alert: filterHasAlert.value || undefined,
      page: currentPage.value,
      page_size: pageSize.value,
    })
    const data = res.data
    patients.value = data?.data || []
    total.value = data?.total || 0
  } catch (err) {
    console.error('加载孕妇列表失败:', err)
  } finally {
    loading.value = false
  }
}

/** 跳转孕妇详情 */
function goDetail(row: any) {
  const role = appStore.currentRole
  const routeName = role === 'doctor' ? 'DoctorPregnantDetail' : 'NursePregnantDetail'
  router.push({ name: routeName, params: { pregnantId: row.pregnant_id } })
}

/** 格式化孕周 */
function formatGestWeek(days?: number): string {
  if (!days) return '未知'
  const w = Math.floor(days / 7)
  const d = days % 7
  return `${w}+${d}`
}

/** 格式化日期 */
function formatDate(d?: string): string {
  if (!d) return ''
  return d.slice(0, 10)
}

onMounted(() => {
  loadPatients()
})
</script>

<style scoped>
.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.search-input {
  width: 240px;
}

.filter-select {
  width: 140px;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin-left: 12px;
}

.text-muted {
  color: var(--text-muted);
  font-size: 12px;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 0;
  gap: 14px;
}

.empty-state p {
  color: var(--text-muted);
  font-size: 14px;
  font-weight: 500;
}

/* Responsive */
@media (max-width: 768px) {
  .search-bar {
    flex-direction: column;
    align-items: stretch;
  }
  .search-input {
    width: 100%;
  }
  .filter-select {
    width: 100%;
  }
  .page-subtitle {
    display: block;
    margin-left: 0;
    margin-top: 4px;
  }
}
</style>
