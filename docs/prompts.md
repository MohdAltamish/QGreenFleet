# prompts.md — Reusable AI Prompts

> **Implementation status (current code):** this is a planning document; the plan text below is kept as written. Planned but not built: QiNN / any quantum-inspired neural net (no PyTorch); exact MILP baseline (no Pyomo/HiGHS); PostgreSQL; pymoo/DEAP (all algorithms are from-scratch NumPy); EEXI; interactive route map in the React UI (only the legacy Streamlit Data page has a Folium map); docker compose; AIS data or cross-checking; emission-cap, demand-surge and shore-power-availability scenario levers. The prediction target of MAPE < 10% is **not met**: held-out ships give R² 0.524 / MAPE 26.3% (ship's own EEDI) and R² 0.348 / MAPE 34.5% (EEDI unknown). See README.md for what exists.

## Scaffolding
"Create `src/optimization/qiea.py` implementing the QIEA loop exactly as specified in docs/algorithms.md §1, using the Solution dataclass from individual.py. Vectorized NumPy, seeded RNG, unit tests for rotation gate normalization (α²+β²=1) and archive update."

## Prediction
"Implement `qpso_tuner.py`: QPSO over XGB search space {eta:[0.01,0.3], max_depth:[3,10], subsample:[0.5,1.0], n_estimators:[100,1000]}. Objective: 5-fold CV RMSE. Follow docs/algorithms.md §4."

## Constraints
"Implement C1–C6 from docs/mathematical-model.md in constraints.py: repair for C1/C2/C6, adaptive penalty for C4/C5. Return violations dict. Add tests with a hand-computed 2-vessel example."

## UI
"Build Streamlit page 'Optimize': load configs/*.yaml, run optimizer in a thread, live-update convergence chart via st.empty(), then render Pareto scatter (Z1 vs Z2, hover = solution details) with Plotly."

## Debugging
"Optimization returns empty archive. Instrument: log feasible count per generation, penalty magnitudes vs objective scale, and repair success rate. Suggest fixes."

## Benchmark analysis
"Given outputs/benchmark_results.csv (algo, instance, seed, hypervolume, evals_to_95, time), produce mean±std tables and matplotlib convergence plots per instance."
