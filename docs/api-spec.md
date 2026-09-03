# API Specification (FastAPI)

Base: /api/v1 — OpenAPI at /docs

## POST /predict
Req: {vessel_type, dwt, engine_kw, speed_kn, load_pct, wind_speed?, wave_height?}
Res: {fuel_tpd, model, confidence_interval}

## POST /optimize  → 202
Req: {scenario: {...} | scenario_id, config_overrides?: {...}}
Res: {job_id}

## GET /optimize/{job_id}
Res: {status: running|done|failed, progress, pareto?: [{id, fuel_cost, ghg_tco2e, opex, assignments:[{vessel,route,speed,fuel}], cii_bands}]}

## GET/POST /scenarios
Scenario: {name, fuel_prices:{HFO,LNG,MeOH,H2,NH3}, carbon_price, emission_cap?, shore_power_ports:[...], demand_multiplier}

## GET /report/{solution_id}?type=technical|summary&format=pdf|md
Res: file stream (dual technical or executive summary report in PDF or Markdown format)

## Errors
400 invalid config (field errors listed) · 422 infeasible scenario → {violations:[...]} · 404 unknown id
