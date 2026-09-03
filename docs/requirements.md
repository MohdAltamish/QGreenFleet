# Requirements Specification

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

## Python dependencies (requirements.txt)
numpy, pandas, scikit-learn, xgboost, torch, pymoo, deap, pyomo, highspy,
fastapi, uvicorn, pydantic, streamlit, plotly, folium, pyarrow, pytest, weasyprint, pyyaml
