import { pct } from '../lib/format'

/**
 * Stat tile: label · value · optional signed delta · optional footnote.
 *
 * `goodDirection` says which sign is an improvement, so the delta's color
 * reflects meaning rather than arithmetic sign — for fuel cost and emissions a
 * decrease is good, so a rise is shown as a regression.
 */
export function StatTile({
  label,
  value,
  unit,
  delta,
  deltaLabel,
  goodDirection = 'down',
  foot,
  hero = false,
  children,
}) {
  return (
    <div className="stat">
      <div className="stat__label">{label}</div>
      <div className={`stat__value${hero ? ' stat__value--hero' : ''}`}>
        {value}
        {unit && <span className="stat__unit">{unit}</span>}
      </div>
      {delta != null && (
        <Delta value={delta} goodDirection={goodDirection} suffix={deltaLabel} />
      )}
      {foot && <div className="stat__foot">{foot}</div>}
      {children}
    </div>
  )
}

/** Signed percentage chip whose color encodes improvement, not sign. */
export function Delta({ value, goodDirection = 'down', suffix, decimals = 1 }) {
  if (value == null || Number.isNaN(value)) return null
  const flat = Math.abs(value) < 0.05
  const improving = goodDirection === 'down' ? value < 0 : value > 0
  const tone = flat ? 'flat' : improving ? 'good' : 'bad'
  const arrow = flat ? '±' : value > 0 ? '▲' : '▼'
  return (
    <span className={`delta delta--${tone}`}>
      <span aria-hidden="true">{arrow}</span>
      {pct(value, decimals)}
      {suffix && <span className="delta__suffix">{suffix}</span>}
    </span>
  )
}
