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
