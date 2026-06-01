export type AgentRole = 'doctor' | 'nurse'
export type Severity = 'danger' | 'warning' | 'info' | 'success'

export interface FabTab {
  name: string
  label: string
}

export interface AnalysisSection {
  key: string
  label: string
  icon: string
  severity: Severity
  scrollTarget?: string
}

export interface ChipOption {
  value: string
  label: string
  icon?: string
  color?: string
}

export const DOCTOR_FAB_TABS: FabTab[] = [
  { name: 'chat', label: '对话' },
  { name: 'analysis', label: '分析' },
  { name: 'report', label: '报告' },
  { name: 'issues', label: '问题' },
]

export const NURSE_FAB_TABS: FabTab[] = [
  { name: 'chat', label: '对话' },
  { name: 'analysis', label: '分析' },
  { name: 'report', label: '上报' },
]

export const DOCTOR_ANALYSIS_SECTIONS: AnalysisSection[] = [
  { key: 'risk_summary', label: '风险总结', icon: 'Warning', severity: 'danger', scrollTarget: 'section-risk_summary' },
  { key: 'analysis', label: '综合分析', icon: 'DataAnalysis', severity: 'info', scrollTarget: 'section-analysis' },
  { key: 'reasoning_chain', label: '推理链', icon: 'Guide', severity: 'info', scrollTarget: 'section-reasoning_chain' },
  { key: 'suggested_orders', label: '建议医嘱', icon: 'Document', severity: 'warning', scrollTarget: 'section-suggested_orders' },
  { key: 'evidence_references', label: '循证参考', icon: 'Reading', severity: 'info', scrollTarget: 'section-evidence_references' },
]

export const NURSE_ANALYSIS_SECTIONS: AnalysisSection[] = [
  { key: 'summary', label: '综合分析', icon: 'DataAnalysis', severity: 'info', scrollTarget: 'section-summary' },
  { key: 'risk_assessment', label: '风险评估', icon: 'Warning', severity: 'danger', scrollTarget: 'section-risk_assessment' },
  { key: 'nursing_suggestions', label: '护理建议', icon: 'FirstAidKit', severity: 'success', scrollTarget: 'section-nursing_suggestions' },
  { key: 'followup_focus', label: '随访重点', icon: 'Calendar', severity: 'info', scrollTarget: 'section-followup_focus' },
]

export const NURSE_REPORT_ISSUE_TYPES: ChipOption[] = [
  { value: 'risk_alert', label: '风险预警', icon: 'Warning' },
  { value: 'abnormal_data', label: '异常数据', icon: 'TrendCharts' },
  { value: 'patient_complaint', label: '患者投诉', icon: 'ChatDotRound' },
  { value: 'other', label: '其他', icon: 'More' },
]

export const PRIORITY_OPTIONS: ChipOption[] = [
  { value: 'low', label: '低', color: '#94a3b8' },
  { value: 'medium', label: '中', color: '#3b82f6' },
  { value: 'high', label: '高', color: '#f97316' },
  { value: 'urgent', label: '紧急', color: '#ef4444' },
]

export const ISSUE_FILTER_OPTIONS: ChipOption[] = [
  { value: 'all', label: '全部' },
  { value: 'pending', label: '待处理' },
  { value: 'resolved', label: '已处理' },
]

export const PRIORITY_LABELS: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
  urgent: '紧急',
}

export const PRIORITY_COLORS: Record<string, string> = {
  low: '#94a3b8',
  medium: '#3b82f6',
  high: '#f97316',
  urgent: '#ef4444',
}

export function getGestationalWeek(days?: number): number {
  return Math.floor((days || 0) / 7)
}

export function formatPatientLabel(
  displayName: string,
  gestationalAgeDays?: number,
  riskTags?: string[],
): string {
  const week = getGestationalWeek(gestationalAgeDays)
  const risk = riskTags?.length ? ` [${riskTags.join(',')}]` : ''
  return `${displayName} (孕${week}周)${risk}`
}
