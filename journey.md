# 🚢 The QGreenFleet Journey

*The story of how we built a quantum-inspired fleet decarbonization platform
for SIH Problem #26138.*

---

## Inspiration

Shipping moves ~90% of world trade and produces ~3% of global greenhouse gas
emissions — more than most countries. Fuel is 50–60% of a ship's operating
cost, yet most fleets still run on decades-old rules of thumb: sail at design
speed, burn heavy fuel oil, hope for the best.

Meanwhile, regulators are closing in: IMO carbon ratings (CII), EU carbon
pricing, green fuel mandates. Fleet operators face a genuinely hard question —
*which ships, on which routes, at what speed, on which fuel?* — and the math
behind it is brutal: for just 20 ships and 5 routes, there are more possible
deployment plans than atoms in a glass of water.

That's what hooked us on Egreen Quanta's problem statement. Classical
optimizers drown in this search space. Quantum-inspired algorithms — which
borrow ideas like superposition and tunneling from quantum physics but run on
ordinary laptops — promised a smarter way to search. We wanted to find out if
the promise was real, and prove it with numbers.

## What it does

QGreenFleet is an end-to-end decision support platform that:

- **Predicts fuel consumption** for a ship at a given speed, draft and weather —
  a QPSO-tuned XGBoost model trained on **21,622 EU MRV ship-years (2022–2023)**,
  plus the cubic speed law and rule-based draft/weather factors
- **Optimizes the whole fleet** with a quantum-inspired engine (QIEA + QPSO):
  who sails where, how fast, on which fuel (HFO, LNG, green methanol, hydrogen,
  ammonia), and when to plug into shore power
- **Hands you a menu, not one answer**: a trade-off frontier from cheapest to
  greenest, with a starred recommendation
- **Answers "what if?"**: carbon price, green-methanol subsidy, tighter CII
  limits, and a hypothetical H2/NH3 green corridor
- **Writes the reports for you**: a plain-language executive summary for
  managers and a 12-page technical report for engineers

For our 20-vessel case-study results, see docs/case-study-results.md and outputs/benchmark_report.md (generated from the run outputs).

## How we built it

We built it in five phases, each one feeding the next:

1. **Data.** We hunted for real ship fuel data (spoiler: nobody publishes
   voyage-level fuel logs — they're trade secrets). So we combined three
   sources: EU MRV registry (real annual fuel for 21,622 ship-years, 2022–2023),
   a voyage-level performance dataset (which turned out to have no learnable
   fuel signal), and IMO/FuelEU emission factors.
2. **Prediction.** XGBoost tuned by quantum-behaved particle swarm (QPSO),
   trained on MRV with speed, EEDI and ship category (monotone in speed, log
   target, ship-grouped split). In the optimizer, fuel/day follows the cubic
   speed law with a part-load penalty; draft and weather are rule-based factors.
3. **Optimization.** We implemented QIEA from scratch in NumPy: every fleet
   decision is a "Q-bit" — a probability, not a fixed choice — nudged toward
   good solutions by quantum rotation gates. Speeds are handled by QPSO, whose
   heavy-tailed jumps mimic quantum tunneling. NSGA-II Pareto ranking keeps
   the best trade-offs.
4. **Proof.** We benchmarked against a genetic algorithm, particle swarm, and
   simulated annealing — same budgets, same rules, multiple seeds, fleet sizes
   from 5 to 100 vessels — plus a 5-scenario policy case study.
5. **Product.** A React app on a FastAPI backend (plus the earlier 5-page
   Streamlit app) with live optimization, scenario sweeps, an offline demo
   mode, and dual PDF report generation — backed by a pytest suite.

## Challenges we ran into

- **The data wall.** No public dataset has speed + load + weather + fuel
  together. The voyage-level dataset we found had no learnable fuel signal
  (every stage-2 model scored R² ≤ 0), so we dropped it for training: fuel
  levels come from the MRV model, and draft/weather are rule-based factors.
- **The negative R².** Our first prediction models scored an R² near zero.
  Instead of hiding it, we diagnosed it (the synthetic dataset's power column
  barely correlates with speed), reported it honestly, and added an
  MRV-trained model on real data. On held-out ships it reaches R² 0.524 /
  MAPE 26.3% (R² 0.348 / MAPE 34.5% without the ship's EEDI) — better than a
  category median (R² 0.234 / MAPE 36.9%), but short of our < 10% MAPE target.
- **Constraint hell.** Early optimizer runs produced beautiful plans that
  delivered no cargo. Greedy repair operators plus adaptive penalties
  (violations get more expensive every generation) fixed that.
- **Honest benchmarking is hard.** It's easy to beat a crippled baseline. We
  forced every algorithm to share the same repair, objectives, and evaluation
  budget, and we only report what the generated benchmark outputs show.
- **The 10-minute runtime target.** 60,000 plan evaluations initially took far
  too long. Vectorizing the hot path in NumPy (no Python loops over vessels)
  brought a full 300-generation run to ~9 minutes on a laptop.

## Accomplishments that we're proud of

- **A quantum-inspired engine built from scratch** — Q-bit encoding, rotation
  gates, QPSO tunneling — plain NumPy, no metaheuristic framework
- **Real-world grounding**: the fuel model is trained on 21,622 EU MRV
  ship-years; every emission factor is traceable to IMO/FuelEU sources
- **A carbon-price sweep** that shows where green methanol becomes cheaper
  than HFO — for the crossover value, see docs/case-study-results.md and outputs/benchmark_report.md (generated from the run outputs)
- **Two reports, one truth**: executive summary and technical report generated
  from a single shared data source, with an automated "jargon guard" test that
  fails the build if technical terms leak into the plain-language version
- **A pytest suite**, fully seeded and reproducible: same config + same
  seed = identical results

## What we learned

- **Quantum-inspired ≠ hype — but honesty sells it.** Saying "classical
  hardware, quantum-inspired math" upfront, and comparing against classical
  baselines under equal budgets, matters more than any buzzword
- **Real data beats volume.** 21,622 real MRV ship-years gave a usable model;
  2,736 voyage rows with no fuel signal gave nothing we could learn from
- **Repair beats punishment** for constraint handling: fixing infeasible
  solutions outperformed penalizing them into oblivion
- **The last mile is translation.** The optimizer was half the work; turning a
  Pareto front into a per-ship plan (which ships slow down, which switch fuel,
  what it saves) was the other half
- **Report failures, not just wins.** Our negative-R² story and our corrected
  benchmark claims became strengths, because we could explain exactly why

## What's next for QGreenFleet

- **Real quantum hardware**: our Q-bit encoding maps naturally to QUBO form —
  the roadmap is hybrid solving on quantum annealers as they scale
- **Live data feeds**: AIS vessel tracking + weather APIs for dynamic
  re-optimization mid-voyage, not just annual planning
- **Fleet operator pilot**: validate against a real operator's private fuel
  logs under NDA — the data we couldn't get publicly
- **Beyond ships**: the same framework generalizes to trucking and rail green
  fleet transitions (EV/H₂/diesel mix)
- **Deeper regulation modeling**: full EU ETS phase-in schedules and FuelEU
  Maritime compliance pooling

---

*Built for Smart India Hackathon — Problem #26138 (Egreen Quanta).*
*From "can quantum-inspired search actually help?" to a reproducible,
tested platform that measures the answer. That was the journey.*
