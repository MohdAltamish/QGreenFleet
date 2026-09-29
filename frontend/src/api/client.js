/**
 * Thin fetch wrapper around the QGreenFleet FastAPI backend.
 *
 * In development Vite proxies /api to the uvicorn origin, so requests are
 * same-origin. Set VITE_API_BASE for a production build served separately.
 */

import { IS_STATIC, staticApi, staticChartUrl } from './staticApi'

const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  let response
  try {
    response = await fetch(`${BASE}/api${path}`, {
      method,
      signal,
      headers: body instanceof FormData ? undefined : body ? { 'Content-Type': 'application/json' } : undefined,
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    })
  } catch (cause) {
    if (cause?.name === 'AbortError') throw cause
    throw new ApiError(
      'Cannot reach the QGreenFleet API. Start it with: uvicorn src.api.main:app --port 8000',
      0,
    )
  }

  if (!response.ok) {
    let detail = null
    try {
      detail = (await response.json())?.detail ?? null
    } catch {
      detail = null
    }
    const text = typeof detail === 'string' ? detail : `Request failed (${response.status})`
    throw new ApiError(text, response.status, detail)
  }

  if (response.status === 204) return null
  return response.json()
}

const httpApi = {
  health: () => request('/health'),
  overview: () => request('/overview'),

  fleet: () => request('/fleet'),
  fleetFiles: () => request('/fleet/files'),
  fleetBau: () => request('/fleet/bau'),
  loadFleet: (name) => request('/fleet/load', { method: 'POST', body: { name } }),
  generateFleet: (params) => request('/fleet/generate', { method: 'POST', body: params }),
  uploadFleetFile: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/fleet/upload-file', { method: 'POST', body: form })
  },

  predict: (params) => request('/predict', { method: 'POST', body: params }),
  predictCurve: (params) => request('/predict/curve', { method: 'POST', body: params }),
  models: () => request('/models'),
  emissionsFactors: () => request('/emissions/factors'),

  scenarios: () => request('/scenarios'),
  scenario: (name) => request(`/scenarios/${encodeURIComponent(name)}`),
  scenarioReport: (name) => request(`/scenarios/${encodeURIComponent(name)}/report`),
  carbonSweep: () => request('/carbon-sweep'),

  startOptimization: (config) => request('/optimize', { method: 'POST', body: config }),
  job: (id, { includeResult = true } = {}) =>
    request(`/optimize/${encodeURIComponent(id)}?include_result=${includeResult}`),
  jobs: () => request('/optimize/jobs'),
  cancelJob: (id) => request(`/optimize/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  benchmark: () => request('/benchmark'),
  reports: () => request('/reports'),
  charts: () => request('/charts'),
}

/**
 * The live HTTP client, or the static snapshot client in the published demo
 * build. Pages import `api` and are unaware of which one they got; anything the
 * snapshot cannot do rejects with an explanatory error the UI surfaces.
 */
export const api = IS_STATIC ? staticApi : httpApi

/** True when this build reads a baked-in snapshot instead of a live backend. */
export { IS_STATIC } from './staticApi'

/** Absolute URL of a report PDF, for a plain download link. */
export const reportUrl = (key) => `${BASE}/api/reports/${encodeURIComponent(key)}`

/** Figure source: a backend URL, or an embedded data URI in the static build. */
export const chartUrl = (name) =>
  IS_STATIC ? staticChartUrl(name) : `${BASE}/api/charts/${encodeURIComponent(name)}`
