# Case Study — 20-Vessel Container Fleet

## Setup
- Fleet: 20 synthetic vessels, 5 routes (`data/synthetic/fleet_20v_5r_seed42.json`), from the synthetic generator
- Fuel availability and shore power per route come from the fleet file
- Scenarios (`src/case_study/run.py`): baseline; carbon_100 (carbon price $100/t); cii_tightened (CII limits −11%); meoh_subsidized (green methanol −20%); green_corridor (what-if: hypothetical H2/NH3 bunkering on one route + dual-fuel container ships, carbon $100/t)

## Baseline (BAU)
All vessels HFO at design speed, first-fit assignment → record cost, CO₂e, CII bands.

## Experiments
1. Optimize each scenario, present Pareto front; pick knee-point solution
2. Report per scenario: fuel −X%, CO₂e −Y%, cost ±Z%, # vessels switching fuel, avg speed change
3. Sensitivity: sweep carbon price 0→200 $/t → plot fuel-mix shift

## Results
See docs/case-study-results.md and outputs/benchmark_report.md (generated from the run outputs).
