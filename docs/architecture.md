# System Architecture

## Layers
1. **Data Layer** — loaders for MRV/Kaggle CSVs, synthetic generator, Parquet cache. (`src/data/`)
2. **Prediction Engine** — feature pipeline → models (physics, RF, XGB, QPSO-XGB, QiNN) → registry of best model. (`src/prediction/`)
3. **Emissions & Constraints Library** — WtW factors, CII calculator, constraint evaluators. (`src/emissions/`, `src/optimization/constraints.py`)
4. **Optimization Engine** — QIEA + QPSO hybrid, NSGA-II ranking, repair operators. (`src/optimization/`)
5. **Benchmark Module** — GA/PSO/SA/MILP runners, metrics (hypervolume, IGD), plotting. (`src/benchmark/`)
6. **API** — FastAPI: /predict, /optimize, /scenarios, /report. (`src/api/`)
7. **UI** — Streamlit pages: Data, Predict, Optimize, Scenarios, Reports. (`ui/`)

## Data flow
CSV/synthetic → feature pipeline → trained predictor ƒ(v, s, load, weather)
→ optimizer uses ƒ inside objective evaluation → Pareto set → UI/report.

## Key design decisions
- Predictor is injected into the optimizer as a callable → engines decoupled, mockable in tests
- Config-driven runs (YAML in `configs/`) → reproducibility
- Discrete vars (assignment, fuel) handled by QIEA Q-bits; continuous speed by QPSO; joint individual = (Qbit matrix, speed vector)
- Constraints: repair-first (fix demand/capacity violations), penalty for the rest

## Directory tree
```
qgreenfleet/
├── configs/           # yaml run configs
├── data/              # raw/, processed/, synthetic/
├── src/{data,prediction,optimization,emissions,benchmark,api}/
├── ui/
│   ├── app.py
│   ├── pages/         # 5 pages: Data, Predict, Optimize, Scenarios, Reports
│   └── utils/
│       └── report_data.py  # single source of truth for both report types
├── notebooks/
├── tests/
├── docs/
└── .gitlab-ci.yml
```
