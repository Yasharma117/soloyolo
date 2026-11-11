// The design system's own gate: colors live in src/tokens and nowhere else in the package.
// Run: npm run check -w @soloyolo/design-system (CI runs it).
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const root = new URL('../src', import.meta.url).pathname
const HEX = /['"`]#[0-9a-fA-F]{3,8}['"`]|rgba?\(/
const bad = []
function walk(dir) {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f)
    if (statSync(p).isDirectory()) { if (f !== 'tokens') walk(p); continue }
    if (!/\.(ts|tsx)$/.test(f)) continue
    readFileSync(p, 'utf8').split('\n').forEach((line, i) => { if (HEX.test(line)) bad.push(`${relative(root, p)}:${i + 1}: ${line.trim()}`) })
  }
}
walk(root)
if (bad.length) {
  console.error('Raw colors outside src/tokens (use useTheme().color.* or add a token):\n' + bad.join('\n'))
  process.exit(1)
}
console.log('design-system check passed: every color comes from src/tokens')
