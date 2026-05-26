/**
 * 轻量 Markdown 渲染器 - 专为聊天场景优化
 * 支持：标题、粗体、斜体、删除线、行内代码、代码块、列表、任务列表、
 *       表格、引用块、分割线、链接、图片、换行
 */
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// 配置 marked：启用 GFM（表格、任务列表、删除线等）+ 自动换行转 <br>
marked.setOptions({
  breaks: true,
  gfm: true,
})

// 自定义渲染器：链接新窗口打开 + 图片安全属性
// marked v18.0.3 renderer 使用对象参数 API：每个渲染函数接收单个 token 对象
marked.use({
  renderer: {
    link({ href, title, text }: { href: string; title?: string | null; text: string }) {
      const titleAttr = title ? ` title="${title}"` : ''
      return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`
    },
    image({ href, title, text }: { href: string; title?: string | null; text: string }) {
      const titleAttr = title ? ` title="${title}"` : ''
      return `<img src="${href}" alt="${text}"${titleAttr} loading="lazy" referrerpolicy="no-referrer" />`
    },
  },
})

/**
 * 规范化 AI 生成的 markdown 文本
 * AI 模型输出的 markdown 语法标记（###、*、---、1.）经常缺少前置换行符，
 * 导致 marked 将它们当作普通文字而非块级元素。此函数在解析前修复这些格式问题。
 */
function normalizeMarkdown(content: string): string {
  let result = content
  // 1. 标题标记（### / ## / #）前确保有换行（排除行首已有换行和 C# 等代码场景）
  result = result.replace(/([^\n#])(#{1,3})\s/g, '$1\n$2 ')
  // 2. 水平分割线 --- 前确保有换行
  result = result.replace(/([^\n])---(\s*)$/gm, '$1\n---$2')
  // 3. 无序列表 * + 空格（允许标点与 * 之间有空格，如 "： * 西红柿"）
  result = result.replace(/([一-鿿　-〿＀-￯。！？；：）」】》\.!?;:])\s*(\*)\s/g, '$1\n$2 ')
  // 4. 无序列表 - + 空格 同理
  result = result.replace(/([一-鿿　-〿＀-￯。！？；：）」】》\.!?;:])\s*(-)\s/g, '$1\n$2 ')
  // 5. 有序列表 数字. + 空格（允许标点与数字之间有空格）
  result = result.replace(/([一-鿿　-〿＀-￯。！？；：）」】》])\s*(\d+)\.\s/g, '$1\n$2. ')
  // 6. 冒号后紧跟 ### 的双重保障
  result = result.replace(/([：:])(#{1,3})\s/g, '$1\n$2 ')
  return result
}

/**
 * 渲染 Markdown 为安全 HTML
 */
export function renderMarkdown(content: string): string {
  if (!content) return ''
  try {
    const normalized = normalizeMarkdown(content)
    const raw = marked.parse(normalized) as string
    return DOMPurify.sanitize(raw, {
      ADD_ATTR: ['target', 'rel'],
    })
  } catch {
    return escapeHtml(content).replace(/\n/g, '<br>')
  }
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// ==================== 结构化分析检测与解析 ====================

export interface DifferentialDiagnosisItem {
  condition: string
  supported_by: string
  against: string
  tests_needed: string
}

export interface StructuredAnalysis {
  analysis?: string
  evidence_references?: string[]
  suggested_orders?: string
  risk_summary?: string
  differential_diagnosis?: DifferentialDiagnosisItem[]
  reasoning_chain?: string[]
}

/** 结构化分析特征关键词（用于检测） */
const STRUCTURED_KEYWORDS = [
  'risk_summary', 'differential_diagnosis', 'reasoning_chain',
  'evidence_references', 'suggested_orders',
]

/**
 * 检测内容是否包含 AI 结构化分析数据
 * 支持 JSON 字符串和 Markdown 两种格式
 */
export function isStructuredAnalysis(content: string): boolean {
  if (!content) return false
  // JSON 格式检测
  if (/^\s*\{/.test(content)) {
    try {
      const obj = JSON.parse(content)
      return STRUCTURED_KEYWORDS.some(k => k in obj)
    } catch { /* fall through to markdown check */ }
  }
  // Markdown 格式检测：同时包含"风险摘要"和"鉴别诊断"等标记
  const mdCount = STRUCTURED_KEYWORDS.filter(k => content.includes(k)).length
  const cnCount = ['风险摘要', '鉴别诊断', '推理链', '建议医嘱', '综合分析', '证据引用']
    .filter(k => content.includes(k)).length
  return mdCount >= 2 || cnCount >= 3
}

/**
 * 从文本中解析结构化分析数据
 * 优先尝试 JSON 解析，失败后从 Markdown 中提取
 */
export function parseStructuredAnalysis(content: string): StructuredAnalysis | null {
  if (!content) return null

  // 尝试 JSON 解析
  if (/^\s*\{/.test(content)) {
    try {
      const obj = JSON.parse(content)
      if (STRUCTURED_KEYWORDS.some(k => k in obj)) {
        return normalizeAnalysis(obj)
      }
    } catch { /* fall through */ }
  }

  // 从 Markdown 中提取
  return parseMarkdownAnalysis(content)
}

function normalizeAnalysis(raw: Record<string, any>): StructuredAnalysis {
  const result: StructuredAnalysis = {}
  if (typeof raw.analysis === 'string') result.analysis = raw.analysis
  if (typeof raw.risk_summary === 'string') result.risk_summary = raw.risk_summary
  if (typeof raw.suggested_orders === 'string') result.suggested_orders = raw.suggested_orders
  if (Array.isArray(raw.evidence_references)) result.evidence_references = raw.evidence_references
  if (Array.isArray(raw.reasoning_chain)) result.reasoning_chain = raw.reasoning_chain
  if (Array.isArray(raw.differential_diagnosis)) {
    result.differential_diagnosis = raw.differential_diagnosis.map((d: any) => ({
      condition: d.condition || '',
      supported_by: Array.isArray(d.supported_by) ? d.supported_by.join('；') : (d.supported_by || ''),
      against: Array.isArray(d.against) ? d.against.join('；') : (d.against || ''),
      tests_needed: Array.isArray(d.tests_needed) ? d.tests_needed.join('；') : (d.tests_needed || ''),
    }))
  }
  return result
}

/** 从 ## 标题 到下一个 ## 标题之间提取内容 */
function extractSection(text: string, heading: string): string | undefined {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`^#{1,3}\\s*${escaped}\\s*\\n([\\s\\S]*?)(?=\\n#{1,3}\\s|$)`, 'im')
  const match = text.match(regex)
  return match ? match[1].trim() : undefined
}

function parseMarkdownAnalysis(content: string): StructuredAnalysis | null {
  const result: StructuredAnalysis = {}

  const analysis = extractSection(content, '综合分析')
  const evidence = extractSection(content, '证据引用')
  const orders = extractSection(content, '建议医嘱')
  const risk = extractSection(content, '风险摘要')
  const dxSection = extractSection(content, '鉴别诊断')
  const reasoning = extractSection(content, '推理链')

  if (analysis) result.analysis = analysis
  if (orders) result.suggested_orders = orders
  if (risk) result.risk_summary = risk

  if (evidence) {
    result.evidence_references = evidence
      .split(/\n- /)
      .map(s => s.replace(/^-\s*/, '').trim())
      .filter(Boolean)
  }

  if (reasoning) {
    result.reasoning_chain = reasoning
      .split(/\n\d+\.\s*/)
      .map(s => s.trim())
      .filter(Boolean)
  }

  if (dxSection) {
    result.differential_diagnosis = parseDifferentialDiagnosis(dxSection)
  }

  // 如果什么都没解析到，返回 null
  if (Object.keys(result).length === 0) return null
  return result
}

function parseDifferentialDiagnosis(section: string): DifferentialDiagnosisItem[] {
  const items: DifferentialDiagnosisItem[] = []
  // 匹配 **疾病名**: 支持依据: ...; 排除依据: ...; 需检查: ...
  const entryRegex = /-\s*\*\*(.+?)\*\*\s*[:：]\s*([\s\S]*?)(?=\n-\s*\*\*|$)/g
  let match: RegExpExecArray | null

  while ((match = entryRegex.exec(section)) !== null) {
    const condition = match[1].trim()
    const details = match[2].trim()

    const supportedMatch = details.match(/支持依据\s*[:：]\s*(.+?)(?:;\s*排除依据|$)/)
    const againstMatch = details.match(/排除依据\s*[:：]\s*(.+?)(?:;\s*需检查|$)/)
    const testsMatch = details.match(/需检查\s*[:：]\s*(.+?)$/)

    items.push({
      condition,
      supported_by: supportedMatch ? supportedMatch[1].trim() : '',
      against: againstMatch ? againstMatch[1].trim() : '',
      tests_needed: testsMatch ? testsMatch[1].trim() : '',
    })
  }

  return items
}
