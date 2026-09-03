# Fuel Consumption Prediction Benchmark & MRV Report (SIH #26138)

*Updated with Real EU MRV Operational Models (21,622 vessel-years, ship-level zero leakage)*

---

## 1. Statutory EU MRV Operational Model (Production Macro Stage)

Trained directly on **21,622 verified annual vessel reports from the European Union Maritime MRV THETIS database** with strict **ship-level 80/20 train/test partitioning (13,820 unique IMO ships, 0% ship leakage)**.

| Model Architecture | Test R² ↑ | Test MAPE ↓ | Test RMSE (kg/nm) ↓ | 5-Fold CV RMSE | Production Role |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **QPSO-XGBoost (MRV Best)** | **0.5425** | **28.50%** | **44.35** | 49.53 ± 2.00 | **Stage 1 (Macro Baseline)** |
| XGBoost (Default MRV) | 0.5235 | 28.66% | 45.25 | — | Baseline |

### Per-Category Validation Breakdown (4,302 Test Ships)
- **Container**: Test R² = **0.4384** | MAPE = **38.82%** | RMSE = 63.38 kg/nm (N=737)
- **Bulk Carrier**: Test R² = **0.3957** | MAPE = **20.62%** | RMSE = 23.50 kg/nm (N=1,982)
- **Tanker**: Test R² = **0.3494** | MAPE = **33.57%** | RMSE = 52.75 kg/nm (N=1,583)

*Parity Plot: `outputs/parity_mrv.png`*

---

## 2. Micro-Voyage Kaggle Model Comparison (Stage 2 Hydrodynamics)

| Model | 5-Fold CV RMSE (tons/day) | Test RMSE (tons/day) | Test MAPE (%) | Test R² |
| :--- | :--- | :--- | :--- | :--- |
| **PhysicsBaseline** | 3.2767 ± 0.0774 | 3.2555 | 50.73% | -0.0030 |
| **RandomForestModel** | 3.4022 ± 0.1094 | 3.3741 | 51.78% | -0.0774 |
| **XGBoostModel** | 3.6364 ± 0.1306 | 3.6058 | 54.41% | -0.2305 |
| **QPSOXGBoost** | 3.2798 ± 0.0761 | 3.2640 | 50.82% | -0.0082 |

**Selected Best Model:** `PhysicsBaseline` with Test RMSE = `3.2555` tons/day.

## 2. Parity Visualizations

- **PhysicsBaseline**: `outputs/parity_physics.png`
- **RandomForestModel**: `outputs/parity_rf.png`
- **XGBoostModel**: `outputs/parity_xgb.png`
- **QPSOXGBoost**: `outputs/parity_qpso_xgb.png`

## 3. QPSO Hyperparameter Optimization History

| Iteration | Best CV RMSE (tons/day) |
| :--- | :--- |
| 0 | 3.3003 |
| 1 | 3.2990 |
| 2 | 3.2840 |
| 3 | 3.2840 |
| 4 | 3.2840 |
| 5 | 3.2840 |
| 6 | 3.2836 |
| 7 | 3.2836 |
| 8 | 3.2829 |
| 9 | 3.2826 |
| 10 | 3.2823 |
| 11 | 3.2823 |
| 12 | 3.2823 |
| 13 | 3.2823 |
| 14 | 3.2823 |
| 15 | 3.2822 |
| 16 | 3.2821 |
| 17 | 3.2821 |
| 18 | 3.2821 |
| 19 | 3.2821 |
| 20 | 3.2821 |
| 21 | 3.2821 |
| 22 | 3.2821 |
| 23 | 3.2821 |
| 24 | 3.2821 |
| 25 | 3.2821 |

Convergence curve plotted in `outputs/qpso_convergence.png`.