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
