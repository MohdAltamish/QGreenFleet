# Testing Strategy

## Unit tests (pytest)
- rotation gate: normalization preserved; converges qubit toward target bit
- QPSO: samples within bounds after clip; attractor math
- Pareto: nondominated sort on hand-made 6-point set; crowding distance
- constraints: C1 repair meets demand; C3 repair keeps one route per vessel; penalty grows with generation; methanol priced on energy (LHV) basis
- emissions: WtW totals vs manual calc; fuel-type switch changes Z2 correctly
- prediction: pipeline shapes; physics baseline matches formula
- reporting (`test_report.py`): KPI math deltas vs BAU, jargon guard (executive summary free of algorithmic jargon), and dual PDF compilation (technical + executive summary)

## Integration tests
- Toy-fleet QIEA smoke test; QIEA archive-size smoke test on instance M
- Not present: MILP comparison (no MILP baseline), API tests

## Regression
- No golden-file test yet (planned: seed 42 toy run → hypervolume within ±1% of stored value)

## Commands
`pytest -q` · coverage: `pytest --cov=src --cov-fail-under=70`

## CI (.gitlab-ci.yml stages)
lint (ruff) → test (pytest+cov) → benchmark-smoke (S instance, 20 gens) → build (docker build, main only)
