/**
 * labelMaps 分类定义单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  CATEGORIES,
  LAB_CATEGORY,
  getAllCategories,
  getCategory,
  getCategoryMetrics,
  getCategoryByMetric,
  fieldLabel,
  examLabel,
  labLabel,
  triggerSourceLabel,
  ruleIdLabel,
  alertStatusText,
  alertStatusTagType,
  formatRawDetails,
  hasRawDetails,
} from '../labelMaps'
import type { IndicatorCategory } from '../labelMaps'

describe('CATEGORIES 分类定义', () => {
  it('应有 4 个健康趋势分类', () => {
    expect(CATEGORIES).toHaveLength(4)
  })

  it('所有分类应有唯一 key', () => {
    const keys = CATEGORIES.map(c => c.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('生命体征分类应包含体重、血压、心率', () => {
    const cat = CATEGORIES.find(c => c.key === 'vital_signs')!
    expect(cat).toBeDefined()
    expect(cat.metrics).toContain('weight')
    expect(cat.metrics).toContain('systolic')
    expect(cat.metrics).toContain('diastolic')
    expect(cat.metrics).toContain('heart_rate')
  })

  it('生命体征应定义血压配对组', () => {
    const cat = CATEGORIES.find(c => c.key === 'vital_signs')!
    expect(cat.comboGroups).toBeDefined()
    const bpGroup = cat.comboGroups!.find(g => g.name === '血压')
    expect(bpGroup).toBeDefined()
    expect(bpGroup!.metrics).toEqual(['systolic', 'diastolic'])
  })

  it('血糖管理应包含空腹和餐后血糖并配对', () => {
    const cat = CATEGORIES.find(c => c.key === 'blood_sugar')!
    expect(cat.metrics).toHaveLength(2)
    expect(cat.metrics).toContain('blood_sugar_fasting')
    expect(cat.metrics).toContain('blood_sugar_postprandial')
    expect(cat.comboGroups![0].name).toBe('血糖')
  })

  it('生活管理应包含睡眠、步数、情绪', () => {
    const cat = CATEGORIES.find(c => c.key === 'daily_tracking')!
    expect(cat.metrics).toContain('sleep_hours')
    expect(cat.metrics).toContain('steps')
    expect(cat.metrics).toContain('emotion_score')
    // 生活管理不应有配对组
    expect(cat.comboGroups).toBeUndefined()
  })

  it('胎儿监测只有胎动一个指标', () => {
    const cat = CATEGORIES.find(c => c.key === 'fetal')!
    expect(cat.metrics).toEqual(['fetal_movement'])
  })
})

describe('LAB_CATEGORY 化验分类', () => {
  it('应包含 10 个化验指标', () => {
    expect(LAB_CATEGORY.metrics).toHaveLength(10)
  })

  it('所有化验指标应有明确的 key 和中文名', () => {
    for (const m of LAB_CATEGORY.metrics) {
      expect(m).toBeTruthy()
      expect(typeof m).toBe('string')
    }
  })

  it('应有 g/L 组的指标', () => {
    expect(LAB_CATEGORY.metrics).toContain('hemoglobin_g_L')
    expect(LAB_CATEGORY.metrics).toContain('albumin')
  })

  it('应有 U/L 组的指标', () => {
    expect(LAB_CATEGORY.metrics).toContain('alt')
    expect(LAB_CATEGORY.metrics).toContain('ast')
  })

  it('应有 μmol/L 组的指标', () => {
    expect(LAB_CATEGORY.metrics).toContain('creatinine')
    expect(LAB_CATEGORY.metrics).toContain('uric_acid')
    expect(LAB_CATEGORY.metrics).toContain('bilirubin_total')
  })
})

describe('getAllCategories', () => {
  it('应返回 5 个分类（4 健康 + 1 化验）', () => {
    const all = getAllCategories()
    expect(all).toHaveLength(5)
    const keys = all.map(c => c.key)
    expect(keys).toContain('vital_signs')
    expect(keys).toContain('blood_sugar')
    expect(keys).toContain('daily_tracking')
    expect(keys).toContain('fetal')
    expect(keys).toContain('lab_tests')
  })
})

describe('getCategoryMetrics', () => {
  it('应返回生命体征的 4 个指标', () => {
    const metrics = getCategoryMetrics('vital_signs')
    expect(metrics).toHaveLength(4)
  })

  it('lab_tests 应返回 10 个化验指标', () => {
    const metrics = getCategoryMetrics('lab_tests')
    expect(metrics).toHaveLength(10)
  })

  it('不存在的分类应返回空数组', () => {
    const metrics = getCategoryMetrics('nonexistent')
    expect(metrics).toEqual([])
  })
})

describe('getCategory', () => {
  it('应返回正确的分类对象', () => {
    const cat = getCategory('blood_sugar')
    expect(cat).toBeDefined()
    expect(cat!.key).toBe('blood_sugar')
    expect(cat!.name).toBe('血糖管理')
  })

  it('应返回 lab_tests 分类', () => {
    const cat = getCategory('lab_tests')
    expect(cat).toBeDefined()
    expect(cat!.key).toBe('lab_tests')
  })

  it('不存在的分类应返回 undefined', () => {
    expect(getCategory('ghost')).toBeUndefined()
  })
})

describe('getCategoryByMetric', () => {
  it('体重应归入生命体征', () => {
    const cat = getCategoryByMetric('weight')
    expect(cat).toBeDefined()
    expect(cat!.key).toBe('vital_signs')
  })

  it('空腹血糖应归入血糖管理', () => {
    const cat = getCategoryByMetric('blood_sugar_fasting')
    expect(cat!.key).toBe('blood_sugar')
  })

  it('胎动应归入胎儿监测', () => {
    const cat = getCategoryByMetric('fetal_movement')
    expect(cat!.key).toBe('fetal')
  })

  it('血红蛋白应归入化验指标', () => {
    const cat = getCategoryByMetric('hemoglobin_g_L')
    expect(cat!.key).toBe('lab_tests')
  })

  it('不存在的指标应返回 undefined', () => {
    expect(getCategoryByMetric('not_a_metric')).toBeUndefined()
  })
})

describe('分类完整性检查', () => {
  it('所有健康分类的指标不应与化验指标重叠', () => {
    const healthMetrics = new Set(CATEGORIES.flatMap(c => c.metrics))
    const labMetrics = new Set(LAB_CATEGORY.metrics)
    for (const m of healthMetrics) {
      expect(labMetrics.has(m)).toBe(false)
    }
    for (const m of labMetrics) {
      expect(healthMetrics.has(m)).toBe(false)
    }
  })

  it('所有分类的指标不应有重复（跨分类）', () => {
    const allMetrics: string[] = []
    for (const cat of getAllCategories()) {
      allMetrics.push(...cat.metrics)
    }
    expect(new Set(allMetrics).size).toBe(allMetrics.length)
  })

  it('每个分类应有 name, icon, description', () => {
    for (const cat of getAllCategories()) {
      expect(cat.name).toBeTruthy()
      expect(cat.icon).toBeTruthy()
      expect(cat.description).toBeTruthy()
    }
  })
})

describe('fieldLabel 主观数据字段中文映射', () => {
  it('已知字段应返回中文标签', () => {
    expect(fieldLabel('weight')).toBe('体重')
    expect(fieldLabel('bp')).toBe('血压')
    expect(fieldLabel('fetal_movement')).toBe('胎动')
    expect(fieldLabel('sleep_hours')).toBe('睡眠')
    expect(fieldLabel('blood_sugar_fasting')).toBe('空腹血糖')
    expect(fieldLabel('headache')).toBe('头痛')
    expect(fieldLabel('dizziness')).toBe('头晕')
    expect(fieldLabel('mood')).toBe('情绪')
  })

  it('未知 snake_case 字段应尝试词根翻译而非直接返回英文', () => {
    const label = fieldLabel('blood_pressure_level')
    // 应包含中文翻译部分
    expect(label).not.toBe('blood_pressure_level')
    expect(label).toContain('血液')
  })

  it('完全未知的字段应返回可读形式', () => {
    const label = fieldLabel('custom_field_xyz')
    // 不应原样返回 snake_case
    expect(label).not.toBe('custom_field_xyz')
  })
})

describe('examLabel 产科检查字段中文映射', () => {
  it('已知字段应返回中文标签', () => {
    expect(examLabel('fundal_height_cm')).toBe('宫高(cm)')
    expect(examLabel('fetal_heart_rate_bpm')).toBe('胎心率(bpm)')
    expect(examLabel('blood_pressure')).toBe('血压(mmHg)')
    expect(examLabel('cervical_dilation')).toBe('宫口开大')
    expect(examLabel('amniotic_fluid')).toBe('羊水')
  })

  it('未知字段应尝试词根翻译', () => {
    const label = examLabel('fetal_position_custom')
    expect(label).not.toBe('fetal_position_custom')
  })
})

describe('labLabel 生化指标字段中文映射', () => {
  it('已知字段应返回中文标签（含单位）', () => {
    expect(labLabel('hemoglobin_g_L')).toBe('血红蛋白(g/L)')
    expect(labLabel('creatinine')).toBe('肌酐(μmol/L)')
    expect(labLabel('hba1c')).toBe('糖化血红蛋白')
    expect(labLabel('tsh')).toBe('促甲状腺激素')
    expect(labLabel('urine_glucose')).toBe('尿糖')
  })

  it('未知字段应尝试词根翻译', () => {
    const label = labLabel('urine_ketone_custom')
    expect(label).not.toBe('urine_ketone_custom')
  })
})

describe('triggerSourceLabel 触发来源中文映射', () => {
  it('已知来源应返回中文', () => {
    expect(triggerSourceLabel('RULE_ENGINE')).toBe('规则引擎')
    expect(triggerSourceLabel('FGR_ALGORITHM')).toBe('FGR评估算法')
    expect(triggerSourceLabel('MANUAL')).toBe('手动创建')
    expect(triggerSourceLabel('EPDS_SCREENING')).toBe('EPDS心理筛查')
    expect(triggerSourceLabel('AI_ANALYSIS')).toBe('AI分析')
  })

  it('未知来源应返回原始值', () => {
    expect(triggerSourceLabel('UNKNOWN_SOURCE')).toBe('UNKNOWN_SOURCE')
  })

  it('空值应返回 --', () => {
    expect(triggerSourceLabel()).toBe('--')
    expect(triggerSourceLabel('')).toBe('--')
  })
})

describe('ruleIdLabel 规则ID中文映射', () => {
  it('护士端常见规则应返回中文', () => {
    expect(ruleIdLabel('RULE_BP_HIGH')).toBe('血压异常升高')
    expect(ruleIdLabel('RULE_FETAL_DROP')).toBe('胎动显著减少')
    expect(ruleIdLabel('NURSE_AI_ALERT')).toBe('护士AI预警')
  })

  it('医生端扩展规则应返回中文', () => {
    expect(ruleIdLabel('RULE_BP_HIGH_ORANGE')).toBe('血压偏高关注')
    expect(ruleIdLabel('FGR_CRITICAL_RISK')).toBe('FGR极高风险')
    expect(ruleIdLabel('EPDS_HIGH_RISK')).toBe('EPDS心理筛查高风险')
    expect(ruleIdLabel('RULE_EMOTION_CRITICAL')).toBe('情绪评分严重偏低')
  })

  it('未知规则应返回下划线替换后的文本', () => {
    expect(ruleIdLabel('SOME_NEW_RULE')).toBe('SOME NEW RULE')
  })

  it('空值应返回 --', () => {
    expect(ruleIdLabel()).toBe('--')
    expect(ruleIdLabel('')).toBe('--')
  })
})

describe('alertStatusText 预警状态中文文本', () => {
  it('应正确映射各种状态（大小写不敏感）', () => {
    expect(alertStatusText('PENDING')).toBe('待处理')
    expect(alertStatusText('pending')).toBe('待处理')
    expect(alertStatusText('CONFIRMED')).toBe('已确认')
    expect(alertStatusText('ESCALATED')).toBe('已升级(紧急)')
    expect(alertStatusText('DISMISSED')).toBe('已驳回')
    expect(alertStatusText('AUTO_DISMISSED')).toBe('已自动关闭')
  })

  it('未知状态应返回原始值', () => {
    expect(alertStatusText('UNKNOWN')).toBe('UNKNOWN')
  })
})

describe('alertStatusTagType 预警状态Tag颜色', () => {
  it('应正确映射各种状态（大小写不敏感）', () => {
    expect(alertStatusTagType('PENDING')).toBe('warning')
    expect(alertStatusTagType('pending')).toBe('warning')
    expect(alertStatusTagType('ESCALATED')).toBe('danger')
    expect(alertStatusTagType('CONFIRMED')).toBe('success')
    expect(alertStatusTagType('DISMISSED')).toBe('info')
  })

  it('未知状态应返回 info', () => {
    expect(alertStatusTagType('UNKNOWN')).toBe('info')
    expect(alertStatusTagType('')).toBe('info')
  })
})

describe('formatRawDetails / hasRawDetails 原始数据处理', () => {
  it('formatRawDetails 应翻译 key 为中文并排除 llm_analysis', () => {
    const result = JSON.parse(formatRawDetails({
      action: 'ALERT',
      value: 150,
      llm_analysis: 'should be excluded',
    }))
    expect(result).toEqual({ '处理动作': 'ALERT', '数值': 150 })
    expect(result).not.toHaveProperty('llm_analysis')
  })

  it('hasRawDetails 应在仅有 llm_analysis 时返回 false', () => {
    expect(hasRawDetails({ llm_analysis: 'some text' })).toBe(false)
    expect(hasRawDetails({ llm_analysis: 'text', action: 'ALERT' })).toBe(true)
    expect(hasRawDetails(undefined)).toBe(false)
  })
})
