# Benchmarking Results & Protocol

## Prediction Benchmarks
- **Evaluated Models**: Physics Baseline (Admiralty cubic), Random Forest, Default XGBoost, QPSO-Tuned XGBoost.
- **Production model**: QPSO-XGBoost on EU MRV THETIS 2022–2023 (21,622 ship-years), features speed, EEDI, category; ship-grouped split (no ship in both train and test).
- **Held-out ships**: R² 0.524, MAPE 26.3% (ship's own EEDI); EEDI unknown: R² 0.348, MAPE 34.5%; naive category median: R² 0.234, MAPE 36.9%. The PRD target of MAPE < 10% is not met.
- The Kaggle voyage dataset has no learnable signal (all stage-2 models R² ≤ 0), so draft and weather are rule-based factors, not learned.

## Optimization Benchmarks
- **Competitors**:
  1. **QIEA+QPSO (Proposed)**: Discrete Q-bit rotation gates + continuous quantum-behaved PSO speeds.
  2. **Genetic Algorithm (GA)**: NSGA-II real-binary hybrid with tournament selection and arithmetic crossover.
  3. **MOPSO**: Multi-Objective Particle Swarm Optimization with sigmoid binary discretization.
  4. **Simulated Annealing (SA)**: Single-solution scalarized search under identical evaluation budget.
- **Fair Protocol**: All algorithms share identical function evaluation budgets, demand repair (`repair()`), CII constraint validation, and penalty functions.
- **Fleet Instances Evaluated**:
  - **Instance S**: 5 vessels, 3 routes (5 random seeds)
  - **Instance M**: 20 vessels, 4 routes (5 random seeds)
  - **Instance L**: 50 vessels, 10 routes (5 random seeds)
  - **Instance XL**: 100 vessels, 15 routes (5 random seeds)
- **Results** (wall time, hypervolume, IGD, feasibility per instance): see docs/case-study-results.md and outputs/benchmark_report.md (generated from the run outputs). No results numbers are copied here because they change when the runs are regenerated.

## Reproduce
```bash
python -m src.benchmark.run_all --config configs/benchmark.yaml
```
Output artifacts generated: `outputs/benchmark_results.csv`, `outputs/benchmark_report.md`, `outputs/hv_boxplot.png`, `outputs/scalability.png`, and `outputs/convergence_*.png`.
