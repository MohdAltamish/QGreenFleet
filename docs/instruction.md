# instruction.md — How to Work on This Project (Team Playbook)

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
- M2: prediction models (QPSO-XGB, QiNN)
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
