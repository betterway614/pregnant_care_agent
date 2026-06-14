<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">异常审核工作台</h1>
      <div class="page-header__actions">
        <!-- WebSocket 连接状态 -->
        <el-tag
          :type="wsConnected ? 'success' : 'danger'"
          size="small"
          effect="plain"
        >
          {{ wsConnected ? '实时连接' : '连接断开' }}
        </el-tag>

        <el-tag v-if="selectedAlert" type="danger" effect="plain" size="default">
          审核中: {{ selectedAlert.patient_name }}
        </el-tag>
        <el-switch
          v-model="showHistorical"
          active-text="历史预警"
          inactive-text="活跃预警"
          inline-prompt
          size="small"
          @change="loadAlerts"
        />
        <el-button text type="primary" :icon="Refresh" @click="loadAlerts" :loading="loading">
          刷新
        </el-button>
      </div>
    </div>

    <!-- 新预警通知 -->
    <el-alert
      v-if="pendingNewAlerts.length > 0"
      :title="`收到 ${pendingNewAlerts.length} 条新预警`"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    >
      <template #default>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>有新的预警需要处理</span>
          <el-button type="primary" size="small" @click="handleNewAlerts">
            查看新预警
          </el-button>
        </div>
      </template>
    </el-alert>

    <!-- 三栏布局 -->
    <el-row :gutter="16" style="height: calc(100vh - 180px)">
      <!-- 左侧：高危预警列表 -->
      <el-col :span="7" style="height: 100%">
        <div class="content-card" style="height: 100%; display: flex; flex-direction: column">
          <div class="content-card__header">
            <span class="content-card__title">预警列表</span>
            <div style="display: flex; align-items: center; gap: 8px">
              <el-select v-model="filterLevel" size="small" style="width: 90px" @change="loadAlerts" placeholder="全部级别">
                <el-option label="全部" value="" />
                <el-option label="红色" value="RED" />
                <el-option label="橙色" value="ORANGE" />
                <el-option label="黄色" value="YELLOW" />
              </el-select>
              <el-tag size="small">{{ groupedAlerts.length }}组 / {{ alertList.length }}条</el-tag>
            </div>
          </div>
          <div class="content-card__body" style="flex: 1; overflow-y: auto; padding: 0" v-loading="loading">
            <div
              v-for="group in groupedAlerts"
              :key="group.key"
              class="alert-list-item"
              :class="{
                'alert-list-item--active': selectedAlert?.id === group.topAlert.id,
                'alert-list-item--new': isNewAlert(group.topAlert.id)
              }"
              @click="selectAlert(group.topAlert)"
            >
              <div class="alert-list-item__header">
                <span class="alert-list-item__name">{{ group.patient_name }}</span>
                <RiskBadge :level="mapRiskLevel(group.level)" />
                <span v-if="group.count > 1" class="group-count">+{{ group.count - 1 }}</span>
              </div>
              <p class="alert-list-item__msg">{{ group.message }}</p>
              <div class="alert-list-item__meta">
                <span class="text-light">
                  {{ calcGestationalWeek(group.topAlert.gestational_age_days) }}周
                </span>
                <span class="text-light">{{ formatTime(group.topAlert.created_at) }}</span>
              </div>
              <!-- 新预警标记 -->
              <div v-if="isNewAlert(group.topAlert.id)" class="new-alert-badge">新</div>
            </div>
            <div v-if="!alertList.length && !loading" class="empty-state">
              <el-icon :size="40" color="var(--text-light)"><CircleCheck /></el-icon>
              <p>暂无待审核预警</p>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 中间：预警详情 -->
      <el-col :span="10" style="height: 100%">
        <div class="content-card" style="height: 100%; display: flex; flex-direction: column">
          <div class="content-card__header">
            <span class="content-card__title">预警详情</span>
            <el-tag v-if="selectedAlert" :type="getAlertStatusTag(selectedAlert.status)" size="small">
              {{ getAlertStatusText(selectedAlert.status) }}
            </el-tag>
          </div>
          <div
            class="content-card__body"
            style="flex: 1; overflow-y: auto"
            v-loading="detailLoading"
          >
            <template v-if="selectedAlert">
              <!-- 风险详情 -->
              <section class="detail-section">
                <h4 class="detail-section__title">风险详情</h4>
                <div class="detail-grid">
                  <div class="detail-item">
                    <span class="detail-item__label">孕妇</span>
                    <span class="detail-item__value">{{ selectedAlert.patient_name }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-item__label">风险级别</span>
                    <RiskBadge :level="mapRiskLevel(selectedAlert.level)" />
                  </div>
                  <div class="detail-item">
                    <span class="detail-item__label">预警来源</span>
                    <span class="detail-item__value">{{ triggerSourceLabel(selectedAlert.trigger_source) }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-item__label">预警时间</span>
                    <span class="detail-item__value">{{ formatTime(selectedAlert.created_at) }}</span>
                  </div>
                  <div class="detail-item" v-if="selectedAlert.gestational_age_days">
                    <span class="detail-item__label">当前孕周</span>
                    <span class="detail-item__value">{{ calcGestationalWeek(selectedAlert.gestational_age_days) }}周</span>
                  </div>
                </div>
              </section>

              <!-- 触发规则 -->
              <section class="detail-section">
                <h4 class="detail-section__title">触发规则</h4>
                <div class="rule-card">
                  <div class="rule-card__header">
                    <el-icon color="var(--danger)"><WarningFilled /></el-icon>
                    <span>{{ ruleIdLabel(selectedAlert.rule_id || '') }}</span>
                  </div>
                  <p class="rule-card__desc">规则 ID: {{ selectedAlert.rule_id || 'N/A' }}</p>
                  <p class="rule-card__desc" style="margin-top: 6px">
                    {{ ruleStandardMessage(selectedAlert.rule_id || '') || selectedAlert.message }}
                  </p>
                  <p
                    v-if="ruleStandardMessage(selectedAlert.rule_id || '') && ruleStandardMessage(selectedAlert.rule_id || '') !== selectedAlert.message"
                    class="rule-card__desc"
                    style="margin-top: 4px; color: var(--warning); font-size: 12px"
                  >
                    ⚠ 数据库记录消息与规则不一致: "{{ selectedAlert.message }}"
                  </p>
                </div>
              </section>

              <!-- 相关数据 -->
              <section class="detail-section">
                <h4 class="detail-section__title">相关数据</h4>
                <div class="data-table" v-if="hasDetails">
                  <div
                    v-for="[key, value] in detailEntries"
                    :key="key"
                    class="data-row"
                  >
                    <span class="data-row__key">{{ formatDetailKey(key) }}</span>
                    <span class="data-row__value">{{ formatDetailValue(key, value) }}</span>
                  </div>
                </div>
                <p v-else class="text-light">暂无详细数据</p>
              </section>

              <!-- 预警处理时间线 -->
              <section v-if="selectedAlert?.details?.history?.length" class="detail-section">
                <h4 class="detail-section__title">处理记录</h4>
                <el-timeline style="margin-top: 8px">
                  <el-timeline-item
                    v-for="entry in selectedAlert.details.history"
                    :key="entry.seq"
                    :timestamp="entry.timestamp"
                    :type="entry.action === 'created' ? 'primary' : entry.action.includes('escalate') ? 'danger' : entry.action.includes('downgrade') ? 'warning' : 'info'"
                  >
                    <p>
                      <el-tag size="small" :type="entry.source_role === 'system' ? '' : entry.source_role === 'doctor' ? 'success' : 'warning'">
                        {{ entry.source_role === 'system' ? '系统' : entry.source_role === 'doctor' ? '医生' : '护士' }}
                      </el-tag>
                      {{ entry.action === 'created' ? '创建预警' :
                         entry.action === 'downgrade' ? `降级为 ${entry.level}` :
                         entry.action === 'nurse_escalate' ? `升级为 ${entry.level}` :
                         entry.action === 'nurse_appeal' ? '申请复议' :
                         entry.action === 'confirm' ? '确认' :
                         entry.action === 'nurse_confirm' ? '护士确认' :
                         entry.action === 'dismiss' ? '解除' :
                         entry.action === 'nurse_dismiss' ? '护士解除' :
                         entry.action === 'auto_dismiss' ? '自动关闭' : entry.action }}
                    </p>
                    <p v-if="entry.reason" class="timeline-reason">{{ entry.reason }}</p>
                  </el-timeline-item>
                </el-timeline>
              </section>
            </template>

            <!-- 未选中提示 -->
            <div v-if="!selectedAlert" class="empty-state">
              <el-icon :size="48" color="var(--text-light)"><Select /></el-icon>
              <p style="margin-top: 12px">请从左侧列表选择一条预警进行审核</p>
            </div>
          </div>

          <!-- 底部审核操作 -->
          <div v-if="selectedAlert" class="review-actions">
            <el-button
              type="danger"
              :icon="WarningFilled"
              :loading="submitting"
              @click="confirmHighRisk"
              :disabled="!isStatusActionable(selectedAlert.status)"
            >
              确认高危
            </el-button>
            <el-button
              type="primary"
              :icon="DocumentAdd"
              :loading="orderGenerating"
              @click="generateOrderFromAlert"
              :disabled="!isStatusActionable(selectedAlert.status)"
            >
              生成医嘱
            </el-button>
            <el-button
              type="warning"
              :icon="Edit"
              :loading="submitting"
              @click="showDowngradeDialog"
              :disabled="!isStatusActionable(selectedAlert.status)"
            >
              降级
            </el-button>
            <el-button
              plain
              :icon="FolderAdd"
              @click="handleSupplement"
              :disabled="!isStatusActionable(selectedAlert.status)"
            >
              补充资料
            </el-button>
          </div>
        </div>
      </el-col>

      <!-- 右侧：孕妇辅助信息 -->
      <el-col :span="7" style="height: 100%">
        <div class="content-card" style="height: 100%; display: flex; flex-direction: column">
          <div class="content-card__header">
            <span class="content-card__title">孕妇辅助信息</span>
          </div>
          <div
            class="content-card__body"
            style="flex: 1; overflow-y: auto"
            v-loading="pregnantInfoLoading"
          >
            <template v-if="selectedAlert && pregnantFollowUps.length">
              <!-- 最近主诉 -->
              <section class="detail-section">
                <h4 class="detail-section__title">最近主诉</h4>
                <div class="chief-complaint">
                  <p>{{ latestChiefComplaint }}</p>
                  <span class="text-light">{{ latestChiefComplaintDate }}</span>
                </div>
              </section>

              <!-- 随访摘要 -->
              <section class="detail-section">
                <h4 class="detail-section__title">随访摘要</h4>
                <div
                  v-for="record in pregnantFollowUps.slice(0, 5)"
                  :key="record.id"
                  class="followup-item followup-item--clickable"
                  @click="openFollowupDetail(record)"
                >
                  <div class="followup-item__header">
                    <span class="followup-item__date">{{ formatTime(record.follow_up_date) }}</span>
                    <el-tag
                      :type="record.status === 'confirmed' ? 'success' : 'info'"
                      size="small"
                    >
                      {{ record.status === 'confirmed' ? '已确认' : '待确认' }}
                    </el-tag>
                  </div>
                  <p class="followup-item__summary" v-if="record.summary">
                    {{ record.summary }}
                  </p>
                  <div v-if="record.chief_complaint" class="followup-item__complaint">
                    <el-icon color="var(--text-light)"><ChatDotSquare /></el-icon>
                    {{ record.chief_complaint }}
                  </div>
                </div>
              </section>
            </template>

            <div v-if="!selectedAlert" class="empty-state">
              <el-icon :size="40" color="var(--text-light)"><User /></el-icon>
              <p>选择孕妇后查看</p>
            </div>

            <div v-if="selectedAlert && !pregnantFollowUps.length && !pregnantInfoLoading && !aiAnalysisResult" class="empty-state">
              <el-icon :size="40" color="var(--text-light)"><ChatDotSquare /></el-icon>
              <p>暂无随访记录</p>
            </div>

            <!-- AI分析按钮 -->
            <div v-if="selectedAlert" style="margin-bottom: 16px">
              <el-button
                type="primary"
                :icon="MagicStick"
                :loading="aiAnalyzing"
                @click="runDoctorAiAnalysis"
                style="width: 100%"
              >
                Dr.智 AI 分析
              </el-button>
            </div>

            <!-- AI分析结果 -->
            <template v-if="aiAnalysisResult">
              <!-- 推理链 -->
              <section v-if="aiAnalysisResult.reasoning_chain?.length" class="detail-section">
                <h4 class="detail-section__title">
                  <el-icon><Guide /></el-icon> 推理链
                </h4>
                <div class="chain-steps">
                  <div
                    v-for="(step, idx) in aiAnalysisResult.reasoning_chain"
                    :key="idx"
                    class="chain-step"
                  >
                    <span class="chain-step__num">{{ idx + 1 }}</span>
                    <span class="chain-step__text">{{ step }}</span>
                  </div>
                </div>
              </section>

              <!-- 建议医嘱 -->
              <section v-if="aiAnalysisResult.suggested_orders" class="detail-section">
                <h4 class="detail-section__title">建议医嘱</h4>
                <el-alert
                  type="error"
                  :closable="false"
                  show-icon
                  style="margin-bottom: 12px"
                >
                  <template #title>
                    <span style="font-weight: 700; color: #d32f2f">
                      以下为AI生成的医疗建议，不能替代医生专业判断，必须经医生审核修改并签署后方可执行
                    </span>
                  </template>
                </el-alert>
                <div class="suggested-orders">
                  {{ aiAnalysisResult.suggested_orders }}
                </div>
                <el-button
                  type="primary"
                  :icon="DocumentAdd"
                  :loading="orderGenerating"
                  @click="generateOrderFromAnalysis"
                  style="margin-top: 12px; width: 100%"
                >
                  生成正式医嘱
                </el-button>
              </section>

              <!-- 循证参考 -->
              <section v-if="aiAnalysisResult.evidence_references?.length" class="detail-section">
                <h4 class="detail-section__title">循证参考</h4>
                <ul class="evidence-list">
                  <li v-for="(ref, idx) in aiAnalysisResult.evidence_references" :key="idx">
                    {{ ref }}
                  </li>
                </ul>
              </section>
            </template>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 降级弹窗 -->
    <el-dialog
      v-model="downgradeDialogVisible"
      title="降级确认"
      width="420px"
      destroy-on-close
    >
      <div class="dialog-body">
        <p style="margin-bottom: 12px">请选择降级目标等级并填写理由：</p>
        <el-radio-group v-model="downgradeTarget" style="margin-bottom: 16px">
          <el-radio value="ORANGE">橙色预警</el-radio>
          <el-radio value="YELLOW">黄色关注</el-radio>
          <el-radio value="GREEN">正常</el-radio>
        </el-radio-group>
        <el-input
          v-model="downgradeReason"
          type="textarea"
          :rows="3"
          placeholder="请填写降级理由（必填）"
        />
      </div>
      <template #footer>
        <el-button @click="downgradeDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="!downgradeReason.trim()"
          @click="confirmDowngrade"
        >
          确认降级
        </el-button>
      </template>
    </el-dialog>

    <!-- 医嘱建议对话框 -->
    <el-dialog
      v-model="orderDialogVisible"
      title="医嘱建议"
      width="560px"
      destroy-on-close
    >
      <div v-loading="orderGenerating" class="dialog-body">
        <template v-if="generatedOrder">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 16px"
          >
            <p>以下是根据当前风险评估结果生成的医嘱建议，请审核后确认或手写修改。</p>
          </el-alert>

          <div class="order-preview">
            <div class="order-preview__header">
              <span class="order-preview__label">建议医嘱内容</span>
              <el-tag size="small">{{ generatedOrder.order_type }}</el-tag>
            </div>
            <div class="order-preview__content">
              {{ generatedOrder.content }}
            </div>
            <div class="order-preview__meta">
              <span class="text-light">来源: {{ generatedOrder.source }}</span>
            </div>
          </div>
        </template>
      </div>
      <template #footer>
        <el-button @click="orderDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="acceptOrder">
          采纳
        </el-button>
        <el-button plain :loading="submitting" @click="writeManually">
          手写医嘱
        </el-button>
      </template>
    </el-dialog>

    <!-- 补充资料对话框 -->
    <el-dialog
      v-model="supplementDialogVisible"
      title="补充资料"
      width="520px"
      destroy-on-close
    >
      <div v-if="selectedAlert" class="dialog-body">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 16px"
        >
          为 {{ selectedAlert.patient_name }} 的预警补充临床资料，辅助后续审核决策。
        </el-alert>
        <el-form label-width="90px">
          <el-form-item label="临床备注">
            <el-input
              v-model="supplementForm.clinical_notes"
              type="textarea"
              :rows="4"
              placeholder="补充临床观察、症状描述、既往病史等信息..."
              maxlength="2000"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="参考链接">
            <el-input
              v-model="supplementForm.reference_links"
              type="textarea"
              :rows="2"
              placeholder="相关文献、指南链接（每行一条）"
              maxlength="1000"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="补充数据">
            <el-input
              v-model="supplementForm.additional_data"
              type="textarea"
              :rows="3"
              placeholder="实验室检查结果、影像学描述、用药记录等..."
              maxlength="2000"
              show-word-limit
            />
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="supplementDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="doSaveSupplement">
          保存资料
        </el-button>
      </template>
    </el-dialog>

    <!-- 随访详情模态框 -->
    <el-dialog
      v-model="followupDetailVisible"
      :title="'随访记录详情 - ' + (followupDetail?.patient_name || '')"
      width="780px"
      destroy-on-close
      top="5vh"
    >
      <template v-if="followupDetail">
        <el-tabs v-model="followupTab">
          <el-tab-pane label="随访详情" name="detail">
            <div class="followup-soap" v-if="followupDoc?.snapshot">
              <!-- 基本信息 -->
              <div class="soap-info-bar">
                <span>孕周：{{ followupDoc.snapshot.gestational_week }}</span>
                <span>日期：{{ followupDoc.snapshot.follow_up_date }}</span>
                <el-tag :type="classificationTag(followupDoc.snapshot.classification)" size="small">
                  {{ classificationLabel(followupDoc.snapshot.classification) }}
                </el-tag>
              </div>

              <!-- S 主观数据 -->
              <div class="soap-section">
                <h5 class="soap-section__title soap-s">S 主观数据</h5>
                <div v-if="followupDoc.snapshot.self_reported_data" class="soap-grid">
                  <div v-for="(v, k) in followupDoc.snapshot.self_reported_data" :key="k" class="soap-item">
                    <span class="soap-item__key">{{ fieldLabel(String(k)) }}：</span>
                    <span class="soap-item__value">{{ v }}</span>
                  </div>
                </div>
                <p v-if="followupDoc.snapshot.chief_complaint" class="soap-complaint">
                  主诉：{{ followupDoc.snapshot.chief_complaint }}
                </p>
              </div>

              <!-- O 客观检查 -->
              <div class="soap-section" v-if="followupDoc.snapshot.obstetric_exam || followupDoc.snapshot.lab_results">
                <h5 class="soap-section__title soap-o">O 客观检查</h5>
                <div v-if="followupDoc.snapshot.obstetric_exam" class="soap-grid">
                  <div v-for="(v, k) in followupDoc.snapshot.obstetric_exam" :key="k" class="soap-item">
                    <span class="soap-item__key">{{ examLabel(String(k)) }}：</span>
                    <span class="soap-item__value">{{ v }}</span>
                  </div>
                </div>
                <div v-if="followupDoc.snapshot.lab_results" class="soap-grid">
                  <div v-for="(v, k) in followupDoc.snapshot.lab_results" :key="k" class="soap-item">
                    <span class="soap-item__key">{{ labLabel(String(k)) }}：</span>
                    <span class="soap-item__value">{{ v }}</span>
                  </div>
                </div>
              </div>

              <!-- A 评估 -->
              <div class="soap-section" v-if="followupDoc.snapshot.summary">
                <h5 class="soap-section__title soap-a">A 评估</h5>
                <p class="soap-text">{{ followupDoc.snapshot.summary }}</p>
              </div>

              <!-- P 计划 -->
              <div class="soap-section" v-if="followupDoc.snapshot.guidance_tags?.length">
                <h5 class="soap-section__title soap-p">P 计划</h5>
                <div v-for="(g, idx) in followupDoc.snapshot.guidance_tags" :key="idx" class="soap-guidance">
                  <el-tag size="small" effect="plain">{{ g.tag }}</el-tag>
                  <span>{{ g.content }}</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <p>暂无详细随访数据</p>
            </div>
          </el-tab-pane>

          <el-tab-pane label="护士签名" name="signature">
            <div class="signature-tab">
              <template v-if="followupDoc?.signature?.image">
                <div class="signature-tab__img-wrap">
                  <img :src="followupDoc.signature.image" class="signature-tab__img" />
                </div>
                <div class="signature-tab__info">
                  <p>签名人：{{ followupDoc.signature.signer || '护士' }}</p>
                  <p>签名时间：{{ followupDoc.signature.signed_at || '未知' }}</p>
                </div>
              </template>
              <div v-else class="empty-state">
                <el-icon :size="36" color="var(--text-light)"><Edit /></el-icon>
                <p>该随访记录暂无护士签名</p>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="历史数据" name="trends">
            <PatientBioInfoPanel
              v-if="selectedAlert?.pregnant_id"
              :pregnant-id="selectedAlert.pregnant_id"
              :show-trends="true"
              :show-lab="true"
              role="doctor"
            />
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Refresh, WarningFilled, Edit, FolderAdd,
  Select, ChatDotSquare, User, CircleCheck,
  MagicStick, Guide, DocumentAdd,
} from '@element-plus/icons-vue'
import { alertApi, orderApi, followUpApi, doctorAiApi } from '@/api/endpoints'
import { getWebSocketClient } from '@/utils/websocket'
import { useAppStore } from '@/stores/app'
import type { Alert, MedicalOrder, FollowUpRecord } from '@/types'
import RiskBadge from '@/components/common/RiskBadge.vue'
import PatientBioInfoPanel from '@/components/common/PatientBioInfoPanel.vue'
import { ElNotification } from 'element-plus'
import { fieldLabel, examLabel, labLabel, triggerSourceLabel, ruleIdLabel } from '@/utils/labelMaps'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

// 数据状态
const loading = ref(false)
const showHistorical = ref(false)
const filterLevel = ref('')
const detailLoading = ref(false)
const pregnantInfoLoading = ref(false)
const submitting = ref(false)
const alertList = ref<Alert[]>([])
const selectedAlert = ref<Alert | null>(null)
const pregnantFollowUps = ref<FollowUpRecord[]>([])

// WebSocket 相关状态
const wsConnected = ref(false)
const pendingNewAlerts = ref<Alert[]>([])
const newAlertIds = ref<Record<string, boolean>>({})
const wsClient = ref<ReturnType<typeof getWebSocketClient> | null>(null)

// 降级状态
const downgradeDialogVisible = ref(false)
const downgradeTarget = ref('ORANGE')
const downgradeReason = ref('')

// 医嘱状态
const orderDialogVisible = ref(false)
const orderGenerating = ref(false)
const generatedOrder = ref<MedicalOrder | null>(null)

// AI分析状态
const aiAnalyzing = ref(false)
const aiAnalysisResult = ref<any>(null)

// 补充资料状态
const supplementDialogVisible = ref(false)
const supplementForm = ref({
  clinical_notes: '',
  reference_links: '',
  additional_data: '',
})

// 随访详情模态框
const followupDetailVisible = ref(false)
const followupDetail = ref<FollowUpRecord | null>(null)
const followupDoc = ref<any>(null)
const followupTab = ref('detail')

/** 风险级别映射 */
function mapRiskLevel(level: string): string {
  const map: Record<string, string> = {
    RED: 'RED',
    ORANGE: 'ORANGE',
    YELLOW: 'YELLOW',
    GREEN: 'GREEN',
    high: 'RED',
    medium: 'ORANGE',
    low: 'YELLOW',
    critical: 'RED',
  }
  return map[level] || 'YELLOW'
}

/** 计算孕周 */
function calcGestationalWeek(days?: number): number {
  if (!days) return 0
  return Math.floor(days / 7)
}

/** 时间格式化 */
function formatTime(t?: string): string {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 预警状态标签 */
function getAlertStatusTag(status: string): 'danger' | 'warning' | 'success' | 'info' {
  const map: Record<string, 'danger' | 'warning' | 'success' | 'info'> = {
    pending: 'danger',
    escalated: 'danger',
    confirmed: 'warning',
    dismissed: 'info',
    auto_dismissed: 'info',
  }
  return map[status.toLowerCase()] || 'info'
}

/** 预警状态文本 */
function getAlertStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: '待审核',
    escalated: '已升级(紧急)',
    confirmed: '已确认',
    dismissed: '已忽略',
    auto_dismissed: '已自动关闭',
  }
  return map[status.toLowerCase()] || status
}

/** 判断预警状态是否可操作 */
function isStatusActionable(status: string): boolean {
  // confirmed 也被视为可操作：允许医生在确认后仍能开医嘱或补充资料
  return ['pending', 'escalated', 'confirmed'].includes(status.toLowerCase())
}

/** 需要在"相关数据"区域隐藏的字段（已有独立展示区域或为内部字段） */
const DETAIL_HIDDEN_KEYS = new Set([
  'history',        // 处理记录 — 已有独立时间线展示
  'source_role',    // 内部字段
  'created_at',     // 与预警创建时间重复
  'analyzed_at',    // 内部时间戳
  'llm_analysis',   // 复杂嵌套对象，专用 AI 分析按钮展示
  'ai_workflow',    // 复杂嵌套对象，专用 AI 分析按钮展示
])

/** 是否有详情数据 */
const hasDetails = computed(() => {
  if (!selectedAlert.value?.details) return false
  return Object.keys(selectedAlert.value.details).some((k) => !DETAIL_HIDDEN_KEYS.has(k))
})

/** 过滤后的详情条目（排除已有独立展示区域的字段） */
const detailEntries = computed(() => {
  if (!selectedAlert.value?.details) return []
  return Object.entries(selectedAlert.value.details).filter(([key]) => !DETAIL_HIDDEN_KEYS.has(key))
})

/** 按 pregnant_id + domain 分组的预警列表（折叠同患者同域预警） */
const groupedAlerts = computed(() => {
  const groups = new Map<string, any[]>()
  for (const alert of alertList.value) {
    const key = `${alert.pregnant_id}-${(alert as any).domain || 'unknown'}`
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key)!.push(alert)
  }
  return Array.from(groups.entries()).map(([key, alerts]) => {
    const sorted = [...alerts].sort((a, b) => {
      const order: Record<string, number> = { RED: 3, ORANGE: 2, YELLOW: 1 }
      return (order[b.level] || 0) - (order[a.level] || 0)
    })
    return {
      key,
      pregnant_id: sorted[0].pregnant_id,
      patient_name: sorted[0].patient_name,
      level: sorted[0].level,
      message: sorted[0].message,
      count: alerts.length,
      children: alerts,
      topAlert: sorted[0],
    }
  })
})

/** 格式化详情键 */
function formatDetailKey(key: string): string {
  const map: Record<string, string> = {
    // 风险相关
    case_id: '病例编号',
    risk_level: '风险等级',
    risk_assessment: '风险评估',
    risk_score: '风险评分',
    deviation: '偏差',
    // 指标相关
    value: '测量值',
    threshold: '阈值',
    metric_code: '指标代码',
    unit: '单位',
    trend: '趋势',
    // 时间与孕周
    created_at: '创建时间',
    analyzed_at: '分析时间',
    gestational_weeks: '孕周',
    // 置信区间
    confidence_interval: '置信区间',
    // 规则与处理
    action: '处理动作',
    triggered_rules: '触发规则列表',
    source_role: '来源角色',
    history: '处理记录',
    // AI 分析
    llm_analysis: 'AI分析结果',
    ai_workflow: 'AI分析工作流',
    // FGR 相关
    fgr_probability: 'FGR概率',
    predicted_label: '预测标签',
    model_confidence: '模型置信度',
    explanation: '分析解释',
    processing_time: '处理耗时(秒)',
    hardware: '运行硬件',
    fold_details: '交叉验证详情',
    // 预警动作映射
    ALERT_NURSE: '通知护士',
    ALERT_NURSE_AND_DOCTOR: '通知护士和医生',
    ALERT_DOCTOR: '通知医生',
    NOTE_NURSE: '记录备注',
    // 通用
    note: '备注',
    reason: '原因',
    result: '结果',
    summary: '摘要',
  }
  return map[key] || key
}

/** 格式化详情值 */
function formatDetailValue(key: string, value: any): string {
  // 1. 处理 null/undefined
  if (value === null || value === undefined) return '无'

  // 2. 处理对象类型
  if (typeof value === 'object') {
    // 2a. 置信区间特殊处理
    if (value.lowerBound !== undefined && value.upperBound !== undefined) {
      return `${(value.lowerBound * 100).toFixed(1)}% ~ ${(value.upperBound * 100).toFixed(1)}%`
    }

    // 2b. 数组类型 — 根据 key 做友好展示
    if (Array.isArray(value)) {
      if (!value.length) return '无'
      // 触发规则列表 — 用中文规则名展示
      if (key === 'triggered_rules') {
        return value.map((id: string) => ruleIdLabel(id)).join('、')
      }
      // 其他数组 — 检查是否全是简单值
      if (value.every((v: any) => typeof v !== 'object' || v === null)) {
        return value.map((v: any) => String(v)).join('、')
      }
      // 复杂对象数组 — 显示条数
      return `共 ${value.length} 条记录`
    }

    // 2c. 普通对象 — 尝试提取可读摘要
    // 如果有 summary/result/explanation 等常见字段，提取展示
    const summaryKeys = ['summary', 'result', 'explanation', 'risk_assessment', 'message', 'content', 'text']
    for (const sk of summaryKeys) {
      if (value[sk] && typeof value[sk] === 'string') {
        const s = value[sk]
        return s.length > 80 ? s.slice(0, 80) + '…' : s
      }
    }
    // 无法提取摘要 — 显示对象键数
    const keys = Object.keys(value)
    if (keys.length === 0) return '无'
    return `[复杂数据，包含 ${keys.length} 个字段]`
  }

  // 3. 处理基本类型
  const str = String(value)
  const actionMap: Record<string, string> = {
    ALERT_NURSE: '通知护士',
    ALERT_NURSE_AND_DOCTOR: '通知护士和医生',
    ALERT_DOCTOR: '通知医生',
    NOTE_NURSE: '记录备注',
  }
  const riskLevelMap: Record<string, string> = {
    critical: '极高风险',
    high: '高风险',
    medium: '中风险',
    low: '低风险',
  }
  return actionMap[str] || riskLevelMap[str] || str
}

/** 最近主诉 */
const latestChiefComplaint = computed(() => {
  const records = pregnantFollowUps.value
  if (!records.length) return '暂无'
  return records[0].chief_complaint || '无主诉'
})

const latestChiefComplaintDate = computed(() => {
  const records = pregnantFollowUps.value
  if (!records.length) return ''
  return formatTime(records[0].follow_up_date)
})

/** 选择预警 */
async function selectAlert(alert: Alert) {
  selectedAlert.value = alert
  detailLoading.value = false
  pregnantInfoLoading.value = true
  pregnantFollowUps.value = []
  aiAnalysisResult.value = null

  // 更新URL
  router.replace(`/doctor/review/${alert.id}`)

  // 加载孕妇随访信息
  try {
    const res = await followUpApi.list({ pregnant_id: alert.pregnant_id })
    pregnantFollowUps.value = (res.data || []).sort(
      (a, b) => new Date(b.follow_up_date || 0).getTime() - new Date(a.follow_up_date || 0).getTime()
    )
  } catch (err) {
    console.error('加载孕妇随访信息失败:', err)
  } finally {
    pregnantInfoLoading.value = false
  }
}

/** 加载预警列表 */
async function loadAlerts() {
  loading.value = true
  try {
    const params: any = {}
    if (filterLevel.value) params.level = filterLevel.value
    if (!showHistorical.value) {
      params.status = 'pending,escalated'
    }
    const res = await alertApi.list(params)
    alertList.value = res.data || []
  } catch (err) {
    console.error('加载预警列表失败:', err)
  } finally {
    loading.value = false
  }
}

/** 确认高危 */
async function confirmHighRisk() {
  if (!selectedAlert.value) return
  const alert = selectedAlert.value
  submitting.value = true
  try {
    await alertApi.review(alert.id, 'confirm')
    // 从列表中移除
    alertList.value = alertList.value.filter((a) => a.id !== alert.id)
    // 自动生成医嘱并跳转到签名页
    try {
      const res = await orderApi.generate({
        pregnant_id: alert.pregnant_id,
        alert_id: alert.id,
        risk_level: alert.level,
        gestational_weeks: calcGestationalWeek(alert.gestational_age_days),
      })
      router.push({ name: 'OrderSign', params: { orderId: res.data.id } })
    } catch (orderErr) {
      console.error('生成医嘱失败:', orderErr)
      ElNotification.warning('高危已确认，但医嘱生成失败，请手动创建医嘱')
    }
  } catch (err) {
    console.error('确认高危失败:', err)
  } finally {
    submitting.value = false
  }
}

/** 从预警直接生成医嘱（不修改预警状态） */
async function generateOrderFromAlert() {
  if (!selectedAlert.value) return
  const alert = selectedAlert.value
  orderGenerating.value = true
  try {
    const res = await orderApi.generate({
      pregnant_id: alert.pregnant_id,
      alert_id: alert.id,
      risk_level: alert.level,
      gestational_weeks: calcGestationalWeek(alert.gestational_age_days),
    })
    router.push({ name: 'OrderSign', params: { orderId: res.data.id } })
  } catch (err) {
    console.error('生成医嘱失败:', err)
    ElNotification.error('生成医嘱失败，请重试')
  } finally {
    orderGenerating.value = false
  }
}

/** 显示降级弹窗 */
function showDowngradeDialog() {
  downgradeTarget.value = 'ORANGE'
  downgradeReason.value = ''
  downgradeDialogVisible.value = true
}

/** 确认降级 */
async function confirmDowngrade() {
  if (!selectedAlert.value || !downgradeReason.value.trim()) return
  submitting.value = true
  try {
    await alertApi.review(
      selectedAlert.value.id,
      'downgrade',
      downgradeReason.value,
      downgradeTarget.value
    )
    if (downgradeTarget.value === 'GREEN') {
      // GREEN 降级关闭：从列表移除
      alertList.value = alertList.value.filter((a) => a.id !== selectedAlert.value!.id)
    } else {
      // ORANGE/YELLOW 降级分流：更新列表中等级显示
      selectedAlert.value.level = downgradeTarget.value
      selectedAlert.value.status = 'pending'
    }
    downgradeDialogVisible.value = false
    if (!alertList.value.length) selectedAlert.value = null
  } catch (err) {
    console.error('降级失败:', err)
  } finally {
    submitting.value = false
  }
}

/** 补充资料 */
function handleSupplement() {
  supplementForm.value = { clinical_notes: '', reference_links: '', additional_data: '' }
  supplementDialogVisible.value = true
}

/** 保存补充资料 */
async function doSaveSupplement() {
  if (!selectedAlert.value) return
  submitting.value = true
  try {
    const reason = [
      supplementForm.value.clinical_notes ? `临床备注：${supplementForm.value.clinical_notes}` : '',
      supplementForm.value.reference_links ? `参考链接：${supplementForm.value.reference_links}` : '',
      supplementForm.value.additional_data ? `补充数据：${supplementForm.value.additional_data}` : '',
    ].filter(Boolean).join('\n')
    await alertApi.review(selectedAlert.value.id, 'supplement', reason)
    supplementDialogVisible.value = false
  } catch (err) {
    console.error('保存补充资料失败:', err)
  } finally {
    submitting.value = false
  }
}

/** 生成医嘱建议 */
async function generateOrderSuggestion() {
  if (!selectedAlert.value) return
  orderGenerating.value = true
  orderDialogVisible.value = true
  generatedOrder.value = null
  try {
    const res = await orderApi.generate({
      pregnant_id: selectedAlert.value.pregnant_id,
      alert_id: selectedAlert.value.id,
      risk_level: selectedAlert.value.level,
      gestational_weeks: calcGestationalWeek(selectedAlert.value.gestational_age_days),
    })
    generatedOrder.value = res.data
  } catch (err) {
    console.error('生成医嘱建议失败:', err)
  } finally {
    orderGenerating.value = false
  }
}

/** 采纳医嘱 */
async function acceptOrder() {
  if (!generatedOrder.value) return
  submitting.value = true
  try {
    await orderApi.update(generatedOrder.value.id, { status: 'draft' })
    orderDialogVisible.value = false
    selectedAlert.value = null
  } catch (err) {
    console.error('采纳医嘱失败:', err)
  } finally {
    submitting.value = false
  }
}

/** 从AI分析结果生成正式医嘱 */
async function generateOrderFromAnalysis() {
  if (!selectedAlert.value || !aiAnalysisResult.value?.suggested_orders) return
  orderGenerating.value = true
  try {
    const res = await orderApi.generate({
      pregnant_id: selectedAlert.value.pregnant_id,
      alert_id: selectedAlert.value.id,
      risk_level: selectedAlert.value.level,
      gestational_weeks: calcGestationalWeek(selectedAlert.value.gestational_age_days),
    })
    // 跳转到医嘱签名页
    router.push({ name: 'OrderSign', params: { orderId: res.data.id } })
  } catch (err) {
    console.error('生成医嘱失败:', err)
  } finally {
    orderGenerating.value = false
  }
}

/** 手写医嘱 */
function writeManually() {
  orderDialogVisible.value = false
  // 跳转到医嘱管理页面
  router.push('/doctor/orders')
}

/** 打开随访详情模态框 */
async function openFollowupDetail(record: FollowUpRecord) {
  followupDetail.value = record
  followupDetailVisible.value = true
  followupTab.value = 'detail'
  followupDoc.value = null

  // 加载随访文档（含签名）
  try {
    const res = await followUpApi.getDocument(record.id)
    followupDoc.value = res.data
  } catch (err) {
    console.error('加载随访文档失败:', err)
  }
  // 历史数据由 PatientBioInfoPanel 组件自行加载
}

/** 随访分类标签颜色 */
function classificationTag(classification: string): 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    normal: 'success', abnormal: 'warning', critical: 'danger',
  }
  return map[classification] || 'info'
}

/** 随访分类标签文本 */
function classificationLabel(classification: string): string {
  const map: Record<string, string> = { normal: '正常', abnormal: '异常', critical: '高危' }
  return map[classification] || classification
}

/** 触发AI分析 */
async function runDoctorAiAnalysis() {
  if (!selectedAlert.value) return
  aiAnalyzing.value = true
  aiAnalysisResult.value = null
  try {
    const res = await doctorAiApi.analyze(selectedAlert.value.pregnant_id)
    aiAnalysisResult.value = res.data
  } catch (err) {
    console.error('AI分析失败:', err)
  } finally {
    aiAnalyzing.value = false
  }
}

/** 规则ID对应的标准消息（与后端规则引擎保持一致） */
function ruleStandardMessage(ruleId: string): string {
  const map: Record<string, string> = {
    RULE_BP_HIGH: '血压异常升高（≥140/90mmHg）',
    RULE_BP_HIGH_ORANGE: '血压偏高（≥135/85mmHg），需要关注',
    RULE_BP_LOW: '血压偏低，需关注',
    RULE_LATE_PREGNANCY_BP: '孕晚期血压偏高，子痫前期风险',
    RULE_BS_POSTPRANDIAL_HIGH: '餐后血糖异常（>7.0mmol/L）',
    RULE_BS_FASTING_HIGH: '空腹血糖偏高（>5.3mmol/L），建议复查',
    RULE_WEIGHT_GAIN_FAST: '体重周增长过快（>2kg/周）',
    RULE_WEIGHT_GAIN_SLOW: '体重增长过慢，需关注营养摄入',
    RULE_FETAL_DROP: '胎动显著减少（低于平均50%）',
    RULE_FETAL_VERY_LOW: '胎动极少（<3次/小时），请立即就医',
    RULE_EMOTION_CRITICAL: '近7日情绪评分持续偏低（平均≤1.5分），建议心理干预',
    RULE_EMOTION_HIGH: '近7日情绪评分偏低（平均≤2.0分），需关注心理状态',
    RULE_SLEEP_SHORT: '睡眠不足5小时，建议改善睡眠',
    FGR_CRITICAL_RISK: 'FGR评估结果: 极高风险',
    FGR_HIGH_RISK: 'FGR评估结果: 高风险',
    FGR_MEDIUM_RISK: 'FGR评估结果: 中风险',
    EPDS_HIGH_RISK: 'EPDS心理健康筛查高风险，建议心理干预',
    NURSE_AI_ALERT: '护士AI分析预警',
  }
  return map[ruleId] || ''
}

/** WebSocket 预警回调 */
const handleNewAlert = (alert: Alert) => {
  console.log('审核工作台收到新预警:', alert)

  // 添加到待处理列表
  pendingNewAlerts.value.push(alert)
  newAlertIds.value[alert.id] = true

  // 添加到预警列表顶部
  alertList.value.unshift(alert)

  // 显示通知
  ElNotification({
    title: '新预警通知',
    message: `${alert.patient_name}: ${alert.message}`,
    type: getAlertType(alert.level),
    duration: 5000,
  })
}

/** WebSocket 预警状态变更回调（护士操作后实时更新） */
const handleAlertStatusChange = (alert: any) => {
  console.log('审核工作台收到预警状态变更:', alert)
  // 更新列表中对应预警
  const idx = alertList.value.findIndex(a => a.id === alert.id)
  if (idx >= 0) {
    alertList.value[idx] = { ...alertList.value[idx], ...alert }
  }
  // 如果当前选中预警被更新，同步更新选中项
  if (selectedAlert.value?.id === alert.id) {
    selectedAlert.value = { ...selectedAlert.value, ...alert }
  }
}

/** WebSocket 连接状态回调 */
const handleStateChange = (state: string) => {
  wsConnected.value = state === 'OPEN'
}

/**
 * 初始化 WebSocket
 */
function initWebSocket() {
  const doctorId = appStore.currentUserId || 'doctor'
  wsClient.value = getWebSocketClient(doctorId)

  // 注册预警回调
  wsClient.value.onAlert(handleNewAlert)
  wsClient.value.onAlertStatusChange(handleAlertStatusChange)

  // 注册连接状态回调
  wsClient.value.onStateChange(handleStateChange)

  // 连接 WebSocket
  wsClient.value.connect()
}

/**
 * 判断是否是新预警
 */
function isNewAlert(alertId: string): boolean {
  return !!newAlertIds.value[alertId]
}

/**
 * 处理新预警
 */
function handleNewAlerts() {
  // 选中第一个新预警
  if (pendingNewAlerts.value.length > 0) {
    selectAlert(pendingNewAlerts.value[0])
    // 清空待处理列表
    pendingNewAlerts.value = []
    // 清除新预警标记
    newAlertIds.value = {}
  }
}

/**
 * 获取预警类型
 */
function getAlertType(level: string): 'success' | 'warning' | 'info' | 'error' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'error'> = {
    RED: 'error',
    ORANGE: 'warning',
    YELLOW: 'info',
  }
  return map[level] || 'info'
}

// 根据路由参数选中预警
onMounted(async () => {
  await loadAlerts()
  initWebSocket()

  // 根据路由参数选中预警
  const alertId = route.params.alertId as string
  if (alertId) {
    const found = alertList.value.find((a) => a.id === alertId)
    if (found) {
      await selectAlert(found)
    }
  }
})

onUnmounted(() => {
  // 清理 WebSocket 连接
  if (wsClient.value) {
    wsClient.value.offAlert(handleNewAlert)
    wsClient.value.offAlertStatusChange(handleAlertStatusChange)
    wsClient.value.offStateChange(handleStateChange)
    wsClient.value.disconnect()
  }
})
</script>

<style scoped>
.page-header__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 预警列表项 */
.alert-list-item {
  padding: 16px 18px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: var(--transition);
  position: relative;
}

.alert-list-item:hover {
  background: rgba(232, 245, 233, 0.25);
}

.alert-list-item--active {
  background: rgba(232, 245, 233, 0.35);
  border-left: 3px solid var(--primary);
  box-shadow: inset 0 0 0 1px rgba(46, 125, 50, 0.08);
}

/* 新预警样式 */
.alert-list-item--new {
  border-left: 3px solid var(--warning);
  background: rgba(255, 243, 224, 0.5);
}

.new-alert-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: var(--warning);
  color: white;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--radius-xs);
  font-weight: 700;
  box-shadow: 0 2px 6px rgba(245, 124, 0, 0.3);
}

.alert-list-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.alert-list-item__name {
  font-weight: 700;
  font-size: 14px;
}

.alert-list-item__msg {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 8px;
}

.alert-list-item__meta {
  display: flex;
  justify-content: space-between;
}

/* 详情区块 */
.detail-section {
  margin-bottom: 24px;
}

.detail-section__title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 6px;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.detail-item__label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.detail-item__value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

/* 规则卡片 */
.rule-card {
  background: rgba(211, 47, 47, 0.06);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius);
  padding: 16px;
  border: 1px solid rgba(211, 47, 47, 0.12);
}

.rule-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 10px;
  color: var(--danger);
}

.rule-card__desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

/* 数据表格 */
.data-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.data-row {
  display: flex;
  justify-content: space-between;
  padding: 10px 12px;
  background: rgba(241, 245, 249, 0.6);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.data-row:hover {
  background: rgba(232, 245, 233, 0.3);
}

.data-row__key {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 500;
}

.data-row__value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: 'SF Mono', 'Fira Code', monospace;
}

/* 底部审核操作栏 */
.review-actions {
  padding: 16px 20px;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 10px;
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

/* 主诉 */
.chief-complaint {
  background: rgba(241, 245, 249, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius);
  padding: 16px;
  border: 1px solid var(--border);
}

.chief-complaint p {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.7;
  margin-bottom: 8px;
}

/* 随访项 */
.followup-item {
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
  transition: background var(--transition-fast);
}

.followup-item:last-child {
  border-bottom: none;
}

.followup-item:hover {
  background: rgba(232, 245, 233, 0.15);
  border-radius: var(--radius-xs);
  margin: 0 -4px;
  padding-left: 4px;
  padding-right: 4px;
}

.followup-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.followup-item__date {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.followup-item__summary {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 8px;
}

.followup-item__complaint {
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 医嘱预览 */
.order-preview {
  background: rgba(241, 245, 249, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius);
  padding: 18px;
  border: 1px solid var(--border);
}

.order-preview__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.order-preview__label {
  font-weight: 700;
  font-size: 14px;
}

.order-preview__content {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.8;
  padding: 14px;
  background: var(--glass-bg);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius-sm);
  margin-bottom: 12px;
  border: 1px solid var(--glass-border);
}

.order-preview__meta {
  font-size: 12px;
}

.text-light {
  font-size: 12px;
  color: var(--text-muted);
}

.empty-state p {
  color: var(--text-muted);
  font-size: 14px;
  font-weight: 500;
}

/* 分组计数 */
.group-count {
  background: rgba(99, 102, 241, 0.12);
  color: #6366f1;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  font-weight: 700;
  margin-left: 4px;
}

/* 时间线理由 */
.timeline-reason {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.5;
}

.dialog-body {
  padding: 8px 0;
}

/* 推理链 */
.chain-steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chain-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.chain-step__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  min-width: 24px;
  border-radius: 50%;
  background: var(--primary-gradient);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(46, 125, 50, 0.25);
}

/* 建议医嘱 */
.suggested-orders {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
  background: rgba(241, 245, 249, 0.6);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: var(--radius);
  padding: 14px;
  white-space: pre-wrap;
  border: 1px solid var(--border);
}

/* 循证参考 */
.evidence-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.8;
}

/* ====== 随访详情模态框 ====== */

.followup-item--clickable {
  cursor: pointer;
}

.followup-item--clickable:hover {
  background: rgba(232, 245, 233, 0.2);
  border-radius: var(--radius-xs);
}

.soap-info-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 14px;
  background: #f8f9fa;
  border-radius: var(--radius-sm);
  margin-bottom: 16px;
  font-size: 13px;
}

.soap-section {
  margin-bottom: 16px;
  padding: 12px 14px;
  background: var(--glass-bg);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}

.soap-section__title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 2px solid;
}

.soap-s { border-color: #6366f1; color: #6366f1; }
.soap-o { border-color: #22c55e; color: #22c55e; }
.soap-a { border-color: #f59e0b; color: #f59e0b; }
.soap-p { border-color: #8b5cf6; color: #8b5cf6; }

.soap-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.soap-item {
  display: flex;
  gap: 4px;
  font-size: 13px;
}

.soap-item__key {
  color: var(--text-muted);
  min-width: 80px;
}

.soap-item__value {
  color: var(--text-primary);
  font-weight: 600;
}

.soap-complaint {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.soap-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
  margin: 0;
}

.soap-guidance {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  color: var(--text-secondary);
}

/* 签名 Tab */
.signature-tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px 0;
}

.signature-tab__img-wrap {
  border: 1px dashed #ccc;
  border-radius: 8px;
  padding: 8px;
  background: #fff;
}

.signature-tab__img {
  max-width: 300px;
  max-height: 100px;
}

.signature-tab__info {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
}

.signature-tab__info p {
  margin: 4px 0;
}

</style>
