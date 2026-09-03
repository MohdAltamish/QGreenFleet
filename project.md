# 🚢 Quantum-Inspired Fuel Consumption Prediction & Green Fleet Optimization

**SIH Problem ID:** 26138 | **Organization:** Egreen Quanta | **Theme:** Clean & Green Technology | **Category:** Software

---

## 1. Problem Statement

The maritime and logistics industries face mounting pressure to cut greenhouse gas (GHG) emissions while staying operationally efficient and cost-effective. Fuel is one of the largest operational expenses (typically 50–60% of a vessel's operating cost) and the dominant environmental impact of fleet operations.

**Why traditional methods fail:**
- Fleet optimization is **high-dimensional** (vessel mix × routes × speeds × fuel types × schedules)
- Fuel consumption is **non-linear** (roughly cubic with speed, and heavily affected by weather, hull fouling, load)
- The problem is **multi-objective**: fuel cost vs. emissions vs. schedule reliability conflict with each other
- Integration of **alternative fuels** (LNG, methanol, hydrogen, ammonia) and **shore power** adds combinatorial complexity
- Regulations (IMO CII, EEXI, EU ETS, FuelEU Maritime) impose hard constraints that change yearly

**The opportunity:** Quantum-inspired metaheuristic algorithms run on classical hardware but borrow quantum principles (superposition-based probabilistic encoding, quantum rotation gates, tunneling behavior) to achieve stronger global search, faster convergence, and better solution diversity on large-scale combinatorial problems.

---

## 2. Our Solution

**"QGreenFleet"** — an end-to-end decision support platform with two coupled engines:

1. **Prediction Engine:** A quantum-inspired ML model that predicts vessel fuel consumption from operational features (speed, load, weather, vessel type, engine specs).
2. **Optimization Engine:** A quantum-inspired multi-objective metaheuristic (QIEA + QPSO hybrid) that decides the optimal fleet deployment — which vessels, what capacity, what speed, which fuel — to minimize fuel, cost, and lifecycle emissions while meeting cargo demand and regulations.

The prediction engine feeds the optimizer: predicted fuel curves become the objective function inputs, so optimization decisions are grounded in data-driven reality rather than static assumptions.

### Solution Highlights
- **Quantum-Inspired Evolutionary Algorithm (QIEA):** Q-bit probabilistic encoding of discrete fleet decisions (vessel selection, fuel type), updated via quantum rotation gates
- **Quantum Particle Swarm Optimization (QPSO):** continuous variables (cruising speed per leg) with delta-potential-well behavior enabling escape from local optima
- **NSGA-II-style Pareto ranking** for true multi-objective trade-off fronts (cost vs. CO₂e vs. reliability)
- **Well-to-Wake lifecycle emissions accounting** per fuel type, not just tank-to-wake
- **Scenario simulator:** fuel price shocks, new emission caps, demand surges, shore-power availability
- **Benchmarking harness:** side-by-side vs. GA, PSO, Simulated Annealing, and exact MILP on small instances

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Web UI (React / Streamlit)               │
│   Scenario Builder │ Pareto Explorer │ Fleet Map │ Reports  │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API (FastAPI)
┌──────────────────────────┴──────────────────────────────────┐
│                     Orchestration Layer                     │
├──────────────┬───────────────────┬──────────────────────────┤
│  Prediction  │   Optimization    │   Scenario & Benchmark   │
│  Engine      │   Engine          │   Module                 │
│  (QiML +     │   (QIEA + QPSO +  │   (Monte Carlo, what-if, │
│  XGBoost     │   NSGA-II Pareto) │   GA/PSO/MILP baselines) │
│  baseline)   │                   │                          │
├──────────────┴───────────────────┴──────────────────────────┤
│              Emissions & Constraints Library                │
│   WtW factors (HFO/LNG/MeOH/H₂/NH₃) │ IMO CII/EEXI rules   │
├─────────────────────────────────────────────────────────────┤
│                       Data Layer                            │
│   Vessel DB │ Voyage/AIS data │ Weather │ Fuel prices       │
│              (PostgreSQL + Parquet files)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.11+ | ML + optimization ecosystem |
| Prediction | scikit-learn, XGBoost, PyTorch (QiNN) | Baselines + quantum-inspired neural net |
| Optimization | NumPy, pymoo (extended with custom quantum operators), DEAP | Multi-objective framework, custom QIEA/QPSO |
| Exact baseline | Pyomo + CBC/HiGHS solver | MILP benchmark on small instances |
| API | FastAPI + Pydantic | Async, auto-docs, type-safe |
| Frontend | Streamlit (MVP) → React + Plotly.js (final) | Fast iteration, then polish |
| Database | PostgreSQL + Parquet (pandas/pyarrow) | Structured fleet data + fast analytics |
| Visualization | Plotly, Folium/Leaflet (route maps) | Interactive Pareto fronts & maps |
| Reports | WeasyPrint / ReportLab | PDF report generation |
| DevOps | GitLab CI/CD, Docker, pytest | Automated benchmark suite in pipeline |

---

## 5. Core Algorithms (Technical Detail)

### 5.1 Fuel Consumption Prediction
- **Physics prior:** Admiralty formula baseline — `Fuel ∝ (Δ^(2/3) × V³) / C_adm` (displacement, speed, admiralty coefficient)
- **Features:** speed over ground, draft/load %, wind speed & direction, significant wave height, vessel type, DWT, engine power, hull age, trim
- **Models compared:** Linear (physics), Random Forest, XGBoost, **Quantum-Inspired Neural Network** (qubit-like neurons with rotation-based activation) and **QPSO-tuned XGBoost** (quantum swarm for hyperparameter + feature selection)
- **Metrics:** RMSE, MAPE, R², plus per-vessel-type breakdown

### 5.2 Multi-Objective Optimization Formulation
**Decision variables:**
- `x[v,r] ∈ {0,1}` — vessel v assigned to route r
- `s[v,r] ∈ [Vmin, Vmax]` — cruising speed
- `f[v] ∈ {HFO, LNG, MeOH, H₂, NH₃}` — fuel type
- `sp[v,p] ∈ {0,1}` — shore power usage at port p

**Objectives (minimize):**
1. Total fuel cost = Σ predicted_fuel(v, s, load) × price(f)
2. Lifecycle GHG = Σ fuel × WtW_factor(f) (gCO₂e/MJ)
3. Total opex (charter + port + fuel + carbon price under EU ETS)

**Constraints:** cargo demand per route ≥ demand; transit time ≤ schedule window; CII rating ≥ required band; vessel capacity; fuel availability at ports.

### 5.3 Quantum-Inspired Metaheuristic
- **Encoding:** each discrete decision is a Q-bit `[α, β]` with |α|²+|β|²=1 → observation collapses to a binary solution
- **Update:** quantum rotation gate steers Q-bits toward the best Pareto-nondominated solutions; adaptive rotation angle Δθ decays over generations
- **QPSO for speeds:** particles sampled from a delta potential well around attractor `p = φ·pbest + (1−φ)·gbest`, giving heavy-tailed jumps (quantum tunneling analogue)
- **Diversity:** quantum mutation (Q-bit reinitialization) + crowding distance preservation

---

## 6. Build Process (Roadmap)

| Phase | Duration | Deliverable |
|---|---|---|
| 1. Data & EDA | Week 1 | Cleaned dataset, feature pipeline, EDA notebook |
| 2. Prediction MVP | Week 1–2 | XGBoost baseline + QiNN/QPSO-XGB, accuracy report |
| 3. Math model | Week 2 | Full MINLP formulation document + emission factor library |
| 4. QIEA/QPSO engine | Week 2–3 | Core optimizer, unit-tested on toy fleet (5 vessels, 3 routes) |
| 5. Benchmarking | Week 3 | Convergence curves, hypervolume, scalability (10→200 vessels) vs GA/PSO/SA/MILP |
| 6. Platform | Week 4 | FastAPI + UI, scenario simulation, Pareto explorer, PDF reports |
| 7. Case study & demo | Week 4 | 20-vessel/5-route case study, demo video, docs |

---

## 7. Use Cases

1. **Shipping line fleet planner:** decides annual vessel deployment & speed policy to hit CII targets at minimum cost
2. **Port authority:** evaluates shore-power investment impact on visiting-fleet emissions
3. **Charterer / cargo owner:** compares carriers on predicted voyage emissions (Scope 3 reporting)
4. **Regulator / policy analyst:** scenario-tests carbon price levels and fuel mandates on fleet behavior
5. **Green corridor consortiums:** plan alternative-fuel bunkering infrastructure using optimized fuel-mix forecasts
6. **Extension to land logistics:** the same framework applies to truck/rail green fleet mix (EV/H₂/diesel)

---

## 8. Existing Solutions & Competitive Analysis

| Solution | Type | Prediction | Optimization | Alt-Fuel Scenarios | Quantum-Inspired | Multi-Objective Pareto | Open/Cost |
|---|---|---|---|---|---|---|---|
| **DNV Veracity / ECO Insight** | Commercial analytics | ✅ Statistical | ❌ Limited | Partial | ❌ | ❌ | Expensive, closed |
| **StormGeo s-Insight** | Weather routing | ✅ Voyage-level | ✅ Single-voyage routing only | ❌ | ❌ | ❌ | Commercial |
| **Wärtsilä FOS** | Fleet ops suite | ✅ | ✅ Voyage optimization | Partial | ❌ | ❌ | Commercial |
| **ZeroNorth** | Commercial platform | ✅ ML-based | ✅ Speed/bunker | Partial | ❌ | Partial | Commercial |
| **Academic GA/PSO models** | Research | Varies | ✅ Classical metaheuristics | Rare | ❌ | Sometimes | Not productized |
| **Classical MILP tools (e.g., research + Gurobi)** | Research/enterprise | ❌ | ✅ Exact but doesn't scale | Rare | ❌ | Weighted-sum only | Solver license cost |
| **QGreenFleet (Ours)** | Open platform | ✅ Quantum-inspired ML | ✅ QIEA + QPSO, scalable | ✅ LNG/MeOH/H₂/NH₃ + shore power | ✅ | ✅ True Pareto fronts | Open source |

**Our differentiators:** (1) coupled prediction→optimization loop, (2) quantum-inspired global search with benchmarked convergence advantage, (3) full lifecycle (WtW) emissions with alternative-fuel scenario analysis, (4) open, reproducible benchmarking.

---

## 9. Datasets & References

### Datasets
| Dataset | Use | Link/Source |
|---|---|---|
| Ship Fuel Consumption dataset (Kaggle) | Prediction training | kaggle.com — search "ship fuel consumption" |
| EU MRV THETIS public emissions data | Real vessel fuel/CO₂ per year, by ship | mrv.emsa.europa.eu |
| NOAA / Copernicus Marine weather data | Weather features (wind, waves) | marine.copernicus.eu |
| AIS sample data (Danish Maritime Authority, MarineCadastre.gov) | Speed/route reconstruction | dma.dk, marinecadastre.gov |
| IMO GHG Study 2020 emission factors | WtW emission factors per fuel | imo.org |
| Ship performance dataset (UCI/research, e.g., "Propulsion Plants" CBM dataset) | Engine-level modeling | UCI ML Repository |
| Synthetic fleet generator (ours) | Scalability benchmarks (10–200 vessels) | Included in repo |

### Key References
1. Han, K.-H. & Kim, J.-H. (2002). *Quantum-inspired evolutionary algorithm for a class of combinatorial optimization.* IEEE Trans. Evolutionary Computation.
2. Sun, J. et al. (2004). *Particle swarm optimization with particles having quantum behavior (QPSO).* IEEE CEC.
3. Deb, K. et al. (2002). *NSGA-II: A fast and elitist multiobjective genetic algorithm.* IEEE TEC.
4. IMO (2020). *Fourth IMO GHG Study* — emission factors & fuel pathways.
5. Psaraftis, H. & Kontovas, C. (2013). *Speed models for energy-efficient maritime transportation.* Transportation Research Part C.
6. Fagerholt, K. et al. — research on fleet deployment & slow steaming optimization.
7. FuelEU Maritime Regulation (EU 2023/1805) — WtW GHG intensity limits.
8. Yan, R. et al. (2021). *Machine learning for ship fuel consumption prediction* — Transportation Research Part E (survey).

---

## 10. Evaluation & Benchmarking Plan

- **Prediction:** RMSE / MAPE / R² vs. linear, RF, XGBoost baselines; k-fold CV per vessel type
- **Optimization:** hypervolume & IGD of Pareto fronts, convergence speed (generations to 95% best), solution quality vs. MILP optimum on small instances, scalability wall-clock at 10/50/100/200 vessels
- **Case study:** 20-vessel container fleet, 5 routes, 4 fuel options — report fuel saved (%), CO₂e reduced (%), cost delta vs. business-as-usual

---

## 11. Team & Repository Structure

```
qgreenfleet/
├── data/                  # datasets + synthetic generator
├── src/
│   ├── prediction/        # QiNN, QPSO-XGB, baselines
│   ├── optimization/      # qiea.py, qpso.py, pareto.py, constraints.py
│   ├── emissions/         # WtW factor library, CII calculator
│   ├── benchmark/         # GA/PSO/SA/MILP baselines, metrics
│   └── api/               # FastAPI app
├── ui/                    # Streamlit / React frontend
├── notebooks/             # EDA, experiments
├── tests/
├── docs/
└── .gitlab-ci.yml         # lint + tests + benchmark job
```
