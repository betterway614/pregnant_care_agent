/**
 * 统一的英文→中文标签映射
 *
 * 所有健康指标、随访字段、产科检查、生化指标的中文名称
 * 集中管理，避免各组件重复定义。
 */

// ==================== 健康趋势指标 ====================

/** 指标分类定义 */
export interface IndicatorCategory {
  key: string           // 分类唯一标识
  name: string          // 中文名
  icon: string          // emoji 图标
  description: string   // 简短描述，提示用户此分类的查看场景
  metrics: string[]     // 包含的指标 code
  /** 配对组：同一组内的指标渲染为 combo chart（共享 tooltip 和 X 轴） */
  comboGroups?: { name: string; metrics: string[] }[]
  /** 建议同时显示的指标上限，超限时提示用户 */
  maxVisible?: number
}

/** 指标分类体系 — 按临床领域 + 单位类型分组 */
export const CATEGORIES: IndicatorCategory[] = [
  {
    key: 'vital_signs',
    name: '生命体征',
    icon: '🫀',
    description: '体重、血压、心率等常规监测指标',
    metrics: ['weight', 'systolic', 'diastolic', 'heart_rate'],
    comboGroups: [{ name: '血压', metrics: ['systolic', 'diastolic'] }],
    maxVisible: 4,
  },
  {
    key: 'blood_sugar',
    name: '血糖管理',
    icon: '🍬',
    description: '空腹和餐后血糖',
    metrics: ['blood_sugar_fasting', 'blood_sugar_postprandial'],
    comboGroups: [{ name: '血糖', metrics: ['blood_sugar_fasting', 'blood_sugar_postprandial'] }],
    maxVisible: 2,
  },
  {
    key: 'daily_tracking',
    name: '生活管理',
    icon: '📊',
    description: '睡眠、运动、情绪等日常记录',
    metrics: ['sleep_hours', 'steps', 'emotion_score'],
    maxVisible: 3,
  },
  {
    key: 'fetal',
    name: '胎儿监测',
    icon: '👶',
    description: '胎动计数',
    metrics: ['fetal_movement'],
    maxVisible: 1,
  },
]

/** 化验指标分类（独立于健康趋势，单位体系不同） */
export const LAB_CATEGORY: IndicatorCategory = {
  key: 'lab_tests',
  name: '化验指标',
  icon: '🔬',
  description: '血常规、肝肾功能等实验室检查',
  metrics: [
    'hemoglobin_g_L', 'albumin',           // g/L 组
    'alt', 'ast',                            // U/L 组
    'creatinine', 'uric_acid', 'bilirubin_total', // μmol/L 组
    'wbc', 'platelet',                       // ×10⁹/L 组
    'hct',                                    // % 组
  ],
  maxVisible: 6,
}

/** 根据分类 key 获取该分类下所有指标的元数据 */
export function getCategoryMetrics(categoryKey: string): string[] {
  if (categoryKey === 'lab_tests') return LAB_CATEGORY.metrics
  const cat = CATEGORIES.find(c => c.key === categoryKey)
  return cat ? cat.metrics : []
}

/** 根据分类 key 获取分类信息 */
export function getCategory(categoryKey: string): IndicatorCategory | undefined {
  if (categoryKey === 'lab_tests') return LAB_CATEGORY
  return CATEGORIES.find(c => c.key === categoryKey)
}

/** 获取所有分类（含化验） */
export function getAllCategories(): IndicatorCategory[] {
  return [...CATEGORIES, LAB_CATEGORY]
}

/** 根据指标 code 反向查找所属分类 */
export function getCategoryByMetric(metric: string): IndicatorCategory | undefined {
  for (const cat of getAllCategories()) {
    if (cat.metrics.includes(metric)) return cat
  }
  return undefined
}

/** 健康趋势指标选项（含 value + label），用于 checkbox/select */
export const METRIC_OPTIONS = [
  { value: 'weight', label: '体重' },
  { value: 'systolic', label: '收缩压' },
  { value: 'diastolic', label: '舒张压' },
  { value: 'blood_sugar_fasting', label: '空腹血糖' },
  { value: 'blood_sugar_postprandial', label: '餐后血糖' },
  { value: 'fetal_movement', label: '胎动' },
  { value: 'heart_rate', label: '心率' },
  { value: 'sleep_hours', label: '睡眠' },
  { value: 'steps', label: '步数' },
  { value: 'emotion_score', label: '情绪' },
]

/** 健康趋势指标中文名称映射 */
export const TREND_NAME_MAP: Record<string, string> = {
  weight: '体重',
  systolic: '收缩压',
  diastolic: '舒张压',
  fetal_movement: '胎动',
  blood_sugar: '血糖',
  blood_sugar_fasting: '空腹血糖',
  blood_sugar_postprandial: '餐后血糖',
  heart_rate: '心率',
  sleep_hours: '睡眠',
  steps: '步数',
  emotion_score: '情绪',
}

/** 根据 metric code 获取中文名称 */
export function trendName(metric: string): string {
  return TREND_NAME_MAP[metric] || metric
}

// ==================== 生化指标 ====================

/** 生化指标选项（含 value + label），用于 checkbox/select */
export const LAB_METRIC_OPTIONS = [
  { value: 'hemoglobin_g_L', label: '血红蛋白' },
  { value: 'alt', label: '谷丙转氨酶' },
  { value: 'ast', label: '谷草转氨酶' },
  { value: 'creatinine', label: '肌酐' },
  { value: 'albumin', label: '白蛋白' },
  { value: 'uric_acid', label: '尿酸' },
  { value: 'wbc', label: '白细胞' },
  { value: 'platelet', label: '血小板' },
  { value: 'hct', label: '红细胞压积' },
  { value: 'bilirubin_total', label: '总胆红素' },
]

/** 生化指标完整元数据 */
export const LAB_METRIC_META: Record<string, { name: string; unit: string; normal_low: number | null; normal_high: number | null }> = {
  hemoglobin_g_L: { name: '血红蛋白', unit: 'g/L', normal_low: 100, normal_high: 160 },
  alt: { name: '谷丙转氨酶(ALT)', unit: 'U/L', normal_low: 0, normal_high: 40 },
  ast: { name: '谷草转氨酶(AST)', unit: 'U/L', normal_low: 0, normal_high: 40 },
  creatinine: { name: '肌酐', unit: 'μmol/L', normal_low: 45, normal_high: 84 },
  uric_acid: { name: '尿酸', unit: 'μmol/L', normal_low: 150, normal_high: 360 },
  albumin: { name: '白蛋白', unit: 'g/L', normal_low: 35, normal_high: 55 },
  wbc: { name: '白细胞', unit: '×10⁹/L', normal_low: 4.0, normal_high: 10.0 },
  platelet: { name: '血小板', unit: '×10⁹/L', normal_low: 100, normal_high: 300 },
  hct: { name: '红细胞压积', unit: '%', normal_low: 35, normal_high: 50 },
  bilirubin_total: { name: '总胆红素', unit: 'μmol/L', normal_low: 0, normal_high: 21 },
}

// ==================== 随访字段标签 ====================

/** 主观数据字段中文映射 */
const FIELD_LABEL_MAP: Record<string, string> = {
  weight: '体重',
  bp: '血压',
  blood_pressure: '血压',
  bp_morning: '晨血压',
  bp_evening: '晚血压',
  fetal_movement: '胎动',
  diet: '饮食',
  mood: '情绪',
  emotion_score: '情绪评分',
  sleep: '睡眠',
  sleep_hours: '睡眠',
  sleep_quality: '睡眠质量',
  stress: '压力',
  support: '社会支持',
  medication: '用药',
  supplement: '补充剂',
  nausea: '恶心呕吐',
  bleeding: '出血',
  feeling: '身体感受',
  wound: '伤口',
  edema: '水肿',
  contraction: '宫缩',
  exercise: '运动',
  preparation: '分娩准备',
  signs: '临产征兆',
  appetite: '食欲',
  self_harm: '自伤想法',
  blood_sugar_fasting: '空腹血糖',
  blood_sugar_2h: '餐后血糖',
  blood_sugar_postprandial: '餐后血糖',
  steps: '步数',
  heart_rate: '心率',
  reason: '原因说明',
  notes: '备注',
  symptoms: '症状',
  temperature: '体温',
  headache: '头痛',
  dizziness: '头晕',
  fatigue: '疲劳',
  pain: '疼痛',
  swelling: '肿胀',
  vomiting: '呕吐',
  constipation: '便秘',
  frequency_of_urination: '排尿频率',
  baby_movement: '胎动',
  water_break: '破水',
  vision_changes: '视力变化',
  shortness_of_breath: '呼吸困难',
}

/** 产科检查字段中文映射 */
const EXAM_LABEL_MAP: Record<string, string> = {
  fundal_height_cm: '宫高(cm)',
  abdominal_circumference_cm: '腹围(cm)',
  fetal_position: '胎位',
  fetal_heart_rate_bpm: '胎心率(bpm)',
  blood_pressure: '血压(mmHg)',
  urine_protein: '尿蛋白',
  blood_sugar_fasting: '空腹血糖',
  blood_sugar_2h: '餐后2h血糖',
  cervical_dilation: '宫口开大',
  effacement: '宫颈消退',
  presentation: '先露',
  amniotic_fluid: '羊水',
  estimated_fetal_weight: '估计胎儿体重',
}

/** 生化指标字段中文映射 */
export const LAB_LABEL_MAP: Record<string, string> = {
  hemoglobin_g_L: '血红蛋白(g/L)',
  urine_protein: '尿蛋白',
  blood_sugar_fasting: '空腹血糖(mmol/L)',
  blood_sugar_2h: '餐后2h血糖(mmol/L)',
  alt: '谷丙转氨酶(U/L)',
  ast: '谷草转氨酶(U/L)',
  creatinine: '肌酐(μmol/L)',
  uric_acid: '尿酸(μmol/L)',
  albumin: '白蛋白(g/L)',
  wbc: '白细胞(×10⁹/L)',
  platelet: '血小板(×10⁹/L)',
  hct: '红细胞压积(%)',
  bilirubin_total: '总胆红素(μmol/L)',
  urine_glucose: '尿糖',
  urine_ketone: '尿酮体',
  hba1c: '糖化血红蛋白',
  tsh: '促甲状腺激素',
  ft4: '游离甲状腺素',
}

/** snake_case 常见英文词根→中文映射（用于未知 key 的友好回退） */
const SNAKE_WORD_MAP: Record<string, string> = {
  blood: '血液', pressure: '压力/血压', sugar: '糖', heart: '心', rate: '率',
  weight: '体重', height: '身高', sleep: '睡眠', mood: '情绪', diet: '饮食',
  fetal: '胎儿', baby: '婴儿', movement: '活动', motion: '运动',
  pain: '疼痛', score: '评分', level: '水平', count: '计数',
  morning: '晨', evening: '晚', night: '夜', day: '日',
  fasting: '空腹', postprandial: '餐后', quality: '质量',
  systolic: '收缩压', diastolic: '舒张压',
  urine: '尿', protein: '蛋白', glucose: '葡萄糖', ketone: '酮体',
  hemoglobin: '血红蛋白', albumin: '白蛋白', creatinine: '肌酐',
  acid: '酸', total: '总', direct: '直接', indirect: '间接',
  wbc: '白细胞', rbc: '红细胞', platelet: '血小板', hct: '红细胞压积',
  alt: '谷丙转氨酶', ast: '谷草转氨酶', tsh: '促甲状腺激素',
  fundal: '宫底', abdominal: '腹部', circumference: '周长',
  position: '位置', cervical: '宫颈', dilation: '扩张',
  amniotic: '羊水', fluid: '液体', estimated: '估计',
  temperature: '体温', headache: '头痛', dizziness: '头晕',
  fatigue: '疲劳', nausea: '恶心', vomiting: '呕吐',
  edema: '水肿', bleeding: '出血', contraction: '宫缩',
  appetite: '食欲', stress: '压力', exercise: '运动',
  steps: '步数', emotion: '情绪', feeling: '感受',
  reason: '原因', notes: '备注', symptoms: '症状',
  self: '自', harm: '伤害', harm_thoughts: '自伤想法',
}

/** 将 snake_case 英文 key 转为友好中文标签（尽力翻译，无法翻译的部分保留原文） */
function snakeToChineseLabel(key: string): string {
  const parts = key.split('_')
  const translated = parts.map(p => SNAKE_WORD_MAP[p] || p)
  // 如果所有部分都翻译成功，拼接中文
  const allTranslated = translated.every(t => !/^[a-z_]+$/i.test(t) || SNAKE_WORD_MAP[t])
  if (allTranslated && translated.every(t => !/^[a-z]+$/.test(t))) {
    return translated.join('')
  }
  // 部分翻译：用中文部分 + 原文下划线分隔
  return translated.join(' ')
}

/** 获取主观数据字段中文标签，未匹配时将 snake_case 转为可读中文 */
export function fieldLabel(key: string): string {
  return FIELD_LABEL_MAP[key] || snakeToChineseLabel(key)
}

/** 获取产科检查字段中文标签，未匹配时将 snake_case 转为可读中文 */
export function examLabel(key: string): string {
  return EXAM_LABEL_MAP[key] || snakeToChineseLabel(key)
}

/** 获取生化指标字段中文标签，未匹配时将 snake_case 转为可读中文 */
export function labLabel(key: string): string {
  return LAB_LABEL_MAP[key] || snakeToChineseLabel(key)
}

// ==================== 预警公共映射 ====================

/** 触发来源中文映射（护士端 + 医生端共用） */
const TRIGGER_SOURCE_LABEL_MAP: Record<string, string> = {
  RULE_ENGINE: '规则引擎',
  FGR_ALGORITHM: 'FGR评估算法',
  MANUAL: '手动创建',
  EPDS_SCREENING: 'EPDS心理筛查',
  FOLLOWUP: '随访',
}

/** 获取触发来源中文标签 */
export function triggerSourceLabel(source?: string): string {
  if (!source) return '--'
  return TRIGGER_SOURCE_LABEL_MAP[source] || source
}

/** 规则ID中文名称映射（全量，覆盖护士端 + 医生端所有规则） */
const RULE_ID_LABEL_MAP: Record<string, string> = {
  RULE_BP_HIGH: '血压异常升高',
  RULE_BP_HIGH_ORANGE: '血压偏高关注',
  RULE_BP_CRITICAL: '血压危急',
  RULE_BP_LOW: '血压偏低',
  RULE_LATE_PREGNANCY_BP: '孕晚期血压偏高',
  RULE_BLOOD_SUGAR_HIGH: '血糖偏高',
  RULE_BS_POSTPRANDIAL_HIGH: '餐后血糖异常',
  RULE_BS_FASTING_HIGH: '空腹血糖偏高',
  RULE_WEIGHT_GAIN_FAST: '体重增长过快',
  RULE_WEIGHT_GAIN_SLOW: '体重增长过慢',
  RULE_FETAL_DROP: '胎动显著减少',
  RULE_FETAL_VERY_LOW: '胎动极少',
  RULE_FETAL_HEART: '胎心异常',
  RULE_GDM: '妊娠糖尿病',
  RULE_PRE_ECLAMPSIA: '子痫前期',
  RULE_EMOTION_CRITICAL: '情绪评分严重偏低',
  RULE_EMOTION_HIGH: '情绪评分偏低',
  RULE_SLEEP_SHORT: '睡眠不足',
  FGR_CRITICAL_RISK: 'FGR极高风险',
  FGR_HIGH_RISK: 'FGR高风险',
  FGR_MEDIUM_RISK: 'FGR中风险',
  EPDS_HIGH_RISK: 'EPDS心理筛查高风险',
  NURSE_AI_ALERT: '护士AI预警',
  AGENT_TOOL_ALERT: '智能体工具预警',
  MANUAL: '手动创建',
}

/** 获取规则ID中文名称 */
export function ruleIdLabel(ruleId?: string): string {
  if (!ruleId) return '--'
  return RULE_ID_LABEL_MAP[ruleId] || ruleId.replace(/_/g, ' ')
}

/** 预警状态中文文本映射 */
const ALERT_STATUS_TEXT_MAP: Record<string, string> = {
  PENDING: '待处理',
  CONFIRMED: '已确认',
  DISMISSED: '已驳回',
  ESCALATED: '已升级(紧急)',
  AUTO_DISMISSED: '已自动关闭',
}

/** 获取预警状态中文文本（兼容大小写输入） */
export function alertStatusText(status: string): string {
  return ALERT_STATUS_TEXT_MAP[(status || '').toUpperCase()] || status
}

/** 预警状态对应的 Element Plus Tag 类型 */
const ALERT_STATUS_TAG_MAP: Record<string, string> = {
  PENDING: 'warning',
  CONFIRMED: 'success',
  DISMISSED: 'info',
  ESCALATED: 'danger',
  AUTO_DISMISSED: 'info',
}

/** 获取预警状态 Tag 颜色类型（兼容大小写输入） */
export function alertStatusTagType(status: string): string {
  return ALERT_STATUS_TAG_MAP[(status || '').toUpperCase()] || 'info'
}

/** 原始数据 key 中文映射（用于 JSON 详情展示） */
const RAW_KEY_MAP: Record<string, string> = {
  action: '处理动作', metric: '指标', value: '数值', threshold: '阈值',
  unit: '单位', pregnant_id: '孕妇ID', gestational_week: '孕周',
  trigger_source: '触发来源', rule_id: '规则ID',
  bp_systolic: '收缩压', bp_diastolic: '舒张压', blood_sugar: '血糖',
  fetal_movement: '胎动', risk_level: '风险等级', risk_score: '风险评分',
  estimated_weight: '估计体重', explanation: '说明', recommendation: '建议',
}

/** 格式化原始数据（排除 llm_analysis，key 中文化） */
export function formatRawDetails(details: Record<string, any>): string {
  const raw: Record<string, any> = {}
  for (const [key, val] of Object.entries(details)) {
    if (key === 'llm_analysis') continue
    const label = RAW_KEY_MAP[key] || key
    raw[label] = val
  }
  return JSON.stringify(raw, null, 2)
}

/** 是否有需要展示的原始数据（排除 llm_analysis 后仍有其他字段） */
export function hasRawDetails(details: Record<string, any> | undefined): boolean {
  if (!details) return false
  const raw = { ...details }
  delete raw.llm_analysis
  return Object.keys(raw).length > 0
}

// ==================== 详情结构化展示 ====================

/** 需要在"相关数据"区域隐藏的字段（已有独立展示区域或为内部字段） */
export const HIDDEN_DETAIL_KEYS = new Set([
  'history',        // 处理记录 — 已有独立时间线展示
  'source_role',    // 内部字段
  'created_at',     // 与预警创建时间重复
  'analyzed_at',    // 内部时间戳
  'llm_analysis',   // 复杂嵌套对象，专用 AI 分析区域展示
  'ai_workflow',    // 复杂嵌套对象，专用 AI 分析区域展示
])

/** 详情 key 中文映射（结构化 key-value 展示用） */
export function formatDetailKey(key: string): string {
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
    gestational_weeks: '孕周',
    // 置信区间
    confidence_interval: '置信区间',
    // 规则与处理
    action: '处理动作',
    triggered_rules: '触发规则列表',
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

/** 详情值友好格式化 */
export function formatDetailValue(key: string, value: any): string {
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

/** 处理记录动作中文映射 */
export function historyActionLabel(action: string): string {
  const map: Record<string, string> = {
    created: '创建预警',
    downgrade: '降级',
    nurse_escalate: '护士升级',
    nurse_appeal: '护士复议',
    confirm: '医生确认高危',
    nurse_confirm: '护士确认',
    dismiss: '解除',
    nurse_dismiss: '护士解除',
    auto_dismiss: '自动关闭',
  }
  return map[action] || action
}
