/// <reference types="node" />

import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const srcRoot = resolve(currentDir, '..', '..')
const themeCssPath = resolve(srcRoot, 'styles', 'patient-theme.css')
const backgroundSvgPath = resolve(srcRoot, 'assets', 'pregnancy-care-bg.svg')

describe('patient theme background artwork', () => {
  it('uses the pregnancy care SVG as the global patient theme background', () => {
    const css = readFileSync(themeCssPath, 'utf-8')

    expect(css).toContain('pregnancy-care-bg.svg')
    expect(css).toContain('.patient-theme::before')
  })

  it('keeps the pregnancy care background as accessible vector artwork', () => {
    const svg = readFileSync(backgroundSvgPath, 'utf-8')

    expect(svg).toContain('<svg')
    expect(svg).toContain('role="img"')
    expect(svg).toContain('pregnancy-care-background')
  })
})
