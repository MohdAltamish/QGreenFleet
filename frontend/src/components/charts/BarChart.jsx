import { useState } from 'react'
import { CHROME } from '../../lib/palette'
import { band, barPath, linear, paddedDomain, ticks as makeTicks } from '../../lib/scales'
import { Legend, Tooltip, XAxis, YAxis } from './ChartFrame'
import { clampHeight, useChartWidth } from './useChart'

/**
 * Horizontal bar chart with per-bar hover.
 *
 * Bars are capped at 24px with a 4px rounded data end, square at the baseline.
 * Values are direct-labelled just past the bar end in text ink — never on the
 * fill, whose luminance differs per series and per theme. Each bar's hit area spans the full band,
 * so the target is comfortably larger than the mark.
 *
 * bars: [{ key, label, value, color, note? }]
 */
export function BarChart({ bars, height, formatValue = (v) => v, formatLabel, ariaLabel }) {
  const [ref, width] = useChartWidth()
  const [hover, setHover] = useState(null)

  if (!bars?.length) return <div className="states">No data to plot.</div>

  const M = { top: 6, right: 70, bottom: 34, left: 136 }
  const rowHeight = 40
  const plotHeight = bars.length * rowHeight
  const chartHeight = height ?? plotHeight + M.top + M.bottom

  const labels = bars.map((b) => b.key)
  const yScale = band(labels, [M.top, M.top + plotHeight], { paddingInner: 0.32, paddingOuter: 0.1 })
  const barThickness = Math.min(24, yScale.bandwidth)
  const xMax = Math.max(...bars.map((b) => b.value), 0)
  const x = linear(paddedDomain([0, xMax], { zeroBase: true, pad: 0.02 }), [
    M.left,
    Math.max(M.left + 20, width - M.right),
  ])
  const xTicks = makeTicks(x.domain, Math.min(6, Math.max(2, Math.floor(width / 120))))

  return (
    <div className="chart" ref={ref}>
      <svg viewBox={`0 0 ${width} ${chartHeight}`} role="img" aria-label={ariaLabel}>
        {/* Vertical gridlines behind the bars */}
        <g aria-hidden="true">
          {xTicks.map((t) => (
            <line
              key={t}
              x1={x(t)}
              x2={x(t)}
              y1={M.top}
              y2={M.top + plotHeight}
              stroke={CHROME.grid}
              strokeWidth={1}
            />
          ))}
          <line
            x1={M.left}
            x2={M.left}
            y1={M.top}
            y2={M.top + plotHeight}
            stroke={CHROME.axis}
            strokeWidth={1}
          />
          {xTicks.map((t) => (
            <text
              key={`t-${t}`}
              className="axis-label"
              x={x(t)}
              y={M.top + plotHeight + 16}
              textAnchor="middle"
            >
              {formatValue(t)}
            </text>
          ))}
        </g>

        {bars.map((b) => {
          const yTop = yScale(b.key) + (yScale.bandwidth - barThickness) / 2
          const barWidth = Math.max(0, x(b.value) - x(0))
          const labelText = (formatLabel || formatValue)(b.value)
          return (
            <g
              key={b.key}
              onPointerEnter={() => setHover(b.key)}
              onPointerLeave={() => setHover(null)}
              tabIndex={0}
              onFocus={() => setHover(b.key)}
              onBlur={() => setHover(null)}
              role="listitem"
              aria-label={`${b.label}: ${labelText}`}
            >
              {/* Full-band transparent hit area — larger than the painted mark */}
              <rect
                x={M.left}
                y={yScale(b.key)}
                width={Math.max(1, width - M.right - M.left)}
                height={yScale.bandwidth}
                fill="transparent"
              />
              <path
                className="mark-bar"
                d={barPath({
                  x: x(0),
                  y: yTop,
                  width: barWidth,
                  height: barThickness,
                  horizontal: true,
                })}
                fill={b.color}
                opacity={hover && hover !== b.key ? 0.55 : 1}
              />
              <text
                className="axis-label axis-label--cat"
                x={M.left - 12}
                y={yTop + barThickness / 2}
                textAnchor="end"
                dominantBaseline="middle"
              >
                {b.label}
              </text>
              <text
                className="mark-label mark-dot"
                x={x(b.value) + 8}
                y={yTop + barThickness / 2}
                textAnchor="start"
                dominantBaseline="middle"
              >
                {labelText}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/**
 * Grouped column chart: one group per category, one column per series.
 *
 * A 2px surface gap separates adjacent columns instead of a stroke.
 *
 * groups: [{ key, label }]  series: [{ key, label, color, values: {groupKey: n} }]
 */
export function GroupedColumnChart({
  groups,
  series,
  height: desktopHeight = 260,
  formatValue = (v) => v,
  yLabel,
  ariaLabel,
}) {
  const [ref, width] = useChartWidth()
  const [hover, setHover] = useState(null)
  const height = clampHeight(desktopHeight)

  if (!groups?.length || !series?.length) return <div className="states">No data to plot.</div>

  const groupKeys = groups.map((g) => g.key)
  // Tilt the category labels when the widest one cannot fit in its band.
  const widestLabel = Math.max(...groups.map((g) => g.label.length))
  const approxBand = (width - 78) / groups.length
  const rotate = widestLabel * 6.4 > approxBand ? 28 : 0
  const M = { top: 12, right: 16, bottom: rotate ? 74 : 42, left: 62 }
  const xGroup = band(groupKeys, [M.left, Math.max(M.left + 20, width - M.right)], {
    paddingInner: 0.28,
    paddingOuter: 0.12,
  })
  const GAP = 2
  const colWidth = Math.min(24, (xGroup.bandwidth - GAP * (series.length - 1)) / series.length)

  const values = groups.flatMap((g) => series.map((s) => s.values[g.key]).filter(Number.isFinite))
  const y = linear(paddedDomain(values, { zeroBase: true }), [height - M.bottom, M.top])
  const yTicks = makeTicks(y.domain, 5)

  return (
    <div className="chart" ref={ref}>
      <Legend items={series.map((s) => ({ label: s.label, color: s.color }))} marker="rect" />
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel}>
        <YAxis
          scale={y}
          ticks={yTicks}
          format={formatValue}
          left={M.left}
          right={width - M.right}
          title={yLabel}
        />
        <XAxis
          scale={xGroup}
          ticks={groupKeys}
          format={(k) => groups.find((g) => g.key === k)?.label ?? k}
          bottom={height - M.bottom}
          center
          rotate={rotate}
        />

        {groups.map((g) => {
          const groupStart =
            xGroup(g.key) + (xGroup.bandwidth - (colWidth * series.length + GAP * (series.length - 1))) / 2
          return series.map((s, si) => {
            const value = s.values[g.key]
            if (!Number.isFinite(value)) return null
            const yTop = y(Math.max(0, value))
            const barHeight = Math.abs(y(value) - y(0))
            const id = `${g.key}-${s.key}`
            return (
              <g
                key={id}
                onPointerEnter={() => setHover({ id, group: g, series: s, value })}
                onPointerLeave={() => setHover(null)}
                tabIndex={0}
                onFocus={() => setHover({ id, group: g, series: s, value })}
                onBlur={() => setHover(null)}
                aria-label={`${g.label} ${s.label}: ${formatValue(value)}`}
              >
                <rect
                  x={groupStart + si * (colWidth + GAP) - 3}
                  y={M.top}
                  width={colWidth + 6}
                  height={height - M.bottom - M.top}
                  fill="transparent"
                />
                <path
                  className="mark-col"
                  d={barPath({
                    x: groupStart + si * (colWidth + GAP),
                    y: yTop,
                    width: colWidth,
                    height: Math.max(1, barHeight),
                  })}
                  fill={s.color}
                  opacity={hover && hover.id !== id ? 0.55 : 1}
                />
              </g>
            )
          })
        })}
      </svg>
      {hover && (
        <Tooltip
          x={xGroup.center(hover.group.key)}
          y={y(hover.value)}
          boxWidth={width}
          head={hover.group.label}
          rows={[{ label: hover.series.label, color: hover.series.color, value: formatValue(hover.value) }]}
        />
      )}
    </div>
  )
}
