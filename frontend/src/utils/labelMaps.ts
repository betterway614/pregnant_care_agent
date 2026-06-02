/**
 * 统一的英文→中文标签映射
 *
 * 所有健康指标、随访字段、产科检查、生化指标的中文名称
 * 集中管理，避免各组件重复定义。
 */

// ==================== 健康趋势指标 ====================

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
}

/** 生化指标字段中文映射 */
const LAB_LABEL_MAP: Record<string, string> = {
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
}

/** 获取主观数据字段中文标签，未匹配时返回原始 key */
export function fieldLabel(key: string): string {
  return FIELD_LABEL_MAP[key] || key
}

/** 获取产科检查字段中文标签，未匹配时返回原始 key */
export function examLabel(key: string): string {
  return EXAM_LABEL_MAP[key] || key
}

/** 获取生化指标字段中文标签，未匹配时返回原始 key */
export function labLabel(key: string): string {
  return LAB_LABEL_MAP[key] || key
}
