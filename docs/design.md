# Design Document

> **Implementation status (current code):** this is a planning document; the plan text below is kept as written. Planned but not built: QiNN / any quantum-inspired neural net (no PyTorch); exact MILP baseline (no Pyomo/HiGHS); PostgreSQL; pymoo/DEAP (all algorithms are from-scratch NumPy); EEXI; interactive route map in the React UI (only the legacy Streamlit Data page has a Folium map); docker compose; AIS data or cross-checking; emission-cap, demand-surge and shore-power-availability scenario levers. The prediction target of MAPE < 10% is **not met**: held-out ships give R² 0.524 / MAPE 26.3% (ship's own EEDI) and R² 0.348 / MAPE 34.5% (EEDI unknown). See README.md for what exists.

## 1. Module Designs

### src/prediction
- `models.py` — PhysicsBaseline (admiralty cubic), RandomForest, XGBoost, QPSO-XGBoost wrappers with a common fit/predict interface
- `qpso_tuner.py` — QPSO over the XGBoost hyperparameter space (no feature mask)
- `mrv_model.py` — QPSO-XGBoost trained on EU MRV THETIS 2022–2023 (21,622 ship-years): features speed, EEDI, ship category; monotone speed constraint; log target; ship-grouped split
- `predictor.py` — `FuelPredictor`: MRV model level × admiralty speed law (fuel/day ∝ v³, with part-load SFOC penalty) × rule-based draft and weather factors; fleet EEDI estimated from DWT via IMO reference lines (MEPC.231(65))
- `train.py`, `calibration.py` — training entry point and calibration helpers
- No QiNN / neural-net model exists (planned only)

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
- CII: attained CII = CO₂ / (DWT·distance), computed in `src/optimization/constraints.py` (no separate `cii.py`)

### src/benchmark
- `baselines.py` — GA (NSGA-II), MOPSO and SA, all from-scratch NumPy (no pymoo; the MILP baseline was not built)
- `metrics.py` — hypervolume, IGD, evaluations-to-95%
- Same evaluation budget for all algorithms on an instance (pop × gens per instance in `configs/benchmark.yaml`)

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
Scenario(fuel_prices, carbon_price) — in code, CII limits are per vessel (`cii_limit`) and fuel/shore-power availability are per-route flags; `emission_cap` and `shore_power_ports` scenario fields were planned, not built

## 3. UI design (Streamlit, 5 pages)
1. **Data** — upload/preview fleet & routes; generate synthetic
2. **Predict** — train/compare models; accuracy table + parity plot
3. **Optimize** — pick scenario config → run → live convergence chart → Pareto scatter (cost vs CO₂e, color = reliability)
4. **Scenarios** — clone scenario, edit sliders (fuel price, cap), side-by-side compare
5. **Report** — select a Pareto solution → dual report preview toggle (Technical Report vs Executive Summary) with dual downloads (`technical.pdf` / `summary.pdf` and markdown exports).

## 4. API design (FastAPI)
Actual endpoints: see docs/api-spec.md (all under `/api`).

## 5. Error handling
Infeasible scenario → return violation report, not crash. Missing weather → default calm-sea values with warning flag.
