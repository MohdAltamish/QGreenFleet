import { useState } from 'react'
import { CHROME } from '../../lib/palette'
import { linear, paddedDomain, ticks as makeTicks } from '../../lib/scales'
import { Legend, Tooltip, XAxis, YAxis } from './ChartFrame'
import { clampHeight, useChartWidth, usePointer } from './useChart'

const M = { top: 14, right: 22, bottom: 46, left: 66 }

/**
 * Scatter plot for the Pareto trade-off surface.
 *
 * Uses a nearest-point layer rather than per-dot hit boxes, so the pointer only
 * has to be closest to a point instead of landing dead-centre on an 8px dot.
 * Marks are semi-transparent (--scatter-alpha, raised in light mode where a
 * low alpha vanishes on white) so overlapping solutions build up density.
 *
 * points: [{ id, x, y, highlight?, meta? }]
 */
export function ScatterChart({
  points,
  height: desktopHeight = 300,
  xLabel,
  yLabel,
  formatX = (v) => v,
  formatY = (v) => v,
  highlightLabel = 'Recommended',
  baseLabel = 'Pareto solution',
  ariaLabel,
}) {
  const [ref, width] = useChartWidth()
  const { pointer, onMove, onLeave } = usePointer()
  const [focused, setFocused] = useState(null)
  const height = clampHeight(desktopHeight)

  if (!points?.length) return <div className="states">No solutions to plot.</div>

  const x = linear(paddedDomain(points.map((p) => p.x)), [M.left, Math.max(M.left + 20, width - M.right)])
  const y = linear(paddedDomain(points.map((p) => p.y)), [height - M.bottom, M.top])
  const xTicks = makeTicks(x.domain, Math.min(6, Math.max(2, Math.floor(width / 110))))
  const yTicks = makeTicks(y.domain, 5)

  // Nearest-point selection within a generous radius.
  let active = focused
  if (!active && pointer) {
    let best = null
    for (const p of points) {
      const dx = x(p.x) - pointer.x
      const dy = y(p.y) - pointer.y
      const d2 = dx * dx + dy * dy
      if (d2 < 60 * 60 && (!best || d2 < best.d2)) best = { d2, point: p }
    }
    active = best?.point ?? null
  }

  const legend = [
    { label: baseLabel, color: 'var(--series-1)' },
    ...(points.some((p) => p.highlight) ? [{ label: highlightLabel, color: 'var(--series-2)' }] : []),
  ]

  return (
    <div className="chart" ref={ref}>
      <Legend items={legend} marker="rect" />
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={ariaLabel}
        onPointerMove={onMove}
        onPointerLeave={onLeave}
      >
        <YAxis scale={y} ticks={yTicks} format={formatY} left={M.left} right={width - M.right} title={yLabel} />
        <XAxis scale={x} ticks={xTicks} format={formatX} bottom={height - M.bottom} title={xLabel} />

        {points.map((p) => {
          const isActive = active?.id === p.id
          return (
            <g
              key={p.id}
              tabIndex={0}
              onFocus={() => setFocused(p)}
              onBlur={() => setFocused(null)}
              aria-label={`${p.id}: ${xLabel} ${formatX(p.x)}, ${yLabel} ${formatY(p.y)}`}
            >
              {p.highlight ? (
                // A star marks the recommended (knee) solution: shape carries
                // the distinction as well as hue.
                <path
                  className="mark-dot"
                  d={starPath(x(p.x), y(p.y), isActive ? 11 : 9, 4.6)}
                  fill="var(--series-2)"
                  stroke={CHROME.surface}
                  strokeWidth={2}
                />
              ) : (
                <circle
                  className="mark-dot"
                  cx={x(p.x)}
                  cy={y(p.y)}
                  r={isActive ? 7 : 5.5}
                  fill="var(--series-1)"
                  style={{ fillOpacity: isActive ? 1 : 'var(--scatter-alpha)' }}
                  stroke="var(--series-1)"
                  strokeWidth={1}
                />
              )}
            </g>
          )
        })}
      </svg>

      {active && (
        <Tooltip
          x={x(active.x)}
          y={y(active.y)}
          boxWidth={width}
          head={active.id}
          rows={[
            { label: xLabel, color: 'var(--series-1)', value: formatX(active.x) },
            { label: yLabel, color: 'var(--series-3)', value: formatY(active.y) },
            ...(active.meta || []),
          ]}
        />
      )}
    </div>
  )
}

/** Five-pointed star path centred on (cx, cy). */
function starPath(cx, cy, outer, inner) {
  const pts = []
  for (let i = 0; i < 10; i += 1) {
    const r = i % 2 === 0 ? outer : inner
    const a = (Math.PI / 5) * i - Math.PI / 2
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`)
  }
  return `M${pts.join('L')}Z`
}
