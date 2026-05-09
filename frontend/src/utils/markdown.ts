/**
 * 轻量 Markdown 渲染器 - 专为聊天场景优化
 * 支持：粗体、斜体、行内代码、代码块、列表、链接、换行
 */
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// 配置 marked
marked.setOptions({
  breaks: true,
  gfm: true,
})

// 自定义渲染器：链接新窗口打开（适配 marked v18 API）
marked.use({
  renderer: {
    link({ href, title, tokens }: { href: string; title?: string | null; tokens: any[] }) {
      const text = this.parser?.parseInline(tokens) || ''
      const titleAttr = title ? ` title="${title}"` : ''
      return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`
    },
  },
})

/**
 * 渲染 Markdown 为安全 HTML
 */
export function renderMarkdown(content: string): string {
  if (!content) return ''
  try {
    const raw = marked.parse(content) as string
    return DOMPurify.sanitize(raw, {
      ADD_TAGS: ['a'],
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
