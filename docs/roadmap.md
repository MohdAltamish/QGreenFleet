# Roadmap

> **Implementation status (current code):** this is a planning document; the plan text below is kept as written. Planned but not built: QiNN / any quantum-inspired neural net (no PyTorch); exact MILP baseline (no Pyomo/HiGHS); PostgreSQL; pymoo/DEAP (all algorithms are from-scratch NumPy); EEXI; interactive route map in the React UI (only the legacy Streamlit Data page has a Folium map); docker compose; AIS data or cross-checking; emission-cap, demand-surge and shore-power-availability scenario levers. The prediction target of MAPE < 10% is **not met**: held-out ships give R² 0.524 / MAPE 26.3% (ship's own EEDI) and R² 0.348 / MAPE 34.5% (EEDI unknown). See README.md for what exists.

## Phase 1 — Foundation (Week 1)
Data pipeline (MRV+Kaggle), EDA notebook, physics + XGBoost baselines, synthetic generator v1, repo/CI setup
**Exit:** MAPE baseline number; toy instance defined

## Phase 2 — Quantum core (Week 2)
QIEA + QPSO + Pareto archive, constraints/repair, QPSO-XGB + QiNN, math model doc finalized
**Exit:** Pareto front on 5v/3r toy verified vs MILP

## Phase 3 — Benchmark & scale (Week 3)
GA/MOPSO/SA/MILP baselines, metric suite, 10-seed runs on S–XXL, scalability tuning (vectorization)
**Exit:** convergence + HV plots showing our advantage

## Phase 4 — Platform & demo (Week 4)
Streamlit 5 pages, FastAPI, scenario engine, PDF reports, 20-vessel case study, demo video, implementation guide
**Exit:** end-to-end live demo < 10 min

## Stretch
React UI, AIS+weather joined dataset, EU ETS module depth, Docker deploy
