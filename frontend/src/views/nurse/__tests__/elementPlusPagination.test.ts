import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { resolve } from 'node:path'

function vueFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = resolve(dir, entry)
    if (statSync(path).isDirectory()) return vueFiles(path)
    return path.endsWith('.vue') ? [path] : []
  })
}

describe('Element Plus pagination compatibility', () => {
  it('uses size instead of deprecated small prop on el-pagination', () => {
    const srcDir = resolve(__dirname, '../../../')
    const offenders = vueFiles(srcDir).flatMap((file) => {
      const content = readFileSync(file, 'utf8')
      const blocks = content.match(/<el-pagination[\s\S]*?\/?>/g) || []
      return blocks
        .filter((block) => /^\s*small\s*$/m.test(block))
        .map(() => file.replace(srcDir, 'src'))
    })

    expect(offenders).toEqual([])
  })
})
