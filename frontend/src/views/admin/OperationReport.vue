<template>
  <div class="operation-report">
    <!-- Tab 切换 -->
    <el-tabs v-model="activeTab" class="report-tabs">
      <el-tab-pane label="智能体报告" name="agent">
        <div class="tab-toolbar">
          <el-button type="primary" :loading="generatingAgent" @click="generateAgentReport">
            <el-icon><Document /></el-icon>
            生成报告
          </el-button>
        </div>

        <!-- 智能体报告列表 -->
        <el-card shadow="never" class="section-card">
          <template #header>历史报告</template>
          <el-table
            :data="agentReports"
            stripe
            size="small"
            @row-click="viewAgentReport"
            v-loading="loadingAgentList"
          >
            <el-table-column prop="id" label="报告ID" width="100" />
            <el-table-column prop="created_at" label="生成时间" width="170" />
            <el-table-column prop="total_tokens" label="Token总量" width="120">
              <template #default="{ row }">{{ formatTokens(row.total_tokens) }}</template>
            </el-table-column>
            <el-table-column prop="call_count" label="调用次数" width="100" />
            <el-table-column prop="satisfaction" label="满意度" width="100">
              <template #default="{ row }">
                <el-tag :type="getSatisfactionType(row.satisfaction)" size="small">
                  {{ row.satisfaction }}%
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click.stop="viewAgentReport(row)">
                  查看详情
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 智能体报告详情 -->
        <template v-if="agentDetail">
          <el-row :gutter="16" style="margin-top: 16px;">
            <!-- 概览摘要 -->
            <el-col :span="24">
              <el-card shadow="never" class="section-card">
                <template #header>
                  <div class="section-header">
                    <h3>概览摘要</h3>
                    <el-tag type="info" size="small">报告ID: {{ agentDetail.id }}</el-tag>
                  </div>
                </template>
                <el-descriptions :column="4" border size="small">
                  <el-descriptions-item label="报告周期">{{ agentDetail.period }}</el-descriptions-item>
                  <el-descriptions-item label="总调用次数">{{ agentDetail.call_count.toLocaleString() }}</el-descriptions-item>
                  <el-descriptions-item label="Token总量">{{ formatTokens(agentDetail.total_tokens) }}</el-descriptions-item>
                  <el-descriptions-item label="平均延迟">{{ agentDetail.avg_latency_ms }}ms</el-descriptions-item>
                  <el-descriptions-item label="活跃用户数">{{ agentDetail.active_users }}</el-descriptions-item>
                  <el-descriptions-item label="会话数">{{ agentDetail.session_count }}</el-descriptions-item>
                  <el-descriptions-item label="满意度">
                    <el-tag :type="getSatisfactionType(agentDetail.satisfaction)" size="small">
                      {{ agentDetail.satisfaction }}%
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="异常数">
                    <el-tag :type="agentDetail.anomaly_count > 0 ? 'danger' : 'success'" size="small">
                      {{ agentDetail.anomaly_count }}
                    </el-tag>
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
          </el-row>

          <el-row :gutter="16" style="margin-top: 16px;">
            <!-- Token 消耗分析 (按角色) -->
            <el-col :xs="24" :sm="24" :md="12">
              <el-card shadow="never" class="section-card">
                <template #header>Token 消耗分析</template>
                <VChart :option="tokenByRoleChartOption" autoresize style="height: 280px;" />
                <div class="metric-list" v-if="agentDetail.token_analysis?.by_role">
                  <div class="metric-item" v-for="(stat, role) in agentDetail.token_analysis.by_role" :key="role">
                    <span class="metric-label">{{ roleLabel(role) }}</span>
                    <span class="metric-value">{{ formatTokens(stat.total) }} ({{ stat.count }}次)</span>
                  </div>
                </div>
              </el-card>
            </el-col>

            <!-- 意图分布分析 (新增) -->
            <el-col :xs="24" :sm="24" :md="12">
              <el-card shadow="never" class="section-card">
                <template #header>意图分布分析</template>
                <VChart :option="intentChartOption" autoresize style="height: 280px;" />
                <div class="metric-list" v-if="agentDetail.intent_analysis?.distribution">
                  <div class="metric-item" v-for="item in topIntents" :key="item.intent">
                    <span class="metric-label">{{ item.intent }}</span>
                    <span class="metric-value">{{ item.count }}</span>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>

          <el-row :gutter="16" style="margin-top: 16px;">
            <!-- 工具使用分析 -->
            <el-col :xs="24" :sm="24" :md="12">
              <el-card shadow="never" class="section-card">
                <template #header>工具使用分析</template>
                <VChart :option="toolSuccessChartOption" autoresize style="height: 280px;" />
                <el-table :data="agentDetail.tool_analysis?.top_tools?.slice(0, 5)" stripe size="small" style="margin-top: 12px;">
                  <el-table-column prop="name" label="工具名称" min-width="120" />
                  <el-table-column prop="count" label="调用次数" width="90" />
                  <el-table-column prop="success_rate" label="成功率" width="90">
                    <template #default="{ row }">
                      <el-progress
                        :percentage="row.success_rate"
                        :stroke-width="6"
                        :color="row.success_rate >= 90 ? '#10b981' : row.success_rate >= 70 ? '#f97316' : '#ef4444'"
                      />
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>
            </el-col>

            <!-- 反馈汇总 (新增) -->
            <el-col :xs="24" :sm="24" :md="12">
              <el-card shadow="never" class="section-card">
                <template #header>用户反馈分析</template>
                <div class="feedback-summary" v-if="agentDetail.feedback_summary">
                  <div class="feedback-stat">
                    <div class="feedback-stat__value positive">{{ agentDetail.feedback_summary.positive }}</div>
                    <div class="feedback-stat__label">👍正面</div>
                  </div>
                  <div class="feedback-stat">
                    <div class="feedback-stat__value negative">{{ agentDetail.feedback_summary.negative }}</div>
                    <div class="feedback-stat__label">👎 负面</div>
                  </div>
                  <div class="feedback-stat">
                    <div class="feedback-stat__value">{{ agentDetail.feedback_summary.total }}</div>
                    <div class="feedback-stat__label">总计</div>
                  </div>
                  <div class="feedback-stat">
                    <div class="feedback-stat__value" :class="feedbackRateClass">
                      {{ feedbackRate }}%
                    </div>
                    <div class="feedback-stat__label">满意率</div>
                  </div>
                </div>
                <el-empty v-else description="暂无反馈数据" :image-size="80" />
              </el-card>
            </el-col>
          </el-row>

          <!-- 优化建议 -->
          <el-row :gutter="16" style="margin-top: 16px;">
            <el-col :xs="24" :sm="24" :md="12">
              <el-card shadow="never" class="section-card">
                <template #header>优化建议</template>
                <div class="suggestion-list" v-if="agentDetail.suggestions?.length">
                  <div
                    v-for="(s, idx) in agentDetail.suggestions"
                    :key="idx"
                    class="suggestion-item"
                    :class="`suggestion-${s.priority}`"
                  >
                    <div class="suggestion-header">
                      <el-icon :size="16">
                        <WarningFilled v-if="s.priority === 'high'" />
                        <InfoFilled v-else-if="s.priority === 'medium'" />
                        <SuccessFilled v-else />
                      </el-icon>
                      <span class="suggestion-title">{{ s.title }}</span>
                      <el-tag :type="s.priority === 'high' ? 'danger' : s.priority === 'medium' ? 'warning' : 'success'" size="small">
                        {{ s.priority === 'high' ? '高' : s.priority === 'medium' ? '中' : '低' }}
                      </el-tag>
                    </div>
                    <p class="suggestion-desc">{{ s.description }}</p>
                  </div>
                </div>
                <el-empty v-else description="暂无优化建议" :image-size="80" />
              </el-card>
            </el-col>

            <!-- 异常告警 -->
            <el-col :xs="24" :sm="24" :md="12">
              <el-card shadow="never" class="section-card">
                <template #header>
                  <div class="section-header">
                    <h3>异常告警</h3>
                    <el-tag :type="agentDetail.anomaly_count > 0 ? 'danger' : 'success'" size="small">
                      {{ agentDetail.anomaly_count }} 条
                    </el-tag>
                  </div>
                </template>
                <el-table :data="agentDetail.anomalies" stripe size="small" v-if="agentDetail.anomalies?.length">
                  <el-table-column prop="time" label="时间" width="170" />
                  <el-table-column prop="level" label="级别" width="80">
                    <template #default="{ row }">
                      <el-tag :type="row.level === 'critical' ? 'danger' : row.level === 'warning' ? 'warning' : 'info'" size="small">
                        {{ row.level === 'critical' ? '严重' : row.level === 'warning' ? '警告' : '提示' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="type" label="类型" width="120" />
                  <el-table-column prop="message" label="描述" min-width="200" show-overflow-tooltip />
                  <el-table-column prop="resolved" label="状态" width="80">
                    <template #default="{ row }">
                      <el-tag :type="row.resolved ? 'success' : 'danger'" size="small">
                        {{ row.resolved ? '已解决' : '未解决' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                </el-table>
                <el-empty v-else description="暂无异常告警" :image-size="80" />
              </el-card>
            </el-col>
          </el-row>
        </template>
      </el-tab-pane>

      <!-- ==================== 设备报告 Tab ==================== -->
      <el-tab-pane label="设备报告" name="device">
        <div class="tab-toolbar">
          <el-button type="primary" :loading="generatingDevice" @click="generateDeviceReport">
            <el-icon><Document /></el-icon>
            生成报告
          </el-button>
        </div>

        <!-- 设备报告列表 -->
        <el-card shadow="never" class="section-card">
          <template #header>历史报告</template>
          <el-table
            :data="deviceReports"
            stripe
            size="small"
            @row-click="viewDeviceReport"
            v-loading="loadingDeviceList"
          >
            <el-table-column prop="id" label="报告ID" width="100" />
            <el-table-column prop="created_at" label="生成时间" width="170" />
            <el-table-column prop="health_score" label="健康评分" width="110">
              <template #default="{ row }">
                <el-tag :type="getHealthScoreType(row.health_score)" size="small">
                  {{ row.health_score }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="avg_vram_percent" label="VRAM平均" width="110">
              <template #default="{ row }">{{ row.avg_vram_percent }}%</template>
            </el-table-column>
            <el-table-column prop="warning_count" label="预警数" width="90">
              <template #default="{ row }">
                <el-tag :type="row.warning_count > 0 ? 'danger' : 'success'" size="small">
                  {{ row.warning_count }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click.stop="viewDeviceReport(row)">
                  查看详情
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 设备报告详情 -->
        <template v-if="deviceDetail">
          <!-- 设备概览 -->
          <el-row :gutter="16" style="margin-top: 16px;">
            <el-col :span="24">
              <el-card shadow="never" class="section-card">
                <template #header>
                  <div class="section-header">
                    <h3>设备概览</h3>
                    <div>
                      <el-tag type="info" size="small" style="margin-right: 8px;">报告ID: {{ deviceDetail.id }}</el-tag>
                      <el-tag :type="getHealthScoreType(deviceDetail.health_score)" size="small">
                        健康评分: {{ deviceDetail.health_score }}
                      </el-tag>
                    </div>
                  </div>
                </template>
                <el-descriptions :column="4" border size="small">
                  <el-descriptions-item label="报告周期">{{ deviceDetail.period }}</el-descriptions-item>
                  <el-descriptions-item label="GPU型号">{{ deviceDetail.gpu_model }}</el-descriptions-item>
                  <el-descriptions-item label="显存总量">{{ deviceDetail.vram_total_gb }}GB</el-descriptions-item>
                  <el-descriptions-item label="CPU核心">{{ deviceDetail.cpu_cores }}核</el-descriptions-item>
                  <el-descriptions-item label="内存总量">{{ deviceDetail.ram_total_gb }}GB</el-descriptions-item>
                  <el-descriptions-item label="监控时长">{{ deviceDetail.monitoring_hours }}h</el-descriptions-item>
                  <el-descriptions-item label="采样次数">{{ deviceDetail.sample_count }}</el-descriptions-item>
                  <el-descriptions-item label="预警总数">
                    <el-tag :type="deviceDetail.warning_count > 0 ? 'danger' : 'success'" size="small">
                      {{ deviceDetail.warning_count }}
                    </el-tag>
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
          </el-row>

          <!-- 资源使用总结 + 功率与温度 -->
          <el-row :gutter="16" style="margin-top: 16px;">
            <el-col :span="12">
              <el-card shadow="never" class="section-card">
                <template #header>资源使用总结</template>
                <div class="resource-grid">
                  <div class="resource-item">
                    <div class="resource-label">VRAM 使用</div>
                    <el-progress
                      :percentage="deviceDetail.resource_summary.avg_vram_percent"
                      :stroke-width="12"
                      :color="getProgressColor(deviceDetail.resource_summary.avg_vram_percent)"
                    />
                    <div class="resource-detail">
                      平均: {{ deviceDetail.resource_summary.avg_vram_percent }}% | 峰值: {{ deviceDetail.resource_summary.peak_vram_percent }}%
                    </div>
                  </div>
                  <div class="resource-item">
                    <div class="resource-label">GPU 使用</div>
                    <el-progress
                      :percentage="deviceDetail.resource_summary.avg_gpu_percent"
                      :stroke-width="12"
                      :color="getProgressColor(deviceDetail.resource_summary.avg_gpu_percent)"
                    />
                    <div class="resource-detail">
                      平均: {{ deviceDetail.resource_summary.avg_gpu_percent }}% | 峰值: {{ deviceDetail.resource_summary.peak_gpu_percent }}%
                    </div>
                  </div>
                  <div class="resource-item">
                    <div class="resource-label">CPU 使用</div>
                    <el-progress
                      :percentage="deviceDetail.resource_summary.avg_cpu_percent"
                      :stroke-width="12"
                      :color="getProgressColor(deviceDetail.resource_summary.avg_cpu_percent)"
                    />
                    <div class="resource-detail">
                      平均: {{ deviceDetail.resource_summary.avg_cpu_percent }}% | 峰值: {{ deviceDetail.resource_summary.peak_cpu_percent }}%
                    </div>
                  </div>
                  <div class="resource-item">
                    <div class="resource-label">内存使用</div>
                    <el-progress
                      :percentage="deviceDetail.resource_summary.avg_ram_percent"
                      :stroke-width="12"
                      :color="getProgressColor(deviceDetail.resource_summary.avg_ram_percent)"
                    />
                    <div class="resource-detail">
                      平均: {{ deviceDetail.resource_summary.avg_ram_percent }}% | 峰值: {{ deviceDetail.resource_summary.peak_ram_percent }}%
                    </div>
                  </div>
                </div>
              </el-card>
            </el-col>

            <el-col :span="12">
              <el-card shadow="never" class="section-card">
                <template #header>功率与温度</template>
                <VChart :option="powerTempChartOption" autoresize style="height: 300px;" />
                <div class="metric-list" v-if="deviceDetail.power_temp">
                  <div class="metric-item">
                    <span class="metric-label">平均功率</span>
                    <span class="metric-value">{{ deviceDetail.power_temp.avg_power_w }}W</span>
                  </div>
                  <div class="metric-item">
                    <span class="metric-label">峰值功率</span>
                    <span class="metric-value">{{ deviceDetail.power_temp.peak_power_w }}W</span>
                  </div>
                  <div class="metric-item">
                    <span class="metric-label">平均温度</span>
                    <span class="metric-value">{{ deviceDetail.power_temp.avg_temp_c }}°C</span>
                  </div>
                  <div class="metric-item">
                    <span class="metric-label">峰值温度</span>
                    <span class="metric-value">{{ deviceDetail.power_temp.peak_temp_c }}°C</span>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>

          <!-- 负载分布 + 预警统计 -->
          <el-row :gutter="16" style="margin-top: 16px;">
            <el-col :span="12">
              <el-card shadow="never" class="section-card">
                <template #header>负载分布</template>
                <VChart :option="loadDistChartOption" autoresize style="height: 280px;" />
                <div class="metric-list" v-if="deviceDetail.load_distribution">
                  <div class="metric-item" v-for="item in deviceDetail.load_distribution.details" :key="item.label">
                    <span class="metric-label">{{ item.label }}</span>
                    <span class="metric-value">{{ item.value }}</span>
                  </div>
                </div>
              </el-card>
            </el-col>

            <el-col :span="12">
              <el-card shadow="never" class="section-card">
                <template #header>预警统计</template>
                <VChart :option="warningChartOption" autoresize style="height: 280px;" />
                <el-table :data="deviceDetail.warnings" stripe size="small" style="margin-top: 12px;" v-if="deviceDetail.warnings?.length">
                  <el-table-column prop="time" label="时间" width="160" />
                  <el-table-column prop="level" label="级别" width="80">
                    <template #default="{ row }">
                      <el-tag :type="row.level === 'critical' ? 'danger' : 'warning'" size="small">
                        {{ row.level === 'critical' ? '严重' : '警告' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="metric" label="指标" width="100" />
                  <el-table-column prop="message" label="描述" min-width="150" show-overflow-tooltip />
                </el-table>
              </el-card>
            </el-col>
          </el-row>

          <!-- 优化建议 + 容量规划 -->
          <el-row :gutter="16" style="margin-top: 16px;">
            <el-col :span="12">
              <el-card shadow="never" class="section-card">
                <template #header>优化建议</template>
                <div class="suggestion-list" v-if="deviceDetail.suggestions?.length">
                  <div
                    v-for="(s, idx) in deviceDetail.suggestions"
                    :key="idx"
                    class="suggestion-item"
                    :class="`suggestion-${s.priority}`"
                  >
                    <div class="suggestion-header">
                      <el-icon :size="16">
                        <WarningFilled v-if="s.priority === 'high'" />
                        <InfoFilled v-else-if="s.priority === 'medium'" />
                        <SuccessFilled v-else />
                      </el-icon>
                      <span class="suggestion-title">{{ s.title }}</span>
                      <el-tag :type="s.priority === 'high' ? 'danger' : s.priority === 'medium' ? 'warning' : 'success'" size="small">
                        {{ s.priority === 'high' ? '高' : s.priority === 'medium' ? '中' : '低' }}
                      </el-tag>
                    </div>
                    <p class="suggestion-desc">{{ s.description }}</p>
                  </div>
                </div>
                <el-empty v-else description="暂无优化建议" :image-size="80" />
              </el-card>
            </el-col>

            <el-col :span="12">
              <el-card shadow="never" class="section-card">
                <template #header>容量规划</template>
                <div v-if="deviceDetail.capacity_plan">
                  <el-descriptions :column="1" border size="small">
                    <el-descriptions-item label="当前显存利用率">
                      {{ deviceDetail.capacity_plan.current_vram_utilization }}%
                    </el-descriptions-item>
                    <el-descriptions-item label="预计可用月数">
                      {{ deviceDetail.capacity_plan.months_until_limit }} 个月
                    </el-descriptions-item>
                    <el-descriptions-item label="建议扩展容量">
                      {{ deviceDetail.capacity_plan.recommended_vram_gb }}GB
                    </el-descriptions-item>
                    <el-descriptions-item label="并发承载能力">
                      {{ deviceDetail.capacity_plan.concurrent_capacity }} 个会话
                    </el-descriptions-item>
                  </el-descriptions>
                  <div class="capacity-note" v-if="deviceDetail.capacity_plan.note">
                    <el-icon><InfoFilled /></el-icon>
                    <span>{{ deviceDetail.capacity_plan.note }}</span>
                  </div>
                </div>
                <el-empty v-else description="暂无容量规划数据" :image-size="80" />
              </el-card>
            </el-col>
          </el-row>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, WarningFilled, InfoFilled, SuccessFilled } from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import client from '@/api/client'

use([CanvasRenderer, LineChart, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent])

// ==================== 状态 ====================
const activeTab = ref('agent')

// 智能体报告
const generatingAgent = ref(false)
const loadingAgentList = ref(false)
const agentReports = ref<any[]>([])
const agentDetail = ref<any>(null)

// 设备报告
const generatingDevice = ref(false)
const loadingDeviceList = ref(false)
const deviceReports = ref<any[]>([])
const deviceDetail = ref<any>(null)

// ==================== 工具函数 ====================
const CHART_COLORS = ['#3b82f6', '#f97316', '#10b981', '#8b5cf6', '#60a5fa', '#f472b6', '#a78bfa']
const ROLE_LABELS: Record<string, string> = { pregnant: '孕妇', nurse: '护士', doctor: '医生', admin: '管理员' }

function roleLabel(role: string) { return ROLE_LABELS[role] ?? role }

function formatTokens(n: number): string {
  if (!n && n !== 0) return '-'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function getSatisfactionType(val: number): '' | 'success' | 'warning' | 'danger' {
  if (val >= 90) return 'success'
  if (val >= 70) return 'warning'
  return 'danger'
}

function getHealthScoreType(val: number): '' | 'success' | 'warning' | 'danger' {
  if (val >= 80) return 'success'
  if (val >= 60) return 'warning'
  return 'danger'
}

function getProgressColor(pct: number): string {
  if (pct >= 90) return '#ef4444'
  if (pct >= 70) return '#f97316'
  if (pct >= 50) return '#eab308'
  return '#10b981'
}

//反馈满意率计算
const feedbackRate = computed(() => {
  const fb = agentDetail.value?.feedback_summary
  if (!fb || fb.total === 0) return 0
  return Math.round(fb.positive / fb.total * 100)
})
const feedbackRateClass = computed(() => {
  const r = feedbackRate.value
  if (r >= 80) return 'success'
  if (r >= 60) return 'warning'
  return 'danger'
})

// Top 意图 (前5)
const topIntents = computed(() => {
  const dist = agentDetail.value?.intent_analysis?.distribution || {}
  return Object.entries(dist)
    .sort((a, b) => (b[1] as number) - (a[1] as number))
    .slice(0, 5)
    .map(([intent, count]) => ({ intent, count }))
})

// ==================== 智能体报告图表 ====================

// Token 消耗按角色分解
const tokenByRoleChartOption = computed(() => {
  const byRole = agentDetail.value?.token_analysis?.by_role || {}
  const roles = Object.keys(byRole)
  return {
    color: ['#3b82f6', '#f97316', '#10b981', '#8b5cf6'],
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['输入Token', '输出Token', '总Token'], bottom: 0 },
    grid: { left: 60, right: 20, top: 20, bottom: 40 },
    xAxis: { type: 'category' as const, data: roles.map(r => roleLabel(r)) },
    yAxis: { type: 'value' as const, name: 'Token' },
    series: [
      { name: '输入Token', type: 'bar', data: roles.map(r => byRole[r]?.input || 0), itemStyle: { color: '#3b82f6' } },
      { name: '输出Token', type: 'bar', data: roles.map(r => byRole[r]?.output || 0), itemStyle: { color: '#f97316' } },
      { name: '总Token', type: 'bar', data: roles.map(r => byRole[r]?.total || 0), itemStyle: { color: '#10b981' } },
    ],
  }
})

// 意图分布饼图
const intentChartOption = computed(() => {
  const chart = agentDetail.value?.intent_analysis?.chart || []
  return {
    color: CHART_COLORS,
    tooltip: { trigger: 'item' as const },
    legend: { orient: 'vertical', right: 10, top: 20 },
    series: [
      {
        type: 'pie',
        radius: ['35%', '65%'],
        center: ['40%', '50%'],
        data: chart.map((d: any) => ({ name: d.intent, value: d.count })),
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.12)' } },
        label: { show: true, fontSize: 10 },
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
      },
    ],
  }
})

// 工具成功率图表
const toolSuccessChartOption = computed(() => {
  const rates = agentDetail.value?.tool_analysis?.success_rates || []
  const top5 = rates.slice(0, 8)
  return {
    color: ['#10b981', '#f97316', '#ef4444'],
    tooltip: { trigger: 'axis' as const },
    grid: { left: 100, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'value' as const, max: 100, name: '成功率 %' },
    yAxis: { type: 'category' as const, data: top5.map(d => d.name), inverse: true },
    series: [{
      type: 'bar',
      data: top5.map(d => ({
        value: d.success_rate,
        itemStyle: {
          color: d.success_rate >= 90 ? '#10b981' : d.success_rate >= 70 ? '#f97316' : '#ef4444',
        }
      })),
      barWidth: 16,
    }],
  }
})

const routeChartOption = computed(() => {
  const data = agentDetail.value?.route_analysis?.chart || []
  return {
    color: CHART_COLORS,
    tooltip: { trigger: 'item' as const },
    series: [
      {
        type: 'pie',
        radius: ['45%', '75%'],
        center: ['50%', '50%'],
        data: data.map((d: any) => ({ name: d.agent, value: d.count })),
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.12)' } },
        label: { show: true, fontSize: 11 },
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
      },
    ],
  }
})

// ==================== 设备报告图表 ====================
const powerTempChartOption = computed(() => {
  const history = deviceDetail.value?.power_temp?.history || []
  return {
    color: ['#ef4444', '#3b82f6'],
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['功率 (W)', '温度 (°C)'], bottom: 0 },
    grid: { left: 60, right: 60, top: 20, bottom: 40 },
    xAxis: { type: 'category' as const, data: history.map((d: any) => d.time) },
    yAxis: [
      { type: 'value' as const, name: 'W', position: 'left' as const },
      { type: 'value' as const, name: '°C', position: 'right' as const },
    ],
    series: [
      {
        name: '功率 (W)',
        type: 'line',
        data: history.map((d: any) => d.power_w),
        smooth: true,
        itemStyle: { color: '#ef4444' },
      },
      {
        name: '温度 (°C)',
        type: 'line',
        yAxisIndex: 1,
        data: history.map((d: any) => d.temp_c),
        smooth: true,
        itemStyle: { color: '#3b82f6' },
      },
    ],
  }
})

const loadDistChartOption = computed(() => {
  const data = deviceDetail.value?.load_distribution?.chart || []
  return {
    color: CHART_COLORS,
    tooltip: { trigger: 'axis' as const },
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category' as const, data: data.map((d: any) => d.time) },
    yAxis: { type: 'value' as const, max: 100, name: '%' },
    series: [
      {
        name: 'GPU 负载',
        type: 'line',
        data: data.map((d: any) => d.gpu_percent),
        smooth: true,
        areaStyle: { opacity: 0.1 },
        itemStyle: { color: '#3b82f6' },
      },
      {
        name: 'VRAM 负载',
        type: 'line',
        data: data.map((d: any) => d.vram_percent),
        smooth: true,
        areaStyle: { opacity: 0.1 },
        itemStyle: { color: '#f97316' },
      },
    ],
  }
})

const warningChartOption = computed(() => {
  const data = deviceDetail.value?.warning_stats || []
  return {
    color: ['#ef4444', '#f97316', '#eab308'],
    tooltip: { trigger: 'item' as const },
    series: [
      {
        type: 'pie',
        radius: ['45%', '75%'],
        center: ['50%', '50%'],
        data: data.map((d: any) => ({ name: d.category, value: d.count })),
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.12)' } },
        label: { show: true, fontSize: 11 },
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
      },
    ],
  }
})

// ==================== API 调用 ====================
async function fetchAgentReportList() {
  loadingAgentList.value = true
  try {
    const res = await client.get('/admin/resource/report/history', { params: { type: 'agent' } })
    agentReports.value = res.data.data || []
  } catch (err: any) {
    console.error('获取智能体报告列表失败:', err)
  } finally {
    loadingAgentList.value = false
  }
}

async function fetchDeviceReportList() {
  loadingDeviceList.value = true
  try {
    const res = await client.get('/admin/resource/report/history', { params: { type: 'device' } })
    deviceReports.value = res.data.data || []
  } catch (err: any) {
    console.error('获取设备报告列表失败:', err)
  } finally {
    loadingDeviceList.value = false
  }
}

async function generateAgentReport() {
  generatingAgent.value = true
  try {
    await client.post('/admin/resource/report/agent')
    ElMessage.success('智能体报告生成成功')
    await fetchAgentReportList()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '生成智能体报告失败')
  } finally {
    generatingAgent.value = false
  }
}

async function generateDeviceReport() {
  generatingDevice.value = true
  try {
    await client.post('/admin/resource/report/device')
    ElMessage.success('设备报告生成成功')
    await fetchDeviceReportList()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '生成设备报告失败')
  } finally {
    generatingDevice.value = false
  }
}

async function viewAgentReport(row: any) {
  try {
    const res = await client.get(`/admin/resource/report/${row.id}`)
    agentDetail.value = res.data
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '获取报告详情失败')
  }
}

async function viewDeviceReport(row: any) {
  try {
    const res = await client.get(`/admin/resource/report/${row.id}`)
    deviceDetail.value = res.data
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '获取报告详情失败')
  }
}

// ==================== 初始化 ====================
fetchAgentReportList()
fetchDeviceReportList()
</script>

<style scoped>
.operation-report {
  max-width: 1200px;
}

.report-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.section-card {
  margin-bottom: 0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-header h3 {
  margin: 0;
  font-size: 15px;
  color: #0f172a;
}

/* 指标列表 */
.metric-list {
  margin-top: 12px;
  border-top: 1px solid #f1f5f9;
  padding-top: 8px;
}

.metric-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 13px;
}

.metric-label {
  color: #64748b;
}

.metric-value {
  font-weight: 600;
  color: #0f172a;
}

/* 资源网格 */
.resource-grid {
  display: grid;
  gap: 16px;
}

.resource-item {
  padding: 8px 0;
}

.resource-label {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 8px;
}

.resource-detail {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}

/* 建议列表 */
.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.suggestion-item {
  border-radius: 8px;
  padding: 12px 14px;
  border-left: 3px solid #e2e8f0;
  background: #f8fafc;
}

.suggestion-high {
  border-left-color: #ef4444;
  background: #fef2f2;
}

.suggestion-medium {
  border-left-color: #f97316;
  background: #fff7ed;
}

.suggestion-low {
  border-left-color: #10b981;
  background: #ecfdf5;
}

.suggestion-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.suggestion-title {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.suggestion-desc {
  margin: 0;
  font-size: 13px;
  color: #64748b;
  line-height: 1.6;
}

/* 容量规划备注 */
.capacity-note {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 12px;
  padding: 10px 12px;
  background: #eff6ff;
  border-radius: 8px;
  font-size: 13px;
  color: #3b82f6;
  line-height: 1.5;
}

/* 反馈汇总 */
.feedback-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  padding: 8px 0;
}

.feedback-stat {
  text-align: center;
  padding: 16px 8px;
  background: #f8fafc;
  border-radius: 12px;
}

.feedback-stat__value {
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.2;
}

.feedback-stat__value.positive { color: #10b981; }
.feedback-stat__value.negative { color: #ef4444; }
.feedback-stat__value.success { color: #10b981; }
.feedback-stat__value.warning { color: #f97316; }
.feedback-stat__value.danger { color: #ef4444; }

.feedback-stat__label {
  font-size: 12px;
  color: #64748b;
  margin-top: 4px;
}

/* 表格行可点击 */
:deep(.el-table__row) {
  cursor: pointer;
  transition: background 0.15s;
}
</style>
