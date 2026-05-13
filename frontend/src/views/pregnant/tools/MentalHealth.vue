<template>
  <div class="page-container">
    <div class="sub-page-header">
      <el-page-header @back="$router.back()">
        <template #content>心理筛查</template>
      </el-page-header>
    </div>

    <div class="patient-info-card">
      <div class="patient-info-card__title">
        <span class="dot" style="background: #7E57C2"></span>
        心理健康筛查
      </div>
      <p class="info-card__text" style="margin-bottom: 12px">
        爱丁堡产后抑郁量表（EPDS）是国际通用的心理健康筛查工具，帮助您了解近期的情绪状态。
      </p>
      <el-button v-if="!showEpds" type="primary" @click="startEpds" style="width: 100%">
        开始心理健康评估
      </el-button>

      <!-- EPDS 问卷 -->
      <div v-if="showEpds" class="epds-form">
        <el-progress
          :percentage="Math.round((epdsCurrentQ / epdsQuestions.length) * 100)"
          :stroke-width="8"
          style="margin-bottom: 16px"
        />
        <div v-if="epdsCurrentQ < epdsQuestions.length" class="epds-question">
          <p class="epds-question__text">
            {{ epdsCurrentQ + 1 }}. {{ epdsQuestions[epdsCurrentQ]?.text }}
          </p>
          <div class="epds-options">
            <button
              v-for="(opt, idx) in (epdsQuestions[epdsCurrentQ]?.options || [])"
              :key="idx"
              class="epds-option"
              :class="{ 'epds-option--selected': epdsAnswers[epdsQuestions[epdsCurrentQ]?.id] === idx }"
              @click="selectEpdsOption(epdsQuestions[epdsCurrentQ]?.id, idx)"
            >
              {{ opt }}
            </button>
          </div>
        </div>

        <div v-if="epdsResult" class="epds-result">
          <div class="epds-result__score">
            总分：<strong>{{ epdsResult.total_score }}</strong>/30
          </div>
          <el-tag
            :type="epdsResult.risk_level === 'low' ? 'success' : epdsResult.risk_level === 'moderate' ? 'warning' : 'danger'"
            size="large"
          >
            {{ epdsResult.risk_description }}
          </el-tag>
          <div class="epds-result__recommendations">
            <p v-for="(rec, idx) in epdsResult.recommendations" :key="idx" class="epds-rec-item">
              {{ rec }}
            </p>
          </div>
          <el-button @click="resetEpds" style="margin-top: 12px">重新评估</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { mentalHealthApi } from '@/api/endpoints'
import { ElMessage } from 'element-plus'

const showEpds = ref(false)
const epdsQuestions = ref<Array<{ id: number; text: string; options: string[] }>>([])
const epdsCurrentQ = ref(0)
const epdsAnswers = ref<Record<number, number>>({})
const epdsResult = ref<{ total_score: number; risk_level: string; risk_description: string; recommendations: string[] } | null>(null)

async function startEpds() {
  try {
    const res = await mentalHealthApi.getQuestions()
    epdsQuestions.value = res.data.questions
    epdsCurrentQ.value = 0
    epdsAnswers.value = {}
    epdsResult.value = null
    showEpds.value = true
  } catch { ElMessage.error('加载问卷失败') }
}

function selectEpdsOption(questionId: number, optionIdx: number) {
  epdsAnswers.value[questionId] = optionIdx
  setTimeout(() => {
    if (epdsCurrentQ.value < epdsQuestions.value.length - 1) epdsCurrentQ.value++
    else submitEpds()
  }, 300)
}

async function submitEpds() {
  try {
    const pregnantId = localStorage.getItem('currentPregnantId') || ''
    const res = await mentalHealthApi.submit({ pregnant_id: pregnantId, answers: epdsAnswers.value })
    epdsResult.value = res.data
  } catch { ElMessage.error('提交失败，请重试') }
}

function resetEpds() {
  showEpds.value = false; epdsCurrentQ.value = 0; epdsAnswers.value = {}; epdsResult.value = null
}
</script>

<style scoped>
.page-container { overflow-y: auto; -webkit-overflow-scrolling: touch; height: 100%; box-sizing: border-box; padding-bottom: 24px; }
.sub-page-header { padding: 12px 16px; border-bottom: 1px solid #eee; background: #fff; position: sticky; top: 0; z-index: 10; }
.info-card__text { font-size: 13px; color: #666; line-height: 1.6; }
.epds-form { margin-top: 8px; }
.epds-question__text { font-size: 15px; font-weight: 500; color: #333; margin-bottom: 12px; line-height: 1.5; }
.epds-options { display: flex; flex-direction: column; gap: 8px; }
.epds-option { padding: 12px 16px; border: 1.5px solid #e0e0e0; border-radius: 10px; background: #fff; font-size: 14px; color: #333; cursor: pointer; transition: all 0.2s ease; text-align: left; }
.epds-option:hover { border-color: #7E57C2; background: #f3e5f5; }
.epds-option--selected { border-color: #7E57C2; background: #ede7f6; color: #4527a0; font-weight: 500; }
.epds-result { margin-top: 16px; padding: 16px; background: #f5f5f5; border-radius: 10px; text-align: center; }
.epds-result__score { font-size: 18px; margin-bottom: 8px; }
.epds-result__recommendations { text-align: left; margin-top: 12px; }
.epds-rec-item { font-size: 13px; color: #555; margin: 4px 0; padding-left: 16px; position: relative; }
.epds-rec-item::before { content: "•"; position: absolute; left: 0; color: #7E57C2; }
</style>
