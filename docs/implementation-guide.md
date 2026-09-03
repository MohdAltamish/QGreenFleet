# Implementation Guide (Deliverable 5)

## 1. Environment
Python 3.11+, `pip install -r requirements.txt`. Optional: Docker (`docker compose up`).

## 2. Data setup
1. Download MRV CSV → `data/raw/mrv.csv`; Kaggle voyage CSV → `data/raw/voyages.csv`
2. `python -m src.data.prepare` → cleaned Parquet in `data/processed/`
3. `python -m src.data.generate_synthetic --vessels 20 --routes 5 --seed 42`

## 3. Train prediction
`python -m src.prediction.train --model all` → metrics table `outputs/prediction_report.md`, best model saved to `models/best.pkl`

## 4. Run optimization
`python -m src.optimization.run --config configs/case_study.yaml`
→ `outputs/pareto.csv`, `outputs/convergence.png`, `outputs/solution_<id>.json`

## 5. Benchmarks
`python -m src.benchmark.run_all --config configs/benchmark.yaml`

## 6. UI / API
`streamlit run ui/app.py` (UI) · `uvicorn src.api.main:app` (API, docs at /docs)

## 7. Config reference (configs/*.yaml)
```yaml
population: 200
generations: 300
theta_start: 0.157   # 0.05π
theta_end: 0.0157
qpso_beta: [1.0, 0.4]
mutation_prob: 0.02
objectives: [fuel_cost, ghg_wtw, opex]
penalty_lambda0: 10.0
seed: 42
```

## 8. Extending
- New fuel: add row in `src/emissions/factors.py`
- New constraint: implement in `constraints.py` + register in `evaluate_all`
- New baseline: subclass `benchmark.baselines.Baseline`
