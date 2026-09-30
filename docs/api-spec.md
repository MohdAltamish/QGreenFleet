# API Specification (FastAPI)

Base: `/api` — OpenAPI at `/docs`. Source of truth: `src/api/main.py`, `src/api/schemas.py`.
In the Docker image the same process also serves the built React app for all non-`/api` paths.

## System
- `GET /api/health` · `GET /api/overview`

## Fleet
- `GET /api/fleet` · `GET /api/fleet/files` · `GET /api/fleet/bau`
- `POST /api/fleet/load` {name} · `POST /api/fleet/generate` {vessels, routes, seed} · `POST /api/fleet/upload` · `POST /api/fleet/upload-file`

## Prediction
- `POST /api/predict` {ship_type, speed_kn, draft_m, weather_severity (0–2), route_type, maintenance_status}
- `POST /api/predict/curve` {ship_types, speed_min, speed_max, points, draft_m, weather_severity}
- `GET /api/models`

## Emissions
- `GET /api/emissions/factors`

## Scenarios (pre-computed case-study runs)
- `GET /api/scenarios` · `GET /api/scenarios/{name}` · `GET /api/scenarios/{name}/report` · `GET /api/carbon-sweep`
- Scenarios: baseline, carbon_100, cii_tightened, meoh_subsidized, green_corridor. There are no emission-cap, demand or shore-power-availability parameters.

## Optimization
- `POST /api/optimize` → 202 {job_id}; body: fuel_prices, carbon_price, pop_size, generations, mutation_prob, lambda0, archive_max, seed
- `GET /api/optimize/jobs` · `GET /api/optimize/{job_id}` · `DELETE /api/optimize/{job_id}`

## Benchmark, reports, charts
- `GET /api/benchmark` · `GET /api/reports` · `GET /api/reports/{key}` · `GET /api/charts` · `GET /api/charts/{name}`
