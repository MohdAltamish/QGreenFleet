# Design Document

## 1. Module Designs

### src/prediction
- `features.py` — FeaturePipeline: speed, speed², speed³, draft%, wind_speed, wave_height, vessel_type (one-hot), DWT, engine_kW
- `physics.py` — Admiralty baseline: fuel = k · Δ^(2/3) · V³ / C
- `models.py` — sklearn/XGB wrappers with common fit/predict/metrics interface
- `qinn.py` — Quantum-Inspired NN: neurons parameterized as rotation angles θ; activation = sin²(θ_in + Σw·x); trained with Adam
- `qpso_tuner.py` — QPSO over XGB hyperparameter space (eta, depth, subsample, n_estimators) + binary feature mask
- Interface: `Predictor.predict(vessel, speed, load, weather) -> tons/day`

### src/optimization
- `individual.py` — Solution = {Q: Qbit[V×(R+F)], speeds: float[V×R]}; observe() collapses Q to binary decisions
- `qiea.py` — population of Q-individuals; per generation: observe → repair → evaluate → Pareto rank → rotation-gate update toward archive leaders; Δθ: 0.05π→0.005π linear decay; quantum mutation prob 0.02
- `qpso.py` — speeds update: p = φ·pbest+(1−φ)·gbest; x = p ± β·|mbest−x|·ln(1/u); β: 1.0→0.4
- `pareto.py` — fast nondominated sort + crowding distance; external archive (max 100)
- `constraints.py` — evaluate_all(sol) -> violations dict; repair(sol): greedy reassign until demand met, clip speeds to schedule-feasible range
- `objectives.py` — fuel_cost(sol, predictor, prices), ghg_wtw(sol, factors), opex(sol)
- `runner.py` — orchestrates; emits history for convergence plots

### src/emissions
- `factors.py` — WtW gCO2e/MJ + LHV MJ/kg per fuel {HFO, LNG, MeOH, H2_green, NH3_green}
- `cii.py` — attained CII = CO₂ / (DWT·distance); band lookup per year

### src/benchmark
- `baselines.py` — GA & PSO via pymoo, SA custom, MILP via Pyomo+HiGHS (linearized speed grid, ≤10 vessels)
- `metrics.py` — hypervolume, IGD, time-to-95%
- Same evaluation budget for all: 200 pop × 300 gens (configurable)

### ui/utils
- `report_data.py` — Single source of truth for both report types; extracts structured KPI deltas (BAU vs knee solution), fleet deployment tables, emissions breakdown, and sensitivity data.
- Chart Inventory (13 figures for dual reports):
  1. `kpi_bars.png` — BAU vs Optimized side-by-side KPI comparison
  2. `pareto_scatter.png` — Fuel cost vs WtW GHG scatter with OPEX size and knee star
  3. `fleet_map.png` — Geographic vessel-route allocation arcs colored by fuel
  4. `speed_dumbbell.png` — Per-vessel speed changes (BAU vs optimized)
  5. `ghg_waterfall.png` — Emissions abatement waterfall (slow steaming, fuel switch, shore power)
  6. `fuel_mix_donut.png` — Energy share by fuel type
  7. `parity_physics.png` — Predicted vs actual parity plot for predictive surrogate
  8. `speed_fuel_curve.png` — Calibrated cubic fuel vs speed curves by ship type
  9. `calibration_check.png` — Kaggle-derived vs real EU MRV fuel-per-nm distributions
  10. `convergence_S.png` — Multi-algorithm convergence curves (mean ± std over seeds)
  11. `hv_boxplot.png` — Hypervolume distribution across seeds per algorithm
  12. `carbon_sweep.png` — Fuel mix sensitivity vs carbon price ($0–$200/t)
  13. `algorithm_diagram.png` — QIEA+QPSO hybrid loop architecture

## 2. Data model (core dataclasses)
Vessel(id, type, dwt, capacity_teu, engine_kw, design_speed, fuels_allowed)
Route(id, distance_nm, port_from, port_to, schedule_days, demand_teu)
Scenario(fuel_prices, emission_cap, shore_power_ports, carbon_price)

## 3. UI design (Streamlit, 5 pages)
1. **Data** — upload/preview fleet & routes; generate synthetic
2. **Predict** — train/compare models; accuracy table + parity plot
3. **Optimize** — pick scenario config → run → live convergence chart → Pareto scatter (cost vs CO₂e, color = reliability)
4. **Scenarios** — clone scenario, edit sliders (fuel price, cap), side-by-side compare
5. **Report** — select a Pareto solution → dual report preview toggle (Technical Report vs Executive Summary) with dual downloads (`technical.pdf` / `summary.pdf` and markdown exports).

## 4. API design (FastAPI)
- POST /predict {vessel, speed, load, weather} → tons/day
- POST /optimize {scenario_id|inline config} → job_id; GET /optimize/{job_id} → Pareto set
- GET /scenarios, POST /scenarios
- GET /report/{solution_id}.pdf

## 5. Error handling
Infeasible scenario → return violation report, not crash. Missing weather → default calm-sea values with warning flag.
