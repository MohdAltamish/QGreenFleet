# context.md — Session Context for AI Assistants

## One-paragraph summary
QGreenFleet predicts ship fuel consumption with a QPSO-tuned XGBoost model trained on EU MRV data (the quantum-inspired part of prediction is the QPSO hyperparameter search) and optimizes fleet deployment (assignment, speed, fuel type, shore power) with a hybrid QIEA+QPSO multi-objective metaheuristic with NSGA-II ranking, minimizing fuel cost, WtW GHG, and opex under demand/schedule/CII/fuel-availability constraints. Benchmarked vs GA (NSGA-II)/MOPSO/SA across 5 to 100 vessels (no MILP baseline). React UI + FastAPI (plus the older Streamlit app) + WeasyPrint PDF reports.

## Current status (update as you go)
- [x] Data pipeline  - [x] Prediction baseline  - [x] Real EU MRV Model  - [x] QIEA core  - [x] QPSO speeds
- [x] Constraints/repair  - [x] Benchmarks (S/M/L/XL complete)  - [x] UI  - [x] Case study  - [x] Dual PDF Report gen

## Headline Validation Metrics
- **Tests**: pytest suite (`pytest -q`).
- **Prediction**: QPSO-XGBoost on EU MRV THETIS 2022–2023 (21,622 ship-years); features speed, EEDI, category; monotone speed constraints; log target; ship-grouped split. Held-out ships: R² 0.524, MAPE 26.3% (ship's own EEDI); EEDI unknown: R² 0.348, MAPE 34.5%; naive category median: R² 0.234, MAPE 36.9%. MAPE target < 10% is not met.
- **Predictor in the optimizer** (`src/prediction/predictor.py`): MRV model level × admiralty speed law (fuel/day ∝ v³, part-load SFOC penalty) × rule-based draft and weather factors. The Kaggle voyage dataset has no learnable signal (all stage-2 models R² ≤ 0). Fleet EEDI estimated from DWT via IMO reference lines (MEPC.231(65)).
- **Benchmark and case-study results**: see docs/case-study-results.md and outputs/benchmark_report.md (generated from the run outputs).
- **Publication Reports**: sample PDFs in `docs/samples/` (regenerate after results change).

## Key decisions log
| Date | Decision | Why |
|---|---|---|
| — | QIEA for discrete + QPSO for continuous | matches variable types; literature-backed |
| — | Exact MILP baseline (HiGHS) planned | not built |
| — | Streamlit MVP first | hackathon speed |
| 2026-09-02 | Dual-report system: technical + executive summary from shared data dict | Serves engineers and managers from one shared data dict |
| 2026-09-03 | Vectorization & offline demo loading | Load pre-computed case-study scenarios without re-running |
| 2026-09-03 | EU MRV prediction model | Grounds predictions in 21,622 MRV ship-years with a ship-grouped split |
| 2026-09-03 | Full-scale benchmark (S/M/L/XL) | Compare QIEA+QPSO vs GA/MOPSO/SA from 5 to 100 vessels; results in outputs/benchmark_report.md |

## Glossary
WtW = well-to-wake; CII = Carbon Intensity Indicator; Q-bit = probabilistic (α,β) encoding; knee point = best trade-off Pareto solution; hypervolume = Pareto quality metric.
