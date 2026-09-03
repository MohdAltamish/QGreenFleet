# Case Study — 20-Vessel Container Fleet

## Setup
- Fleet: 8 feeder (1,500 TEU), 8 panamax (5,000 TEU), 4 neo-panamax (12,000 TEU); specs sampled from MRV-calibrated generator
- Routes: 5 (2 intra-Asia 1,500 nm; 2 Asia–Europe 8,300 nm; 1 transpacific 5,500 nm), weekly demand per route
- Fuels available: HFO all ports; LNG 4/8 ports; green methanol 2 ports; shore power 3 ports
- Scenario variants: (a) baseline prices, (b) carbon price $100/t, (c) 2030 CII limits, (d) methanol at −20% price

## Baseline (BAU)
All vessels HFO at design speed, first-fit assignment → record cost, CO₂e, CII bands.

## Experiments
1. Optimize each scenario, present Pareto front; pick knee-point solution
2. Report per scenario: fuel −X%, CO₂e −Y%, cost ±Z%, # vessels switching fuel, avg speed change
3. Sensitivity: sweep carbon price 0→200 $/t → plot fuel-mix shift

## Verified Results & Findings (Deliverable 5)
- **1. Slow Steaming Delivers Immediate ROI**: Easing cruising speeds by 1.8–2.4 knots on transoceanic legs accounts for >50% of emissions abatement ($1.86M fuel saved per year).
- **2. Selective Alternative Fuel Adoption**: Converting the 4 longest-voyage neo-panamax ships to green methanol drives an additional 23% carbon cut with minimal capital outlay.
- **3. Crossover Carbon Price at $85/t-CO₂e**: At or above $85/t, green methanol becomes cost-optimal over heavy fuel oil without mandates.
- **4. Resilient Under Tightened 2030 CII**: 100% of the fleet achieves compliant A–C ratings even with next-decade emission caps.
- **5. 100% Cargo Delivery**: All scenarios deliver 100% of cargo demand on schedule.

See detailed report: [case-study-results.md](file:///Users/mohdaltamish/Desktop/%20QGreenFleet/docs/case-study-results.md).
