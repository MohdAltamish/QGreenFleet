/**
 * Chart color roles.
 *
 * Every value is a CSS custom property from styles/global.css, so a figure
 * re-themes with the page — there is no second palette to keep in sync and
 * nothing to re-render on a theme switch. The categorical slots are assigned
 * in a fixed order and are never cycled: an entity keeps its hue when a filter
 * removes its neighbours.
 *
 * Slots 1–2 are the brand green and lemon; 3–5 were chosen with the dataviz
 * palette validator so every pair clears CVD ΔE 8 in both themes (worst 8.5
 * dark / 8.4 light). The light-mode lemon sits at 3.0:1 on white, so it is
 * used for marks with direct labels or a table twin, never for text.
 */

export const SERIES = [
  'var(--series-1)',
  'var(--series-2)',
  'var(--series-3)',
  'var(--series-4)',
  'var(--series-5)',
]

export const CHROME = {
  surface: 'var(--surface)',
  grid: 'var(--grid)',
  axis: 'var(--axis)',
  muted: 'var(--text-2)',
  text: 'var(--text)',
}

/** Fuel → fixed categorical slot. Color follows the fuel, never its rank. */
const FUEL_SLOT = {
  HFO: 4,
  LNG_DIESEL: 2,
  MEOH_GREEN: 0,
  H2_GREEN: 1,
  NH3_GREEN: 3,
}

export const fuelColor = (code) => SERIES[FUEL_SLOT[code] ?? 0]

/** Canonical fuel display order, so bar stacks and legends always agree. */
export const FUEL_ORDER = ['HFO', 'LNG_DIESEL', 'MEOH_GREEN', 'H2_GREEN', 'NH3_GREEN']

/** Algorithm → fixed slot for the benchmark charts. */
const ALGO_SLOT = { QIEA: 0, GA: 2, MOPSO: 3, SA: 4 }
export const algoColor = (algo) => SERIES[ALGO_SLOT[algo] ?? 4]

/** Ship type → fixed slot. */
const SHIP_SLOT = { container: 0, bulk: 2, tanker: 3 }
export const shipColor = (type) => SERIES[SHIP_SLOT[type] ?? 0]

/** CII band → status color. Status hues are reserved and never used as series. */
export const ciiColor = (band) =>
  ({ A: 'var(--primary)', B: 'var(--primary)', C: 'var(--warning)', D: 'var(--warning)', E: 'var(--danger)' })[band] ||
  'var(--text-2)'

/** Status tone → icon name, so no state is ever carried by colour alone. */
export const TONE_ICON = { good: 'checkCircle', warning: 'alert', critical: 'xCircle', info: 'info' }
