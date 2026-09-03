# Changelog
All notable changes. Format: Keep a Changelog; versioning: 0.x during hackathon.

## [0.3.0] — 2026-09-03
### Added
- **Real-Data EU MRV Prediction Engine (`src/prediction/mrv_model.py`)**:
  - Trained directly on 21,622 statutory EU MRV THETIS annual vessel reports across 13,820 unique IMO vessels.
  - Ship-level 80/20 train/test partition stratified by naval category with 0% IMO overlap (zero data leakage).
  - QPSO hyperparameter-tuned XGBoost achieving **Test R² = 0.5425**, **Test MAPE = 28.50%** (slashed from 54% synthetic baseline), and **Test RMSE = 44.35 kg/nm** across 4,302 out-of-sample ships.
  - Generated empirical parity plot (`outputs/parity_mrv.png`) and comprehensive report (`outputs/mrv_model_report.md`).
- **Two-Stage Hybrid Production Predictor (`src/prediction/predictor.py`)**:
  - Stage 1 (Macro Real-Data Baseline): EU MRV model predicts operational fuel consumption per nm ($\text{kg/nm} \times \text{kn} \times 24 / 1000$).
  - Stage 2 (Micro Hydrodynamic Adjustment): Voyage surrogate computes draft and weather multiplier clipped to $[0.7, 1.3]$.
  - Graceful fallback to single-stage calibrated predictor when MRV pickle is absent.
- **Benchmark Suite Closeout & Scalability (`src/benchmark/`)**:
  - Completed all 72 evaluation runs across instances S (5v), M (20v), L (50v), and XL (100v) for QIEA, GA, MOPSO, and SA.
  - Generated algorithmic scalability plot (`outputs/scalability.png`) demonstrating sub-exponential scaling.
  - Regenerated `outputs/benchmark_report.md` with complete S/M/L/XL tables, mean ± std, winners bolded, and zero `[pending]` markers.
  - Documented empirical QIEA vs GA speedup factors: 1.1–1.4× faster across fleet scales (S, M, L, XL); QIEA converges to strong compromise solutions faster, outperforming GA's broad spread on collinear maritime objectives.
- **Publication-Grade Diagrams & UI Integration**:
  - Generated `charts/architecture_diagram.png` and `charts/data_trust_diagram.png`.
  - Embedded data trust diagram into Technical Report §5 and architecture diagram into §8.
  - Embedded system architecture diagram directly onto the Streamlit platform home page (`ui/app.py`).
- **Final Sample Publication Reports (`docs/samples/`)**:
  - Pre-compiled updated `QGreenFleet_Executive_Summary.pdf` (1.15 MB, 100% Jargon Guard compliant).
  - Pre-compiled updated `QGreenFleet_Technical_Report.pdf` (1.44 MB, full S/M/L/XL table and 13 figures).
  - Test suite expanded to 81/81 passing unit tests (`pytest -q`).

## [0.2.0] — 2026-09-02
### Added
- **Fuel Consumption Prediction Engine (`src/prediction/`)**:
  - Physics-based cubic admiralty baseline (`PhysicsBaseline`).
  - Quantum-behaved Particle Swarm Optimization hyperparameter tuning for XGBoost (`qpso_tune_xgboost`).
  - Calibration factors calibrated against 21,622 verified EU MRV THETIS vessel-years (container: 8.94×, bulk: 4.49×, tanker: 5.55×).
  - High-performance vectorized surrogate (`FuelPredictor.predict_tpd`).
- **Hybrid Multi-Objective Quantum Optimization Engine (`src/optimization/`)**:
  - Probabilistic Q-bit rotation gates (Han & Kim 2002) for discrete routing, vessel assignment, fuel type, and shore power.
  - Quantum-behaved PSO (Sun et al. 2004) with mean-best attractor for continuous cruising speeds.
  - Non-dominated sorting, crowding distance ranking, and elitist external archive.
  - Strict domain repair operators for cargo demand (C1) and speed/schedule feasibility (C2/C6).
- **Benchmarking Suite (`src/benchmark/`)**:
  - Classical baseline algorithms sharing identical evaluation budget and repair operators: NSGA-II GA, MOPSO, and Simulated Annealing.
  - Multi-metric evaluation: Hypervolume (HV), Inverted Generational Distance (IGD), Evaluations to 95% HV, Spread, and Wall-clock execution time.
  - Scalability analysis across fleet instances S (5v), M (20v), L (50v), and XL (100v).
- **Streamlit Decision Support Platform (`ui/`)**:
  - Multi-page dashboard with global state indicators and offline demo loaders.
  - 13-figure Plotly/Matplotlib visualization library (`ui/utils/chart_helpers.py`).
  - Automated Business-As-Usual (BAU) baseline solver (`ui/utils/fleet_loader.py`).
  - Single source of truth data compiler (`ui/utils/report_data.py`).
- **Dual PDF Reporting System (`ui/utils/pdf_export.py`)**:
  - 2-page Executive Summary with strict Jargon Guard verification.
  - 12-page Technical Fleet Optimization Report with comprehensive 13-figure coverage.
  - Pre-compiled publication samples under `docs/samples/`.
- **Case Study Suite (`src/case_study/`)**:
  - End-to-end evaluation of 4 policy scenarios (Baseline, Carbon Tax $100/t, Tightened 2030 CII, Methanol Subsidy -20%).
  - Carbon tax sensitivity sweep discovering clean fuel economic crossover at $85/t-CO₂e.
- **Developer Workflow & Automation**:
  - `Makefile` and `scripts/demo.sh` for fast reproducible commands.
  - 77 passing unit and integration tests (`pytest -q`).

## [0.1.0] — 2026-08-30
### Added
- Repo scaffold, CI pipeline, synthetic data generator v1
