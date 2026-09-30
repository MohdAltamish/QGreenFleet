# instruction.md — How to Work on This Project (Team Playbook)

> **Implementation status (current code):** this is a planning document; the plan text below is kept as written. Planned but not built: QiNN / any quantum-inspired neural net (no PyTorch); exact MILP baseline (no Pyomo/HiGHS); PostgreSQL; pymoo/DEAP (all algorithms are from-scratch NumPy); EEXI; interactive route map in the React UI (only the legacy Streamlit Data page has a Folium map); docker compose; AIS data or cross-checking; emission-cap, demand-surge and shore-power-availability scenario levers. The prediction target of MAPE < 10% is **not met**: held-out ships give R² 0.524 / MAPE 26.3% (ship's own EEDI) and R² 0.348 / MAPE 34.5% (EEDI unknown). See README.md for what exists.

## Setup (once)
1. Clone repo, create venv, `pip install -r requirements.txt`
2. Download datasets per docs/implementation-guide.md §2
3. `pytest -q` must pass before you start

## Daily workflow
1. Pick an issue from the board (labels: prediction / optimization / platform / docs)
2. Branch: `feature/<issue-id>-short-name`
3. Follow AGENTS.md conventions; write tests first for algorithm code
4. MR → CI green → 1 review → squash merge

## Role split (suggested for 6-member SIH team)
- M1: data pipeline + synthetic generator
- M2: prediction models (QPSO-XGB; QiNN was planned, not built)
- M3: QIEA/QPSO engine + constraints
- M4: benchmarks + experiments + plots
- M5: UI + API + report generation
- M6: docs, case study, pitch deck, demo video

## Definition of Done
Code + tests + doc section updated + reproducible via config + referenced in context.md status.

## Demo-day checklist
- [ ] `make demo` runs case study end-to-end offline (no internet dependency)
- [ ] Backup: pre-computed outputs/ committed in case live run fails
- [ ] Slides: problem → architecture → QIEA animation → benchmark charts → live UI → KPIs
