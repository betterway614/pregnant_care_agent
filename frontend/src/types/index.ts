/* AI-Care 前端类型定义 */

// 孕妇
export interface Pregnant {
  pregnant_id: string
  display_name: string
  nickname?: string
  phone?: string
  hospital_id?: string
  gestational_age_days?: number
  lmp_date?: string
  edd?: string
  risk_tags: string[]
  created_at?: string
}

// 主页响应
export interface HomeResponse {
  pregnant: Pregnant
  gestational_week: number
  gestational_day: number
  baby_info: string
  today_tasks: TaskItem[]
  upcoming_checks: CheckItem[]
  recommendations: Recommendations
  health_summary: HealthSummary
}

export interface TaskItem {
  id: string
  type: string
  title: string
  description: string
  is_completed: boolean
  is_urgent?: boolean
}

export interface CheckItem {
  id: string
  date: string
  item_name: string
  check_type?: string
  status: string
  notes?: string
}

export interface Recommendations {
  weekly_tips: string
  diet_advice: string
  exercise_advice: string
  warning_signs: string
}

export interface HealthSummary {
  latest_weight?: number
  latest_blood_pressure?: string
  latest_fetal_movement?: number
  weight_trend?: string
}

// 推荐响应
export interface RecommendResponse {
  id: string
  content: string
  categories: string[]
  created_at?: string
  source?: string
}

// 健康数据点
export interface HealthDataPoint {
  id: string
  pregnant_id: string
  metric_code: string
  value: number
  unit: string
  recorded_at: string
  source: string
}

// 排期节点
export interface ScheduleNode {
  id: string
  pregnant_id: string
  gest_week: number
  scheduled_date: string
  item: string
  node_type: string
  status: string
  is_published: number
}

// 随访记录
export interface FollowUpRecord {
  id: string
  pregnant_id: string
  gestational_week?: string
  follow_up_date?: string
  self_reported_data: Record<string, any>
  chief_complaint?: string
  health_education: string[]
  status: string
  summary?: string
  created_at?: string
  patient_name?: string
}

// 预警
export interface Alert {
  id: string
  pregnant_id: string
  trigger_source: string
  rule_id?: string
  level: string
  message: string
  details: Record<string, any>
  status: string
  created_at?: string
  patient_name?: string
  gestational_age_days?: number
}

// FGR评估
export interface FgrAssessment {
  case_id: string
  risk_level: string
  risk_label: string
  confidence_interval: { lowerBound: number; upperBound: number }
  explanation: string
  processing_time: number
  hardware: string
}

export interface FgrTrendPoint {
  gestational_weeks: number
  risk_score: number
  confidence_lower: number
  confidence_upper: number
  assessed_at: string
}

// 医嘱
export interface MedicalOrder {
  id: string
  pregnant_id: string
  alert_id?: string
  content: string
  order_type: string
  source: string
  status: string
  created_at?: string
  patient_name?: string
}

// 统计
export interface DashboardStats {
  total_pregnant: number
  pending_alerts: number
  today_followups: number
  pending_reviews: number
  high_risk_count: number
  weekly_new_pregnant: number
}

// 硬件监控
export interface HardwareMonitor {
  gpu_utilization: number
  gpu_memory_used: number
  npu_utilization: number
  cpu_utilization: number
  memory_used: number
  memory_total: number
  inference_latency_ms: number
  power_watts: number
  gpu_info?: { model: string; driver: string; temperature: number }
  npu_info?: { model: string; status: string; ops: string }
  uma_info?: { total_gb: number; used_gb: number; available_gb: number }
  timestamp?: string
}

// 对话
export interface ChatRequest {
  pregnant_id: string
  message: string
  session_id?: string
  message_type?: string
  record_id?: string  // 随访记录ID，存在时进入随访Agent模式
}

export interface ChatResponse {
  content: string
  nlu_result?: { intent: string; entities: Record<string, any> }
  session_id: string
  memory_updated: string[]
  source?: string
  followup_progress?: { answered: number; total: number; status: string }
}

// 角色
export type UserRole = 'nurse' | 'doctor' | 'pregnant' | 'admin'
