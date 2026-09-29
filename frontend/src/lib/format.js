/** Number, currency and unit formatting shared by every view. */

const nf = (opts) => new Intl.NumberFormat('en-US', opts)

/** Compact currency: $4.2M, $812K, $650. */
export function usd(value, { decimals = 2 } = {}) {
  if (value == null || Number.isNaN(value)) return '—'
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(decimals)}B`
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(decimals)}M`
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`
  return `${sign}$${nf({ maximumFractionDigits: 0 }).format(abs)}`
}

/** Thousands-separated integer, or a fixed number of decimals. */
export function num(value, decimals = 0) {
  if (value == null || Number.isNaN(value)) return '—'
  return nf({ minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value)
}

/** Compact magnitude for axis ticks: 1.2M, 51K, 940. */
export function compact(value, decimals = 1) {
  if (value == null || Number.isNaN(value)) return '—'
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(decimals)}B`
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(decimals)}M`
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(abs >= 1e4 ? 0 : decimals)}K`
  return `${sign}${nf({ maximumFractionDigits: decimals }).format(abs)}`
}

/** Signed percentage: +12.4%, -3.1%. */
export function pct(value, decimals = 1) {
  if (value == null || Number.isNaN(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}%`
}

export function tonnes(value, decimals = 0) {
  return `${num(value, decimals)} t`
}

export function seconds(value) {
  if (value == null) return '—'
  if (value < 60) return `${value.toFixed(1)}s`
  const m = Math.floor(value / 60)
  return `${m}m ${Math.round(value % 60)}s`
}

export function bytes(value) {
  if (value == null) return '—'
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)} MB`
  if (value >= 1e3) return `${(value / 1e3).toFixed(0)} KB`
  return `${value} B`
}

/** Human label for an optimizer fuel code. */
const FUEL_LABELS = {
  HFO: 'HFO',
  LFO: 'LFO',
  MGO: 'MGO',
  LNG_OTTO: 'LNG (Otto)',
  LNG_DIESEL: 'LNG (Diesel)',
  MEOH_GREY: 'Methanol (grey)',
  MEOH_GREEN: 'Methanol (green)',
  H2_GREEN: 'Hydrogen (green)',
  NH3_GREEN: 'Ammonia (green)',
}

export const fuelLabel = (code) => FUEL_LABELS[code] || code

export const titleCase = (s) =>
  String(s || '').replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

const WEATHER = ['Calm (Beaufort 0–3)', 'Moderate (Beaufort 4–5)', 'Rough (Beaufort 6+)']
export const weatherLabel = (severity) => WEATHER[severity] ?? `Severity ${severity}`

/**
 * Swap raw fuel codes for readable names inside a free-text change description.
 *
 * Two backend paths produce these strings — the scenario plan builder and the
 * shared report builder — so the substitution lives here, at the point of
 * display, rather than being duplicated in each of them.
 */
export function humanizeChange(text) {
  if (!text) return text
  return Object.keys(FUEL_LABELS).reduce(
    (acc, code) => acc.replace(new RegExp(`\\b${code}\\b`, 'g'), FUEL_LABELS[code]),
    String(text),
  )
}
