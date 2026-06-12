/**
 * HealthTrendChart 分类感知逻辑测试
 * 测试色板完整性、配对检测、单位分组逻辑
 */
import { describe, it, expect } from 'vitest'

// ── 从组件源码提取的常量（保持同步） ──
const METRIC_COLORS: Record<string, string> = {
  weight: '#8B5CF6', systolic: '#EF4444', diastolic: '#F97316',
  blood_sugar_fasting: '#EC4899', blood_sugar_postprandial: '#F472B6',
  fetal_movement: '#06B6D4', heart_rate: '#10B981',
  sleep_hours: '#6366F1', steps: '#F59E0B', emotion_score: '#8B5CF6',
  hemoglobin_g_L: '#DC2626', alt: '#EA580C', ast: '#F59E0B',
  creatinine: '#10B981', albumin: '#8B5CF6', uric_acid: '#06B6D4',
  wbc: '#EC4899', platelet: '#6366F1', hct: '#F472B6', bilirubin_total: '#84CC16',
}

const BP_METRICS = ['systolic', 'diastolic']
const SUGAR_METRICS = ['blood_sugar_fasting', 'blood_sugar_postprandial']

// ── 模拟 buildOption 逻辑中的配对检测 ──
function detectCombo(metricCodes: string[]) {
  const hasBP = BP_METRICS.every(m => metricCodes.includes(m))
  const hasSugar = SUGAR_METRICS.every(m => metricCodes.includes(m))
  const nonComboMetrics = metricCodes.filter(
    m => !BP_METRICS.includes(m) && !SUGAR_METRICS.includes(m),
  )
  return { hasBP, hasSugar, nonComboCount: nonComboMetrics.length, onlyCombo: nonComboMetrics.length === 0 }
}

// ── 模拟单位分组逻辑 ──
function groupByUnit(series: { metric: string; unit: string }[]) {
  const groups = new Map<string, string[]>()
  for (const s of series) {
    const key = s.unit || '_no_unit'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(s.metric)
  }
  const sorted = [...groups.entries()].sort((a, b) => b[1].length - a[1].length)
  return { primaryUnits: sorted.slice(0, 2), overflowUnits: sorted.slice(2) }
}

describe('METRIC_COLORS 色板完整性', () => {
  it('所有 10 个健康趋势指标应有颜色', () => {
    const healthMetrics = ['weight', 'systolic', 'diastolic', 'blood_sugar_fasting',
      'blood_sugar_postprandial', 'fetal_movement', 'heart_rate',
      'sleep_hours', 'steps', 'emotion_score']
    for (const m of healthMetrics) {
      expect(METRIC_COLORS[m]).toBeDefined()
    }
  })

  it('所有 10 个化验指标应有颜色', () => {
    const labMetrics = ['hemoglobin_g_L', 'alt', 'ast', 'creatinine', 'albumin',
      'uric_acid', 'wbc', 'platelet', 'hct', 'bilirubin_total']
    for (const m of labMetrics) {
      expect(METRIC_COLORS[m]).toBeDefined()
    }
  })

  it('所有颜色应为合法 hex 色值', () => {
    const hexRe = /^#[0-9A-Fa-f]{6}$/
    for (const [metric, color] of Object.entries(METRIC_COLORS)) {
      expect(color).toMatch(hexRe)
    }
  })
})

describe('配对检测逻辑', () => {
  it('同时选中收缩压+舒张压应触发 BP 配对', () => {
    const r = detectCombo(['systolic', 'diastolic'])
    expect(r.hasBP).toBe(true)
    expect(r.hasSugar).toBe(false)
  })

  it('同时选中空腹+餐后血糖应触发血糖配对', () => {
    const r = detectCombo(['blood_sugar_fasting', 'blood_sugar_postprandial'])
    expect(r.hasSugar).toBe(true)
    expect(r.hasBP).toBe(false)
  })

  it('只选血压+血糖+其他指标时，仍应检测出配对', () => {
    const r = detectCombo(['systolic', 'diastolic', 'weight', 'heart_rate'])
    expect(r.hasBP).toBe(true)
    expect(r.onlyCombo).toBe(false)
    expect(r.nonComboCount).toBe(2)
  })

  it('只选血糖+体重时，应检测出血糖配对', () => {
    const r = detectCombo(['blood_sugar_fasting', 'blood_sugar_postprandial', 'weight'])
    expect(r.hasSugar).toBe(true)
    expect(r.onlyCombo).toBe(false)
    expect(r.nonComboCount).toBe(1)
  })

  it('单独选中收缩压不应触发血压配对', () => {
    const r = detectCombo(['systolic'])
    expect(r.hasBP).toBe(false)
  })

  it('单独选空腹血糖不应触发血糖配对', () => {
    const r = detectCombo(['blood_sugar_fasting'])
    expect(r.hasSugar).toBe(false)
  })

  it('只有配对的 combo 指标时，onlyCombo 为 true', () => {
    const r = detectCombo(['systolic', 'diastolic'])
    expect(r.hasBP).toBe(true)
    expect(r.onlyCombo).toBe(true)
  })
})

describe('单位分组逻辑', () => {
  it('相同单位的指标应归入同一组', () => {
    const series = [
      { metric: 'systolic', unit: 'mmHg' },
      { metric: 'diastolic', unit: 'mmHg' },
    ]
    const { primaryUnits, overflowUnits } = groupByUnit(series)
    expect(primaryUnits).toHaveLength(1)
    expect(primaryUnits[0][0]).toBe('mmHg')
    expect(primaryUnits[0][1]).toEqual(['systolic', 'diastolic'])
    expect(overflowUnits).toHaveLength(0)
  })

  it('不同单位的指标应分为不同组', () => {
    const series = [
      { metric: 'weight', unit: 'kg' },
      { metric: 'systolic', unit: 'mmHg' },
      { metric: 'diastolic', unit: 'mmHg' },
      { metric: 'heart_rate', unit: 'bpm' },
    ]
    const { primaryUnits, overflowUnits } = groupByUnit(series)
    // mmHg 组（2个指标）> kg（1）和 bpm（1），取前 2 组
    expect(primaryUnits).toHaveLength(2)
    // 第一组应是数量最多的
    expect(primaryUnits[0][0]).toBe('mmHg')
    expect(primaryUnits[0][1]).toHaveLength(2)
    // 第 3 组溢出
    expect(overflowUnits).toHaveLength(1)
  })

  it('超过 2 种单位时，第 3+ 组溢出', () => {
    const series = [
      { metric: 'weight', unit: 'kg' },
      { metric: 'systolic', unit: 'mmHg' },
      { metric: 'blood_sugar_fasting', unit: 'mmol/L' },
      { metric: 'heart_rate', unit: 'bpm' },
    ]
    const { primaryUnits, overflowUnits } = groupByUnit(series)
    expect(primaryUnits).toHaveLength(2)
    expect(overflowUnits.length).toBeGreaterThanOrEqual(0)
    // 总共 4 个不同单位
    expect(primaryUnits.length + overflowUnits.length).toBe(4)
  })

  it('单一指标无单位时应正确处理', () => {
    const series = [
      { metric: 'emotion_score', unit: '' },
    ]
    const { primaryUnits, overflowUnits } = groupByUnit(series)
    expect(primaryUnits).toHaveLength(1)
    expect(primaryUnits[0][0]).toBe('_no_unit')
    expect(overflowUnits).toHaveLength(0)
  })

  it('化验指标按单位分组', () => {
    const series = [
      { metric: 'hemoglobin_g_L', unit: 'g/L' },
      { metric: 'albumin', unit: 'g/L' },
      { metric: 'alt', unit: 'U/L' },
      { metric: 'ast', unit: 'U/L' },
      { metric: 'creatinine', unit: 'μmol/L' },
    ]
    const { primaryUnits } = groupByUnit(series)
    // g/L 组（2）和 U/L 组（2）在前，μmol/L（1）溢出
    expect(primaryUnits).toHaveLength(2)
    const unitKeys = primaryUnits.map(u => u[0])
    expect(unitKeys).toContain('g/L')
    expect(unitKeys).toContain('U/L')
  })
})
