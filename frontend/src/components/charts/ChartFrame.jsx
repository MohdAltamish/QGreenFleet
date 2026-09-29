import { CHROME } from '../../lib/palette'

/**
 * Shared chart chrome: a measured plot area, hairline solid grid and axes, a
 * legend for two or more series, and tooltip positioning.
 *
 * Gridlines and axis rules are solid one-step-off-surface hairlines — never
 * dashed — and the container height includes the x-axis band so labels are
 * never clipped into a nested scrollbar.
 */
/** Legend — always present for two or more series; a single series gets none. */
export function Legend({ items, marker = 'line' }) {
  if (!items || items.length < 2) return null
  return (
    <div className="chart__legend">
      {items.map((item) => (
        <span key={item.label} className="chart__legend-item">
          <span
            className={`chart__legend-key${marker === 'line' ? ' chart__legend-key--line' : ''}`}
            style={{ background: item.color }}
            aria-hidden="true"
          />
          {item.label}
        </span>
      ))}
    </div>
  )
}

/**
 * Tooltip anchored inside the chart box, flipped away from the right/top edges
 * so it never overflows the card.
 */
export function Tooltip({ x, y, width, head, rows, boxWidth }) {
  const flipX = boxWidth != null && x > boxWidth - 170
  const style = {
    left: flipX ? undefined : x + 14,
    right: flipX ? Math.max(8, boxWidth - x + 14) : undefined,
    top: Math.max(4, y - 12),
    minWidth: width,
  }
  return (
    <div className="chart__tooltip" style={style} role="status">
      {head && <div className="chart__tooltip-head">{head}</div>}
      {rows.map((row) => (
        <div key={row.label} className="chart__tooltip-row">
          <span className="chart__tooltip-key" style={{ background: row.color }} aria-hidden="true" />
          <span className="chart__tooltip-name">{row.label}</span>
          <span className="chart__tooltip-value">{row.value}</span>
        </div>
      ))}
    </div>
  )
}

/** Horizontal gridlines plus the y-axis tick labels. */
export function YAxis({ scale, ticks, format, left, right, title }) {
  return (
    <g aria-hidden="true">
      {ticks.map((t) => {
        const y = scale(t)
        return (
          <g key={t}>
            <line x1={left} x2={right} y1={y} y2={y} stroke={CHROME.grid} strokeWidth={1} />
            <text className="axis-label" x={left - 8} y={y} textAnchor="end" dominantBaseline="middle">
              {format(t)}
            </text>
          </g>
        )
      })}
      {title && (
        <text
          className="axis-title"
          transform={`translate(${12},${(scale.range[0] + scale.range[1]) / 2}) rotate(-90)`}
          textAnchor="middle"
        >
          {title}
        </text>
      )}
    </g>
  )
}

/**
 * Baseline rule plus the x-axis tick labels.
 *
 * When `rotate` is set the labels are tilted and right-anchored instead of
 * being allowed to overlap each other — a collided axis is worse than a tilted
 * one, and the table view carries the same categories unrotated.
 */
export function XAxis({ scale, ticks, format, bottom, title, center, rotate = 0 }) {
  return (
    <g aria-hidden="true">
      <line
        x1={scale.range[0]}
        x2={scale.range[1]}
        y1={bottom}
        y2={bottom}
        stroke={CHROME.axis}
        strokeWidth={1}
      />
      {ticks.map((t, i) => {
        const cx = center ? scale.center(t) : scale(t)
        return (
          <text
            key={`${t}-${i}`}
            className={center ? 'axis-label axis-label--cat' : 'axis-label'}
            x={rotate ? 0 : cx}
            y={rotate ? 0 : bottom + 15}
            transform={rotate ? `translate(${cx},${bottom + 14}) rotate(${-Math.abs(rotate)})` : undefined}
            textAnchor={rotate ? 'end' : 'middle'}
            dominantBaseline={rotate ? 'middle' : undefined}
          >
            {format(t)}
          </text>
        )
      })}
      {title && (
        <text
          className="axis-title"
          x={(scale.range[0] + scale.range[1]) / 2}
          y={bottom + (rotate ? 52 : 34)}
          textAnchor="middle"
        >
          {title}
        </text>
      )}
    </g>
  )
}
