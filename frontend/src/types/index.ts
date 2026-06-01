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
  obstetric_exam: Record<string, any>
  lab_results: Record<string, any>
  classification: string
  health_education: string[]
  guidance_tags: Array<{ tag: string; content: string }>
  referral: Record<string, any> | null
  next_followup_date?: string
  status: string
  summary?: string
  reviewed_by?: string
  reviewed_at?: string
  review_comment?: string
  ai_snapshot: Record<string, any>
  record_snapshot: Record<string, any>
  record_text: string | null
  signature_data: Record<string, any>
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
  fgr_probability: number | null
  predicted_label: string | null
  model_confidence: string | null
  confidence_interval: Record<string, number>
  explanation: string
  processing_time: number
  hardware: string
  fold_details: Array<Record<string, any>> | null
}

export interface PatientImageInfo {
  pregnant_id: string
  has_image: boolean
  image_url: string
  display_name: string
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
  signed_at?: string
  acknowledged_at?: string
  patient_name?: string
  created_by?: string
  signature_data?: { image?: string; signer?: string; signed_at?: string }
  order_snapshot?: Record<string, any>
  order_text?: string
  modified_by_doctor?: boolean
  doctor_notes?: string
}

// 医嘱文档
export interface OrderDocument {
  order_id: string
  patient_name: string
  snapshot: Record<string, any>
  text: string
  signature: { image?: string; signer?: string; signed_at?: string }
  has_document: boolean
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

// 对话
export interface ChatRequest {
  pregnant_id: string
  message: string
  session_id?: string
  message_type?: string  // TEXT | AUDIO
  record_id?: string  // 随访记录ID，存在时进入随访Agent模式
  audio_data?: string  // base64 编码的音频数据（message_type=AUDIO 时使用）
  audio_format?: string  // 音频格式: webm, wav, mp3
}

export interface ChatResponse {
  content: string
  nlu_result?: { intent: string; entities: Record<string, any> }
  session_id: string
  memory_updated: string[]
  source?: string
  followup_progress?: { answered: number; total: number; status: string }
  tool_steps?: string[]  // Agent 工具调用步骤（Plan-and-Execute 可见化）
}

export interface AudioRecorderResult {
  base64: string
  format: string
  duration: number
  blob: Blob
}

export interface ConversationMessage {
  role: string
  content: string
  session_id?: string
  created_at?: string
}

// 角色
export type UserRole = 'nurse' | 'doctor' | 'pregnant' | 'admin'

// 健康趋势数据
export interface TrendDataPoint {
  date: string
  gest_week: number
  value: number
}

export interface TrendSeries {
  metric: string
  name: string
  unit: string
  normal_range: { min: number; max: number }
  data: TrendDataPoint[]
  trend: 'rising' | 'falling' | 'stable' | 'insufficient_data'
  latest_value: number | null
  is_normal: boolean | null
}

export interface HealthTrendResponse {
  pregnant_id: string
  gestational_week: string
  axis_mode: string
  series: TrendSeries[]
}

// 随访历史
export interface FollowUpHistoryRecord {
  id: string
  follow_up_date: string | null
  gestational_week: string | null
  status: string
  summary: string | null
  chief_complaint: string | null
  self_reported_data: Record<string, any>
  obstetric_exam: Record<string, any>
  lab_results: Record<string, any>
  classification: string
  health_education: string[]
  guidance_tags: Array<{ tag: string; content: string }>
  referral: Record<string, any> | null
  next_followup_date: string | null
  signature_data?: Record<string, any>
  reviewed_by?: string
  reviewed_at?: string
  review_comment?: string
}

export interface FollowUpHistoryResponse {
  pregnant_id: string
  records: FollowUpHistoryRecord[]
}

// 生化指标趋势
export interface LabTrendDataPoint {
  date: string
  gest_week: number
  value: number | null
  raw_value: string
}

export interface LabTrendItem {
  lab_key: string
  name: string
  unit: string
  normal_low: number | null
  normal_high: number | null
  is_qualitative: boolean
  data_points: LabTrendDataPoint[]
  latest_value: string
  is_normal: boolean | null
}

export interface LabTrendResponse {
  pregnant_id: string
  gestational_week: string
  items: LabTrendItem[]
}

// 随访表单
export interface FollowUpQuestion {
  key: string
  question: string
  type: 'text' | 'number'
  unit?: string
  target?: string
  format?: string
  answered?: boolean
  answer?: any
}

export interface FollowUpPendingResponse {
  record_id: string
  patient_name: string
  template_id: string
  template_name: string
  questions: FollowUpQuestion[]
  answered_count: number
  total_count: number
  has_pending: boolean
  health_education: string[]
}

// ==================== Admin 审计日志类型 ====================

export interface AdminDashboardSummary {
  total_calls: number
  total_tokens: number
  avg_latency_ms: number
  active_sessions: number
}

export interface AdminDailyTrend {
  date: string
  total_tokens: number
  call_count: number
}

export interface AdminVariantDist {
  agent_variant: string
  count: number
  total_tokens: number
}

export interface AdminRecentLog {
  id: number
  session_id: string
  user_id: string
  agent_variant: string
  intent_classification: string | null
  total_tokens: number
  total_latency_ms: number
  guardrail_triggered: boolean
  response_preview: string | null
  created_at: string
}

export interface AdminDashboardResponse {
  summary: AdminDashboardSummary
  daily_trend: AdminDailyTrend[]
  variant_distribution: AdminVariantDist[]
  recent_logs: AdminRecentLog[]
}

export interface AdminTokenDaily {
  date: string
  total_tokens: number
  input_tokens: number
  output_tokens: number
  call_count: number
  avg_latency_ms: number
}

export interface AdminTokenByAgent {
  agent_role: string
  agent_variant: string
  total_tokens: number
  call_count: number
  avg_input_tokens: number
  avg_output_tokens: number
  avg_latency_ms: number
}

export interface AdminSessionItem {
  id: number
  session_id: string
  user_id: string
  agent_role: string
  agent_variant: string
  intent_classification: string | null
  routed_agent: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  total_latency_ms: number
  guardrail_triggered: boolean
  response_preview: string | null
  created_at: string
}

export interface AdminSessionListResponse {
  total: number
  page: number
  page_size: number
  data: AdminSessionItem[]
}

export interface AdminSessionRun {
  id: number
  agent_role: string
  agent_variant: string
  intent_classification: string | null
  routed_agent: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  tool_calls: Array<{ name: string; success: boolean; result_preview: string }> | null
  model_id: string
  total_latency_ms: number
  guardrail_triggered: boolean
  response_preview: string | null
  created_at: string
}

export interface AdminSessionDetail {
  session_id: string
  run_count: number
  runs: AdminSessionRun[]
}

// ==================== 知识库管理类型 ====================

export interface KnowledgeDoc {
  filename: string
  name: string
  extension: string
  size_bytes: number
  size_human: string
  modified_at: string
}

export interface KnowledgeDocListResponse {
  total: number
  data: KnowledgeDoc[]
}

export interface KnowledgeStats {
  enabled: boolean
  document_count: number
  total_size_bytes: number
  total_size_human: string
  embedding_model: string
  embedding_dimensions: number
  search_type: string
  chunk_size: number
  chunk_overlap: number
  chunking_strategy: string
  max_results: number
  reranker_provider: string
  reranker_model: string
  vector_db_table: string
  docs_directory: string
}

export interface RagConfig {
  enabled: boolean
  search_type: string
  chunk_size: number
  chunk_overlap: number
  chunking_strategy: string
  max_results: number
  embedding_model: string
  embedding_dimensions: number
  embedding_api_url: string
  reranker_provider: string
  reranker_model: string
  reranker_base_url: string
  vector_db_table: string
  predefined_tags: string[]
  docs_directory: string
}

export interface RagConfigUpdate {
  search_type?: string
  chunk_size?: number
  chunk_overlap?: number
  chunking_strategy?: string
  max_results?: number
  reranker_provider?: string
  reranker_model?: string
  reranker_base_url?: string
}

export interface KnowledgeSearchResult {
  content: string
  score: number | null
  metadata: Record<string, string>
}

export interface KnowledgeSearchResponse {
  query: string
  filters: Record<string, string>
  results: KnowledgeSearchResult[]
  total: number
}

export interface KnowledgeChunk {
  id: string
  name: string
  content: string
  meta_data: Record<string, any> | null
  filters: Record<string, any> | null
  content_hash: string
  content_id: string
  created_at: string | null
  updated_at: string | null
}

export interface KnowledgeChunkListResponse {
  total: number
  page: number
  page_size: number
  data: KnowledgeChunk[]
  error?: string
}

export interface ChunkDocStat {
  name: string
  chunk_count: number
  min_content_length: number
  max_content_length: number
  avg_content_length: number
}

export interface ChunkStatsResponse {
  total_chunks: number
  documents: ChunkDocStat[]
  error?: string
}

export interface KnowledgeUploadResponse {
  filename: string
  name: string
  size_bytes: number
  size_human: string
  auto_ingest: boolean
  ingested: boolean
  ingest_error?: string
}

export interface KnowledgeIngestResponse {
  message: string
  success: number
  failed: number
  total: number
  errors: Array<{ filename: string; error: string }>
}
