/**
 * Build the published demo as one self-contained HTML file.
 *
 * Vite emits separate CSS/JS assets; an Artifact is a single document, so the
 * bundle and stylesheet are inlined here. The snapshot JSON is already inside
 * the bundle, so the result needs no network at all.
 */
import { execSync } from 'node:child_process'
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

execSync('npx vite build --outDir dist-static', {
  stdio: 'inherit',
  env: { ...process.env, VITE_STATIC_SNAPSHOT: '1' },
})

const assetDir = join('dist-static', 'assets')
const files = readdirSync(assetDir)
const js = files.find((f) => f.endsWith('.js'))
const css = files.find((f) => f.endsWith('.css'))

const cssText = readFileSync(join(assetDir, css), 'utf8')
const jsText = readFileSync(join(assetDir, js), 'utf8')

// Vite's output is an ES module; keep it as one, and guard the closing tag so a
// literal "</script>" inside the bundle cannot terminate the element early.
const html = `<meta charset="utf-8" />
<title>QGreenFleet Dashboard</title>
<style>
${cssText}
</style>
<div id="root"></div>
<script type="module">
${jsText.replace(/<\/script>/gi, '<\\/script>')}
</script>
`

mkdirSync('dist-static', { recursive: true })
const out = join('dist-static', 'qgreenfleet-dashboard.html')
writeFileSync(out, html)
console.log(`\n${out} — ${(Buffer.byteLength(html) / 1e6).toFixed(2)} MB single file`)
