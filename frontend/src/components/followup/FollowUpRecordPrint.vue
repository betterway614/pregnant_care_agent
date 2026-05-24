<template>
  <div class="record-print" ref="printEl">
    <!-- 表头 -->
    <div class="record-print__header">
      <div class="record-print__hospital">AI-Care 孕期智能管理平台</div>
      <div class="record-print__title">随访记录单</div>
      <div class="record-print__id">记录编号：{{ snapshot.record_id || recordId || '--' }}</div>
    </div>

    <!-- 患者信息栏 -->
    <div class="record-print__info-bar">
      <div class="info-item">
        <span class="info-item__label">孕妇</span>
        <span class="info-item__value">{{ snapshot.patient_name || '--' }}</span>
      </div>
      <div class="info-item">
        <span class="info-item__label">孕周</span>
        <span class="info-item__value">{{ snapshot.gestational_week || '--' }}</span>
      </div>
      <div class="info-item">
        <span class="info-item__label">日期</span>
        <span class="info-item__value">{{ snapshot.follow_up_date || '--' }}</span>
      </div>
      <div class="info-item">
        <span class="info-item__label">分类</span>
        <span class="info-item__value" :class="clsClass">{{ clsLabel }}</span>
      </div>
    </div>

    <!-- S: 主观数据 -->
    <div class="record-print__section">
      <div class="section-head">
        <span class="section-badge section-badge--s">S</span>
        <span class="section-title">主观数据</span>
      </div>
      <div class="section-body">
        <div class="kv-grid">
          <div v-for="(val, key) in snapshot.self_reported_data" :key="key" class="kv-item">
            <span class="kv-item__key">{{ fieldLabel(String(key)) }}</span>
            <span class="kv-item__val">{{ val }}</span>
          </div>
        </div>
        <div v-if="snapshot.chief_complaint" class="complaint-line">
          主诉：{{ snapshot.chief_complaint }}
        </div>
      </div>
    </div>

    <!-- O: 客观检查 -->
    <div class="record-print__section">
      <div class="section-head">
        <span class="section-badge section-badge--o">O</span>
        <span class="section-title">客观检查</span>
      </div>
      <div class="section-body">
        <div v-if="hasExam(snapshot.obstetric_exam)">
          <div class="sub-title">产科检查</div>
          <div class="exam-grid">
            <div v-for="(val, key) in snapshot.obstetric_exam" :key="key" class="exam-cell">
              <div class="exam-cell__label">{{ examLabel(String(key)) }}</div>
              <div class="exam-cell__value">{{ val }}</div>
            </div>
          </div>
        </div>
        <div v-if="hasExam(snapshot.lab_results)" style="margin-top: 8px;">
          <div class="sub-title">化验结果</div>
          <div class="exam-grid">
            <div v-for="(val, key) in snapshot.lab_results" :key="key" class="exam-cell">
              <div class="exam-cell__label">{{ labLabel(String(key)) }}</div>
              <div class="exam-cell__value">{{ val }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- A: 评估 -->
    <div class="record-print__section">
      <div class="section-head">
        <span class="section-badge section-badge--a">A</span>
        <span class="section-title">评估</span>
      </div>
      <div class="section-body">
        <p class="assessment-text">{{ snapshot.summary || '暂无评估' }}</p>
      </div>
    </div>

    <!-- P: 计划 -->
    <div class="record-print__section">
      <div class="section-head">
        <span class="section-badge section-badge--p">P</span>
        <span class="section-title">计划</span>
      </div>
      <div class="section-body">
        <div v-for="(g, i) in (snapshot.guidance_tags || [])" :key="i" class="guidance-line">
          [{{ g.tag }}] {{ g.content }}
        </div>
        <div v-if="snapshot.next_followup_date" class="next-date-line">
          下次随访日期：{{ snapshot.next_followup_date }}
        </div>
        <div v-if="snapshot.referral?.has_referral" class="referral-line">
          转诊：{{ snapshot.referral.reason }} → {{ snapshot.referral.institution }} {{ snapshot.referral.department }}
        </div>
      </div>
    </div>

    <!-- 审核信息 -->
    <div v-if="snapshot.reviewed_by" class="record-print__section record-print__section--audit">
      <div class="section-head">
        <span class="section-title">审核信息</span>
      </div>
      <div class="section-body audit-body">
        <span>审核人：{{ snapshot.reviewed_by }}</span>
        <span>审核时间：{{ snapshot.reviewed_at }}</span>
        <span v-if="snapshot.review_comment">审核意见：{{ snapshot.review_comment }}</span>
      </div>
    </div>

    <!-- 签名栏 -->
    <div class="record-print__signatures">
      <div class="sign-block">
        <div class="sign-block__label">随访护士签名</div>
        <div class="sign-block__line">
          <img v-if="nurseSignature" :src="nurseSignature" class="sign-block__img" />
          <span v-else class="sign-block__blank">__________________</span>
        </div>
        <div class="sign-block__date">日期：____________</div>
      </div>
      <div class="sign-block">
        <div class="sign-block__label">孕妇签名</div>
        <div class="sign-block__line">
          <img v-if="patientSignature" :src="patientSignature" class="sign-block__img" />
          <span v-else class="sign-block__blank">__________________</span>
        </div>
        <div class="sign-block__date">日期：____________</div>
      </div>
    </div>

    <!-- 页脚 -->
    <div class="record-print__footer">
      本记录由 AI-Care 孕期智能管理平台生成 | 打印日期：{{ printDate }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  snapshot: Record<string, any>
  recordId?: string
  nurseSignature?: string | null
  patientSignature?: string | null
}>()

const printDate = new Date().toLocaleDateString('zh-CN')

const clsLabel = computed(() => {
  const map: Record<string, string> = { normal: '正常', abnormal: '异常', critical: '高危' }
  return map[props.snapshot.classification || 'normal'] || '未知'
})

const clsClass = computed(() => {
  const c = props.snapshot.classification
  if (c === 'critical') return 'cls--danger'
  if (c === 'abnormal') return 'cls--warning'
  return 'cls--success'
})

function hasExam(obj: Record<string, any> | undefined): boolean {
  return !!obj && Object.keys(obj).length > 0
}

function fieldLabel(key: string): string {
  const map: Record<string, string> = {
    weight: '体重', bp: '血压', fetal_movement: '胎动', diet: '饮食',
    mood: '情绪', sleep: '睡眠', stress: '压力', medication: '用药',
    nausea: '孕吐', feeling: '感受', blood_sugar_fasting: '空腹血糖',
    blood_sugar_2h: '餐后血糖', sleep_quality: '睡眠质量',
  }
  return map[key] || key
}

function examLabel(key: string): string {
  const map: Record<string, string> = {
    fundal_height_cm: '宫高(cm)', abdominal_circumference_cm: '腹围(cm)',
    fetal_position: '胎位', fetal_heart_rate_bpm: '胎心率(bpm)',
    blood_pressure: '血压(mmHg)',
  }
  return map[key] || key
}

function labLabel(key: string): string {
  const map: Record<string, string> = {
    hemoglobin_g_L: '血红蛋白(g/L)', urine_protein: '尿蛋白',
    blood_sugar_fasting: '空腹血糖(mmol/L)', blood_sugar_2h: '餐后血糖(mmol/L)',
    alt: '谷丙转氨酶(U/L)', ast: '谷草转氨酶(U/L)',
    creatinine: '肌酐(μmol/L)', uric_acid: '尿酸(μmol/L)', albumin: '白蛋白(g/L)',
    wbc: '白细胞(×10⁹/L)', platelet: '血小板(×10⁹/L)', hct: '红细胞压积(%)',
    bilirubin_total: '总胆红素(μmol/L)',
  }
  return map[key] || key
}
</script>

<style scoped>
.record-print {
  max-width: 210mm;
  margin: 0 auto;
  padding: 20mm 15mm;
  font-family: 'SimSun', 'Noto Serif SC', serif;
  font-size: 14px;
  line-height: 1.8;
  color: #333;
  background: #fff;
}

/* 表头 */
.record-print__header {
  text-align: center;
  border-bottom: 2px solid #333;
  padding-bottom: 12px;
  margin-bottom: 16px;
}
.record-print__hospital {
  font-size: 12px;
  color: #666;
}
.record-print__title {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 4px;
  margin: 4px 0;
}
.record-print__id {
  font-size: 11px;
  color: #999;
}

/* 患者信息栏 */
.record-print__info-bar {
  display: flex;
  gap: 24px;
  padding: 10px 0;
  border-bottom: 1px solid #eee;
  margin-bottom: 16px;
}
.info-item {
  display: flex;
  gap: 6px;
  align-items: baseline;
}
.info-item__label {
  font-size: 12px;
  color: #999;
}
.info-item__value {
  font-size: 14px;
  font-weight: 600;
}
.cls--success { color: #67c23a; }
.cls--warning { color: #e6a23c; }
.cls--danger { color: #f56c6c; }

/* 各节 */
.record-print__section {
  margin-bottom: 16px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}
.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f8f9fa;
  border-bottom: 1px solid #e4e7ed;
}
.section-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
}
.section-badge--s { background: #409EFF; }
.section-badge--o { background: #67C23A; }
.section-badge--a { background: #E6A23C; }
.section-badge--p { background: #909399; }
.section-title { font-size: 14px; font-weight: 600; }
.section-body { padding: 12px; }

.record-print__section--audit {
  background: #f8f9fa;
}

/* KV grid */
.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 4px 16px;
}
.kv-item { display: flex; gap: 8px; align-items: baseline; }
.kv-item__key { font-size: 12px; color: #666; min-width: 56px; }
.kv-item__val { font-size: 13px; font-weight: 500; }

.complaint-line { margin-top: 8px; font-size: 13px; }

/* Exam grid */
.sub-title { font-size: 12px; color: #666; margin-bottom: 6px; }
.exam-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}
.exam-cell {
  text-align: center;
  padding: 6px;
  background: #f5f7fa;
  border-radius: 4px;
}
.exam-cell__label { font-size: 11px; color: #999; }
.exam-cell__value { font-size: 14px; font-weight: 700; }

.assessment-text { margin: 0; font-size: 13px; line-height: 1.7; }

.guidance-line { font-size: 13px; margin: 4px 0; }
.next-date-line { margin-top: 8px; font-weight: 600; font-size: 13px; }
.referral-line { margin-top: 6px; font-size: 12px; color: #f56c6c; }

.audit-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: #666;
}

/* 签名栏 */
.record-print__signatures {
  display: flex;
  justify-content: space-between;
  margin-top: 32px;
  padding-top: 16px;
  border-top: 1px solid #ccc;
}
.sign-block {
  text-align: center;
  min-width: 180px;
}
.sign-block__label {
  font-size: 12px;
  color: #666;
  margin-bottom: 8px;
}
.sign-block__line {
  min-height: 50px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sign-block__img {
  max-width: 160px;
  max-height: 60px;
  border-bottom: 1px solid #333;
}
.sign-block__blank {
  font-size: 13px;
  color: #ccc;
}
.sign-block__date {
  font-size: 12px;
  color: #666;
  margin-top: 6px;
}

/* 页脚 */
.record-print__footer {
  margin-top: 24px;
  padding-top: 8px;
  border-top: 1px solid #eee;
  font-size: 11px;
  color: #999;
  text-align: center;
}

/* 打印样式 */
@media print {
  .record-print {
    padding: 10mm 15mm;
    box-shadow: none;
    border: none;
  }
  .record-print__section { break-inside: avoid; }
  .record-print__signatures { break-inside: avoid; }
}
</style>
