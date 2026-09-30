# Implementation Guide (Deliverable 5)

## 1. Environment
Python 3.11+, `pip install -r requirements.txt`. Optional: Docker (`docker build -t qgreenfleet . && docker run -p 7860:7860 qgreenfleet`; see docs/deployment.md). There is no docker compose file.

## 2. Data setup
1. Download MRV Excel exports → `data/raw/mrv_<year>.xlsx` (the shipped model uses 2022 and 2023); Kaggle ship performance CSV → `data/raw/ship_performance.csv`
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
`make dev` (FastAPI on :8000 + React on :5173; API docs at /docs) · older Streamlit app: `make demo`

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
- New baseline: add a class with a `run(...)` method in `src/benchmark/baselines.py` (like `GeneticAlgorithm`, `MOPSO`, `SimulatedAnnealing`) and register it in `src/benchmark/run_all.py`
