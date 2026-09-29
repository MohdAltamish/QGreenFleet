/**
 * Static-snapshot implementation of the API surface.
 *
 * Used for the published demo build, where no Python backend is reachable. Every
 * response is real output captured from the FastAPI layer (see
 * scratchpad/snapshot.py); the prediction grid is precomputed across the full
 * slider range, so inference stays interactive rather than canned.
 *
 * What genuinely cannot work without a backend is stated in the UI rather than
 * faked: live optimization runs (the Optimize page shows a recorded run) and
 * fleet mutation / PDF downloads (disabled with a note).
 */
// Aliased in vite.config.js: the real capture for the demo build, an empty
// stub for the live app (see IS_STATIC below).
import snapshot from 'qgf-snapshot'

export const IS_STATIC = import.meta.env.VITE_STATIC_SNAPSHOT === '1'

export const recordedRun = snapshot.recordedRun ?? null

/** Embedded data URI for a figure, or null when it was not captured. */
export const staticChartUrl = (name) => snapshot.chartData?.[name] ?? null

class StaticUnavailable extends Error {
  constructor(message) {
    super(message)
    this.name = 'StaticUnavailable'
    this.status = 501
  }
}

const resolve = (value) => Promise.resolve(value)

const grid = snapshot.predictionGrid

/** Nearest grid coordinate, so a slider position always maps onto a cell. */
const nearest = (values, target) =>
  values.reduce((best, v) => (Math.abs(v - target) < Math.abs(best - target) ? v : best), values[0])

function gridLookup(shipType, draft, weather) {
  const d = nearest(grid.drafts, draft)
  const w = nearest(grid.weather, weather)
  // Keys were written with one-decimal drafts (4.0, 4.5, …); JSON parsing drops
  // the trailing zero, so the draft has to be re-formatted to match.
  return grid.values[`${shipType}|${w}|${d.toFixed(1)}`] || null
}

function pointAt(shipType, speed, draft, weather) {
  const cell = gridLookup(shipType, draft, weather)
  if (!cell) return null
  const s = nearest(grid.speeds, speed)
  const [tpd, adjustment] = cell[grid.speeds.indexOf(s)]
  return { tpd, adjustment, speed: s }
}

export const staticApi = {
  health: () => resolve(snapshot.health),
  overview: () => resolve(snapshot.overview),

  fleet: () => resolve(snapshot.fleet),
  fleetFiles: () => resolve(snapshot.fleetFiles),
  fleetBau: () => resolve(snapshot.fleetBau),
  loadFleet: () =>
    Promise.reject(
      new StaticUnavailable(
        'Switching fleets needs the FastAPI backend. This published demo is a static snapshot of the 20-vessel, 5-route case-study fleet.',
      ),
    ),
  generateFleet: () =>
    Promise.reject(
      new StaticUnavailable(
        'Fleet synthesis runs the MRV-calibrated generator in Python, so it needs the FastAPI backend.',
      ),
    ),
  uploadFleetFile: () =>
    Promise.reject(
      new StaticUnavailable('Uploading a fleet needs the FastAPI backend.'),
    ),

  predict: (params) => {
    const hit = pointAt(params.ship_type, params.speed_kn, params.draft_m, params.weather_severity)
    if (!hit) return Promise.reject(new StaticUnavailable('That operating point is outside the captured grid.'))
    const kgPerHour = (hit.tpd * 1000) / 24
    return resolve({
      request: params,
      fuel_tons_per_day: hit.tpd,
      fuel_kg_per_hour: kgPerHour,
      fuel_kg_per_nm: kgPerHour / Math.max(1e-6, params.speed_kn),
      hydrodynamic_adjustment: hit.adjustment,
      model_name: grid.model_name,
      two_stage: grid.two_stage,
    })
  },

  predictCurve: (params) => {
    const series = (params.ship_types || grid.ship_types).map((shipType) => {
      const cell = gridLookup(shipType, params.draft_m, params.weather_severity)
      return {
        ship_type: shipType,
        points: (cell || []).map((v, i) => ({
          speed_kn: grid.speeds[i],
          fuel_tons_per_day: v[0],
        })),
      }
    })
    return resolve({
      draft_m: params.draft_m,
      weather_severity: params.weather_severity,
      model_name: grid.model_name,
      series,
    })
  },

  models: () => resolve(snapshot.models),
  emissionsFactors: () => resolve(snapshot.emissionsFactors),

  scenarios: () => resolve(snapshot.scenarios),
  scenario: (name) => {
    const detail = snapshot.scenarioDetails?.[name]
    return detail
      ? resolve(detail)
      : Promise.reject(new StaticUnavailable(`Scenario '${name}' was not captured in this snapshot.`))
  },
  scenarioReport: () =>
    Promise.reject(new StaticUnavailable('The report builder needs the FastAPI backend.')),
  carbonSweep: () => resolve(snapshot.carbonSweep),

  startOptimization: () =>
    Promise.reject(
      new StaticUnavailable(
        'A live QIEA+QPSO search runs NumPy in Python, so it needs the FastAPI backend. The results below are a recorded run of the real engine.',
      ),
    ),
  job: () => (recordedRun ? resolve(recordedRun) : Promise.reject(new StaticUnavailable('No recorded run.'))),
  jobs: () => resolve({ jobs: recordedRun ? [{ ...recordedRun, result: undefined }] : [] }),
  cancelJob: () => resolve(recordedRun),

  benchmark: () => resolve(snapshot.benchmark),
  reports: () =>
    resolve({
      reports: (snapshot.reports?.reports || []).map((r) => ({ ...r, available: false })),
    }),
  charts: () => resolve(snapshot.charts),
}
