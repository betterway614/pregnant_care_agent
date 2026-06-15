// @vitest-environment happy-dom
/**
 * OrderDocumentPrint 组件测试 — 医嘱 Markdown 渲染与纯文本兼容
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import OrderDocumentPrint from '../OrderDocumentPrint.vue'

function createWrapper(overrides: Record<string, any> = {}) {
  return mount(OrderDocumentPrint, {
    props: {
      patientName: '测试孕妇',
      gestWeek: '28+3',
      content: '建议每日测血压。',
      orderType: 'standard',
      source: 'AI_RECOMMENDED',
      signatureImage: null,
      signedAt: '2025-06-15T10:00:00',
      ...overrides,
    },
  })
}

// ==================== 纯文本兼容 ====================

describe('纯文本医嘱渲染', () => {
  it('应正常渲染纯文本医嘱内容', () => {
    const wrapper = createWrapper({ content: '建议每2周产检一次，低盐饮食。' })
    const contentEl = wrapper.find('.doc-section__content')
    expect(contentEl.exists()).toBe(true)
    expect(contentEl.text()).toContain('建议每2周产检一次，低盐饮食')
  })

  it('纯文本中的换行应为 <br> 标签', () => {
    const wrapper = createWrapper({ content: '第一行\n第二行' })
    const html = wrapper.find('.doc-section__content').html()
    // marked with breaks:true 会将 \n 转为 <br>
    expect(html).toContain('<br')
  })

  it('纯文本不应包含未转义的 HTML', () => {
    const wrapper = createWrapper({ content: '<script>alert("xss")</script>' })
    const html = wrapper.find('.doc-section__content').html()
    // DOMPurify 应移除或转义 script 标签
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('alert(')
  })
})

// ==================== Markdown 标题渲染 ====================

describe('Markdown 标题渲染', () => {
  it('### 三级标题应渲染为 <h3>', () => {
    const wrapper = createWrapper({ content: '### 用药指导' })
    const html = wrapper.find('.doc-section__content').html()
    expect(html).toContain('<h3')
    expect(html).toContain('用药指导')
    expect(html).not.toContain('###')
  })

  it('## 二级标题应渲染为 <h2>', () => {
    const wrapper = createWrapper({ content: '## 饮食建议' })
    const html = wrapper.find('.doc-section__content').html()
    expect(html).toContain('<h2')
    expect(html).toContain('饮食建议')
  })

  it('多个标题各自正确渲染', () => {
    const content = '### 用药指导\n建议每日服用铁剂。\n### 饮食建议\n增加蛋白质摄入。'
    const wrapper = createWrapper({ content })
    const html = wrapper.find('.doc-section__content').html()
    // 应有2个 h3
    const h3Count = (html.match(/<h3/g) || []).length
    expect(h3Count).toBe(2)
  })
})

// ==================== Markdown 粗体/斜体渲染 ====================

describe('Markdown 粗体和斜体', () => {
  it('**粗体**应渲染为 <strong>', () => {
    const wrapper = createWrapper({ content: '**重要**：请勿擅自停药。' })
    const html = wrapper.find('.doc-section__content').html()
    expect(html).toContain('<strong>')
    expect(html).toContain('重要')
  })

  it('*斜体*应渲染为 <em>', () => {
    const wrapper = createWrapper({ content: '*建议*每日散步30分钟。' })
    const html = wrapper.find('.doc-section__content').html()
    expect(html).toContain('<em>')
    expect(html).toContain('建议')
  })
})

// ==================== Markdown 列表渲染 ====================

describe('Markdown 列表渲染', () => {
  it('- 无序列表应渲染为 <ul><li>', () => {
    const content = '- 每日监测血压\n- 低盐饮食\n- 适量运动'
    const wrapper = createWrapper({ content })
    const html = wrapper.find('.doc-section__content').html()
    expect(html).toContain('<ul')
    expect(html).toContain('<li>')
    // 三条列表项
    const liCount = (html.match(/<li>/g) || []).length
    expect(liCount).toBe(3)
  })

  it('1. 有序列表应渲染为 <ol><li>', () => {
    const content = '1. 空腹血糖监测\n2. 餐后2h血糖监测'
    const wrapper = createWrapper({ content })
    const html = wrapper.find('.doc-section__content').html()
    expect(html).toContain('<ol')
    expect(html).toContain('<li>')
  })
})

// ==================== Markdown 表格渲染 ====================

describe('Markdown 表格渲染', () => {
  it('简单表格应渲染为 <table>', () => {
    const content = '| 项目 | 频率 |\n|------|------|\n| 血压 | 每日 |\n| 血糖 | 每周 |'
    const wrapper = createWrapper({ content })
    const html = wrapper.find('.doc-section__content').html()
    expect(html).toContain('<table')
    expect(html).toContain('<th')
    expect(html).toContain('<td')
    expect(html).toContain('血压')
    expect(html).toContain('每日')
  })
})

// ==================== Markdown 引用块 ====================

describe('Markdown 引用块渲染', () => {
  it('> 引用块应渲染为 <blockquote>', () => {
    const content = '> 以上为医疗建议，具体方案需经主治医生评估后确定。'
    const wrapper = createWrapper({ content })
    const html = wrapper.find('.doc-section__content').html()
    expect(html).toContain('<blockquote')
  })
})

// ==================== 混合内容 ====================

describe('混合 Markdown 内容', () => {
  it('段落 + 列表 + 粗体的混合内容应正确渲染', () => {
    const content = [
      '### 本次医嘱',
      '',
      '请**严格**遵守以下建议：',
      '',
      '- **每日**监测空腹及三餐后2小时血糖',
      '- 低盐低脂饮食，每日盐摄入<6g',
      '- 如出现*头晕、视物模糊*等症状，请**立即**就诊',
      '',
      '> 以上建议基于您28+3周的孕期情况制定。',
    ].join('\n')

    const wrapper = createWrapper({ content })
    const html = wrapper.find('.doc-section__content').html()

    // 标题
    expect(html).toContain('<h3')
    // 粗体
    expect(html).toContain('<strong>严格</strong>')
    // 列表
    expect(html).toContain('<ul')
    // 斜体
    expect(html).toContain('<em>')
    // 引用块
    expect(html).toContain('<blockquote')
    // 不应有原始markdown标记
    expect(html).not.toContain('###')
    expect(html).not.toContain('**')
  })
})

// ==================== 空内容边界 ====================

describe('边界情况', () => {
  it('空字符串应返回空字符串(不做异常渲染)', () => {
    const wrapper = createWrapper({ content: '' })
    const html = wrapper.find('.doc-section__content').html()
    // 空内容不应包含任何异常标记
    expect(wrapper.find('.doc-section__content').exists()).toBe(true)
  })

  it('含有特殊字符的内容不应导致渲染崩溃', () => {
    const content = '建议使用<5g盐/日 & 避免"高糖"食物。'
    const wrapper = createWrapper({ content })
    expect(wrapper.find('.doc-section__content').exists()).toBe(true)
  })
})

// ==================== 组件属性传递 ====================

describe('组件属性传递', () => {
  it('patientName 应正确显示', () => {
    const wrapper = createWrapper({ patientName: '张三' })
    expect(wrapper.text()).toContain('张三')
  })

  it('gestWeek 应正确显示', () => {
    const wrapper = createWrapper({ gestWeek: '32+0' })
    expect(wrapper.text()).toContain('32+0')
  })

  it('orderType 为 standard 时显示"标准医嘱"', () => {
    const wrapper = createWrapper({ orderType: 'standard' })
    expect(wrapper.text()).toContain('标准医嘱')
  })

  it('source 为 AI_RECOMMENDED 时显示"AI辅助生成"', () => {
    const wrapper = createWrapper({ source: 'AI_RECOMMENDED' })
    expect(wrapper.text()).toContain('AI辅助生成')
  })

  it('无签名图片时应显示签名占位符', () => {
    const wrapper = createWrapper({ signatureImage: null })
    expect(wrapper.text()).toContain('医生签名')
  })

  it('有签名图片时应渲染 img', () => {
    const wrapper = createWrapper({
      signatureImage: 'data:image/png;base64,xxx',
    })
    expect(wrapper.find('.doc-signature__img').exists()).toBe(true)
  })
})
