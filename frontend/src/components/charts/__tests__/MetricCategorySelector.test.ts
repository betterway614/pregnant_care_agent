/**
 * MetricCategorySelector 逻辑测试
 * 测试分类切换、指标选择、全选/取消全选等核心逻辑
 * 不挂载 Vue 组件，直接测试状态机逻辑
 */
import { describe, it, expect } from 'vitest'
import {
  CATEGORIES, LAB_CATEGORY, getAllCategories,
  getCategory, getCategoryMetrics,
} from '../../../utils/labelMaps'
import type { IndicatorCategory } from '../../../utils/labelMaps'

// ── 模拟 MetricCategorySelector 的核心状态逻辑 ──

interface SelectorState {
  selected: string[]
  activeCategory: string
  categories: IndicatorCategory[]
}

function createSelectorState(
  initialSelected: string[],
  categoryKeys: string[],
): SelectorState {
  const allCategories = getAllCategories()
  return {
    selected: [...initialSelected],
    activeCategory: categoryKeys[0],
    categories: allCategories.filter(c => categoryKeys.includes(c.key)),
  }
}

function isSelected(state: SelectorState, metric: string): boolean {
  return state.selected.includes(metric)
}

function selectedInCategory(state: SelectorState, cat: IndicatorCategory): string[] {
  return cat.metrics.filter(m => state.selected.includes(m))
}

function isAllSelected(state: SelectorState, cat: IndicatorCategory): boolean {
  return cat.metrics.every(m => state.selected.includes(m))
}

function toggleMetric(state: SelectorState, metric: string, checked: boolean): string[] {
  return checked
    ? [...new Set([...state.selected, metric])]
    : state.selected.filter(m => m !== metric)
}

function toggleAll(state: SelectorState, cat: IndicatorCategory): string[] {
  return isAllSelected(state, cat)
    ? state.selected.filter(m => !cat.metrics.includes(m))
    : [...new Set([...state.selected, ...cat.metrics])]
}

function switchCategory(state: SelectorState, catKey: string): void {
  if (state.categories.some(c => c.key === catKey)) {
    state.activeCategory = catKey
  }
}

/** 模拟 switchToCategory：切换分类时自动全选该分类所有指标 */
function switchToCategory(state: SelectorState, catKey: string): string[] {
  const cat = state.categories.find(c => c.key === catKey)
  if (!cat) return state.selected
  state.activeCategory = catKey
  return [...cat.metrics]
}

describe('MetricCategorySelector 状态逻辑', () => {
  describe('selectAll / deselectAll', () => {
    it('全选血糖分类应将两个血糖指标都加入选中', () => {
      const state = createSelectorState([], ['vital_signs', 'blood_sugar'])
      const sugarCat = getCategory('blood_sugar')!
      const result = toggleAll(state, sugarCat)
      expect(result).toContain('blood_sugar_fasting')
      expect(result).toContain('blood_sugar_postprandial')
    })

    it('已全选后再次全选应取消', () => {
      const state = createSelectorState(
        ['blood_sugar_fasting', 'blood_sugar_postprandial'],
        ['blood_sugar'],
      )
      const sugarCat = getCategory('blood_sugar')!
      const result = toggleAll(state, sugarCat)
      expect(result).not.toContain('blood_sugar_fasting')
      expect(result).not.toContain('blood_sugar_postprandial')
    })

    it('全选不应影响其他分类的已选指标', () => {
      const state = createSelectorState(
        ['weight'],
        ['vital_signs', 'blood_sugar'],
      )
      const sugarCat = getCategory('blood_sugar')!
      const result = toggleAll(state, sugarCat)
      // 体重应保留
      expect(result).toContain('weight')
      // 血糖应被加入
      expect(result).toContain('blood_sugar_fasting')
      expect(result).toContain('blood_sugar_postprandial')
    })

    it('取消全选不应影响其他分类的已选指标', () => {
      const state = createSelectorState(
        ['weight', 'blood_sugar_fasting', 'blood_sugar_postprandial'],
        ['vital_signs', 'blood_sugar'],
      )
      const sugarCat = getCategory('blood_sugar')!
      const result = toggleAll(state, sugarCat)
      // 体重应保留
      expect(result).toContain('weight')
      // 血糖应被移除
      expect(result).not.toContain('blood_sugar_fasting')
      expect(result).not.toContain('blood_sugar_postprandial')
    })
  })

  describe('toggleMetric', () => {
    it('添加指标', () => {
      const state = createSelectorState(['weight'], ['vital_signs'])
      const result = toggleMetric(state, 'systolic', true)
      expect(result).toContain('weight')
      expect(result).toContain('systolic')
    })

    it('移除指标', () => {
      const state = createSelectorState(['weight', 'systolic'], ['vital_signs'])
      const result = toggleMetric(state, 'systolic', false)
      expect(result).toContain('weight')
      expect(result).not.toContain('systolic')
    })

    it('重复添加不应产生重复', () => {
      const state = createSelectorState(['weight'], ['vital_signs'])
      const result = toggleMetric(state, 'weight', true)
      const unique = new Set(result)
      expect(result.length).toBe(unique.size)
    })
  })

  describe('switchCategory', () => {
    it('切换有效分类应更新 activeCategory', () => {
      const state = createSelectorState([], ['vital_signs', 'blood_sugar', 'fetal'])
      switchCategory(state, 'blood_sugar')
      expect(state.activeCategory).toBe('blood_sugar')
    })

    it('切换到无效分类不应改变状态', () => {
      const state = createSelectorState([], ['vital_signs'])
      switchCategory(state, 'nonexistent')
      expect(state.activeCategory).toBe('vital_signs')
    })
  })

  describe('selectedInCategory', () => {
    it('应正确统计各分类已选数', () => {
      const state = createSelectorState(
        ['weight', 'systolic', 'diastolic'],
        ['vital_signs', 'blood_sugar'],
      )
      const vital = getCategory('vital_signs')!
      const sugar = getCategory('blood_sugar')!
      expect(selectedInCategory(state, vital)).toHaveLength(3)
      expect(selectedInCategory(state, sugar)).toHaveLength(0)
    })
  })

  describe('isAllSelected', () => {
    it('血糖分类全选后应返回 true', () => {
      const state = createSelectorState(
        ['blood_sugar_fasting', 'blood_sugar_postprandial'],
        ['blood_sugar'],
      )
      const sugar = getCategory('blood_sugar')!
      expect(isAllSelected(state, sugar)).toBe(true)
    })

    it('部分选择应返回 false', () => {
      const state = createSelectorState(
        ['weight'],
        ['vital_signs'],
      )
      const vital = getCategory('vital_signs')!
      expect(isAllSelected(state, vital)).toBe(false)
    })
  })

  describe('switchToCategory — 切换分类自动全选', () => {
    it('切换分类应全选新分类所有指标', () => {
      const state = createSelectorState(
        ['weight'],
        ['vital_signs', 'blood_sugar'],
      )
      const result = switchToCategory(state, 'blood_sugar')
      expect(result).toContain('blood_sugar_fasting')
      expect(result).toContain('blood_sugar_postprandial')
      expect(result).toHaveLength(2)
    })

    it('切换分类应更新 activeCategory', () => {
      const state = createSelectorState(
        ['weight'],
        ['vital_signs', 'blood_sugar'],
      )
      switchToCategory(state, 'blood_sugar')
      expect(state.activeCategory).toBe('blood_sugar')
    })

    it('切换到无效分类应保留原选中', () => {
      const state = createSelectorState(
        ['weight'],
        ['vital_signs'],
      )
      const result = switchToCategory(state, 'nonexistent')
      expect(result).toEqual(['weight'])
      expect(state.activeCategory).toBe('vital_signs')
    })

    it('切换分类应替换（非追加）之前的选中', () => {
      const state = createSelectorState(
        ['weight', 'systolic', 'diastolic'],
        ['vital_signs', 'blood_sugar'],
      )
      const result = switchToCategory(state, 'blood_sugar')
      // 应该是血糖的两个指标，不包含之前的生命体征指标
      expect(result).toEqual(['blood_sugar_fasting', 'blood_sugar_postprandial'])
    })
  })

  describe('角色差异', () => {
    it('孕妇端不应显示 lab_tests 分类', () => {
      const state = createSelectorState(
        [],
        ['vital_signs', 'blood_sugar', 'daily_tracking', 'fetal'],
      )
      const keys = state.categories.map(c => c.key)
      expect(keys).not.toContain('lab_tests')
    })

    it('医生/护士端应支持 lab_tests 分类', () => {
      const state = createSelectorState(
        [],
        ['vital_signs', 'blood_sugar', 'daily_tracking', 'fetal', 'lab_tests'],
      )
      const keys = state.categories.map(c => c.key)
      expect(keys).toContain('lab_tests')
    })
  })
})
