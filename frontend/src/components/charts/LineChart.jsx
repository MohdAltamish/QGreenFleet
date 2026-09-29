import { CHROME } from '../../lib/palette'
import { linear, linePath, paddedDomain, ticks as makeTicks } from '../../lib/scales'
import { Legend, Tooltip, XAxis, YAxis } from './ChartFrame'
import { clampHeight, useChartWidth, usePointer } from './useChart'

const M = { top: 12, right: 22, bottom: 42, left: 62 }

/**
 * Multi-series line chart with a snapping crosshair.
 *
 * The crosshair finds the nearest x position and the readout lists every
 * series there, so the pointer never has to land on a 2px stroke. One y-axis
 * only — series with incompatible scales belong in separate charts.
 *
 * series: [{ key, label, color, points: [{ x, y }] }]
 */
export function LineChart({
  series,
  height: desktopHeight = 240,
  xLabel,
  yLabel,
  formatX = (v) => v,
  formatY = (v) => v,
  formatValue,
  zeroBase = false,
  labelLast = false,
  ariaLabel,
}) {
  const [ref, width] = useChartWidth()
  const { pointer, onMove, onLeave } = usePointer()
  const height = clampHeight(desktopHeight)

  const all = series.flatMap((s) => s.points)
  if (!all.length) return <div className="states">No data to plot.</div>

  const xs = all.map((p) => p.x)
  const x = linear([Math.min(...xs), Math.max(...xs)], [M.left, Math.max(M.left + 10, width - M.right)])
  const y = linear(paddedDomain(all.map((p) => p.y), { zeroBase }), [height - M.bottom, M.top])
  const yTicks = makeTicks(y.domain, 5)
  const xTicks = makeTicks(x.domain, Math.min(7, Math.max(2, Math.floor(width / 90))))
  const fmtVal = formatValue || formatY

  // Snap the crosshair to the x position nearest the pointer.
  let active = null
  if (pointer && pointer.x >= M.left - 6 && pointer.x <= width - M.right + 6) {
    const target = x.invert(pointer.x)
    const reference = series[0]?.points || []
    let best = null
    for (const p of reference) {
      const d = Math.abs(p.x - target)
      if (!best || d < best.d) best = { d, xValue: p.x }
    }
    if (best) {
      active = {
        xValue: best.xValue,
        px: x(best.xValue),
        rows: series
          .map((s) => {
            const point = s.points.find((p) => p.x === best.xValue)
            return point == null
              ? null
              : { label: s.label, color: s.color, value: fmtVal(point.y), py: y(point.y) }
          })
          .filter(Boolean),
      }
    }
  }

  return (
    <div className="chart" ref={ref}>
      <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} marker="line" />
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={ariaLabel}
        onPointerMove={onMove}
        onPointerLeave={onLeave}
      >
        <YAxis scale={y} ticks={yTicks} format={formatY} left={M.left} right={width - M.right} title={yLabel} />
        <XAxis scale={x} ticks={xTicks} format={formatX} bottom={height - M.bottom} title={xLabel} />

        {active && (
          <line
            x1={active.px}
            x2={active.px}
            y1={M.top}
            y2={height - M.bottom}
            stroke={CHROME.axis}
            strokeWidth={1}
          />
        )}

        {series.map((s) => (
          <g key={s.key}>
            <path
              className="mark-line"
              d={linePath(s.points.map((p) => [x(p.x), y(p.y)]))}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {/* End marker with a 2px surface ring, so crossings stay legible */}
            {s.points.length > 0 && (
              <circle
                className="mark-dot"
                cx={x(s.points[s.points.length - 1].x)}
                cy={y(s.points[s.points.length - 1].y)}
                r={4}
                fill={s.color}
                stroke={CHROME.surface}
                strokeWidth={2}
              />
            )}
          </g>
        ))}

        {/* Selective direct labels: the endpoint only, never every point */}
        {labelLast &&
          series.map((s) => {
            const last = s.points[s.points.length - 1]
            if (!last) return null
            return (
              <text
                key={`lbl-${s.key}`}
                className="mark-label mark-dot"
                x={x(last.x) - 10}
                y={y(last.y) - 12}
                textAnchor="end"
              >
                {fmtVal(last.y)}
              </text>
            )
          })}

        {active?.rows.map((row) => (
          <circle
            key={row.label}
            cx={active.px}
            cy={row.py}
            r={4}
            fill={row.color}
            stroke={CHROME.surface}
            strokeWidth={2}
          />
        ))}
      </svg>

      {active && active.rows.length > 0 && (
        <Tooltip
          x={active.px}
          y={pointer.y}
          boxWidth={width}
          head={`${xLabel ? `${xLabel}: ` : ''}${formatX(active.xValue)}`}
          rows={active.rows}
        />
      )}
    </div>
  )
}
