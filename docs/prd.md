# Product Requirements Document — QGreenFleet

## 1. Purpose
A decision support platform for green fleet management that predicts fuel consumption and optimizes fleet deployment using quantum-inspired algorithms.

## 2. Users & Personas
- **Fleet Planner (primary):** sets fleet, routes, demand; wants min-cost/emission deployment plan
- **Sustainability Officer:** needs CII compliance and lifecycle GHG reports
- **Analyst/Judge:** runs scenarios and benchmarks

## 3. Goals / Success Metrics
| Goal | Metric | Target |
|---|---|---|
| Accurate prediction | MAPE | < 10% on test set |
| Better optimization | Hypervolume vs GA/PSO | ≥ +10% |
| Faster convergence | Generations to 95% best | ≤ 0.7× GA |
| Scale | 200 vessels solvable | < 10 min |
| Usability | Scenario run end-to-end from UI | < 5 clicks |

## 4. Features (MoSCoW)
**Must:** prediction model + accuracy report; MINLP formulation; QIEA/QPSO engine; Pareto front output; constraint handling (demand, schedule, CII); alt-fuel scenarios; benchmark suite; Streamlit UI; case study; dual PDF reports (technical + executive summary).
**Should:** fleet map visualization, fuel-price sensitivity sliders.
**Could:** REST API, React UI, AIS-weather joined dataset, carbon price (EU ETS) module.
**Won't (v1):** real-time AIS ingestion, weather routing, port scheduling.

## 5. User Stories
1. As a planner, I upload/select a fleet + routes + demand and get a Pareto set of deployment plans.
2. As a planner, I pick a plan and see per-vessel assignment, speed, fuel type, cost, CO₂e.
3. As a sustainability officer, I set an emission cap and see the cost of compliance.
4. As an analyst, I toggle fuel prices/availability and compare scenarios side by side.
5. As a judge, I run `make benchmark` and see convergence plots vs baselines.

## 6. Non-functional
Python 3.11+, reproducible seeds, all runs configurable via YAML, CI-tested, results exportable (CSV/PDF).

## 7. Out of scope
Real quantum hardware; live vessel telemetry; crew/port operations.
