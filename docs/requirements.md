# Requirements Specification

> **Implementation status (current code):** this is a planning document; the plan text below is kept as written. Planned but not built: QiNN / any quantum-inspired neural net (no PyTorch); exact MILP baseline (no Pyomo/HiGHS); PostgreSQL; pymoo/DEAP (all algorithms are from-scratch NumPy); EEXI; interactive route map in the React UI (only the legacy Streamlit Data page has a Folium map); docker compose; AIS data or cross-checking; emission-cap, demand-surge and shore-power-availability scenario levers. The prediction target of MAPE < 10% is **not met**: held-out ships give R² 0.524 / MAPE 26.3% (ship's own EEDI) and R² 0.348 / MAPE 34.5% (EEDI unknown). See README.md for what exists.

## Functional Requirements
- FR1: Ingest vessel data (type, DWT, engine kW, capacity), route data (distance, ports), demand matrix
- FR2: Train fuel prediction models: physics baseline, RF, XGBoost, QPSO-XGB, QiNN
- FR3: Report RMSE/MAPE/R² per model and per vessel type; persist best model
- FR4: Encode fleet decisions: x[v,r]∈{0,1}, s[v,r]∈[Vmin,Vmax], f[v]∈{HFO,LNG,MeOH,H2,NH3}, sp[v,p]∈{0,1}
- FR5: Evaluate objectives: fuel cost, WtW GHG, opex; using the trained prediction model
- FR6: Enforce constraints: cargo demand, schedule window, CII band, capacity, fuel availability; via repair + penalty
- FR7: Run QIEA (discrete) + QPSO (continuous) with NSGA-II Pareto ranking; output nondominated set
- FR8: Run baselines (GA, PSO, SA, MILP small-instance) under identical budgets
- FR9: Scenario engine: modify fuel prices, emission caps, demand, shore power availability; diff results
- FR10: UI: scenario builder, Pareto explorer, fleet allocation table/map, emission profile charts
- FR11: Generate PDF/Markdown report of a selected plan
- FR12: Synthetic fleet generator calibrated to EU MRV statistics (10–200 vessels)

## Non-Functional Requirements
- NFR1: 200-vessel instance optimized < 10 min on laptop (8-core)
- NFR2: All experiments reproducible (fixed seed, config-driven)
- NFR3: Test coverage ≥ 70% on src/optimization and src/emissions
- NFR4: Every equation in docs/mathematical-model.md implemented and unit-tested

## Data Requirements
- EU MRV THETIS annual dataset (CSV) — real consumption per ship
- Kaggle voyage-level fuel dataset — speed/load/weather granularity
- IMO 4th GHG Study WtW emission factors — emissions library

## Python dependencies (planned list; actual list is requirements.txt)
Planned: numpy, pandas, scikit-learn, xgboost, torch, pymoo, deap, pyomo, highspy,
fastapi, uvicorn, pydantic, streamlit, plotly, folium, pyarrow, pytest, weasyprint, pyyaml.
Not in requirements.txt (not used): torch, pymoo, deap, pyomo, highspy.
