/** Scale and tick helpers for the hand-rolled SVG charts. */

/** Linear scale factory mapping a numeric domain onto a pixel range. */
export function linear([d0, d1], [r0, r1]) {
  const span = d1 - d0 || 1
  const scale = (v) => r0 + ((v - d0) / span) * (r1 - r0)
  scale.invert = (p) => d0 + ((p - r0) / (r1 - r0 || 1)) * span
  scale.domain = [d0, d1]
  scale.range = [r0, r1]
  return scale
}

/** Band scale for categorical axes, with the leftover slot width left as air. */
export function band(domain, [r0, r1], { paddingInner = 0.3, paddingOuter = 0.15 } = {}) {
  const n = domain.length || 1
  const step = (r1 - r0) / (n + 2 * paddingOuter - paddingInner)
  const width = step * (1 - paddingInner)
  const scale = (value) => {
    const i = domain.indexOf(value)
    return i < 0 ? r0 : r0 + step * (paddingOuter + i)
  }
  scale.bandwidth = width
  scale.step = step
  scale.center = (value) => scale(value) + width / 2
  // Mirror the linear scale's surface so the shared axis components can read
  // the pixel range and category domain off either kind of scale.
  scale.range = [r0, r1]
  scale.domain = domain
  return scale
}

/** "Nice" round tick values covering a domain, for clean axis labels. */
export function ticks([d0, d1], count = 5) {
  if (!Number.isFinite(d0) || !Number.isFinite(d1)) return []
  if (d0 === d1) return [d0]
  const raw = (d1 - d0) / Math.max(1, count)
  const mag = 10 ** Math.floor(Math.log10(raw))
  const norm = raw / mag
  const step = (norm >= 7.5 ? 10 : norm >= 3.5 ? 5 : norm >= 1.5 ? 2 : 1) * mag
  const start = Math.ceil(d0 / step) * step
  const out = []
  for (let v = start; v <= d1 + step * 1e-9; v += step) out.push(Math.round(v / step) * step)
  return out
}

/** Domain padded by a fraction of its span, optionally anchored at zero. */
export function paddedDomain(values, { pad = 0.08, zeroBase = false } = {}) {
  const clean = values.filter((v) => Number.isFinite(v))
  if (!clean.length) return [0, 1]
  let lo = Math.min(...clean)
  let hi = Math.max(...clean)
  if (zeroBase) lo = Math.min(0, lo)
  if (lo === hi) {
    const bump = Math.abs(lo) * 0.1 || 1
    return [lo - bump, hi + bump]
  }
  const span = hi - lo
  return [zeroBase && lo === 0 ? 0 : lo - span * pad, hi + span * pad]
}

/** SVG path for a polyline through [x, y] pixel pairs. */
export const linePath = (points) =>
  points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ')

/**
 * Rounded-top bar path: 4px radius on the data end, square at the baseline.
 * `horizontal` rounds the right end instead of the top.
 */
export function barPath({ x, y, width, height, radius = 4, horizontal = false }) {
  const r = Math.max(0, Math.min(radius, horizontal ? width : height, (horizontal ? height : width) / 2))
  if (r === 0) return `M${x},${y}h${width}v${height}h${-width}Z`
  if (horizontal) {
    return `M${x},${y}h${width - r}a${r},${r} 0 0 1 ${r},${r}v${height - 2 * r}a${r},${r} 0 0 1 ${-r},${r}h${-(width - r)}Z`
  }
  return `M${x},${y + r}a${r},${r} 0 0 1 ${r},${-r}h${width - 2 * r}a${r},${r} 0 0 1 ${r},${r}v${height - r}h${-width}Z`
}
