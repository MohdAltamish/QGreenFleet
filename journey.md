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

- **Predicts fuel consumption** for any ship, speed, load, and weather — using
  ML calibrated against **21,622 real, verified EU ship records**
- **Optimizes the whole fleet** with a quantum-inspired engine (QIEA + QPSO):
  who sails where, how fast, on which fuel (HFO, LNG, green methanol, hydrogen,
  ammonia), and when to plug into shore power
- **Hands you a menu, not one answer**: a trade-off frontier from cheapest to
  greenest, with a starred recommendation
- **Answers "what if?"**: carbon taxes, fuel price shocks, tighter emission
  caps — recomputed in minutes
- **Writes the reports for you**: a plain-language executive summary for
  managers and a 12-page technical report for engineers

On our 20-vessel case study: **−16.2% fuel cost, −23.3% CO₂, with 100% of
cargo delivered on time.**

## How we built it

We built it in five phases, each one feeding the next:

1. **Data.** We hunted for real ship fuel data (spoiler: nobody publishes
   voyage-level fuel logs — they're trade secrets). So we combined three
   sources: EU MRV registry (real annual fuel for 21,622 ship-years), a
   voyage-level performance dataset (the *shape* of how fuel responds to speed
   and weather), and official IMO/FuelEU emission factors.
2. **Prediction.** Physics first (fuel rises with the cube of speed), then ML
   on top (XGBoost tuned by quantum-behaved particle swarm), then a
   calibration layer scaling everything to real-world MRV levels per ship type.
3. **Optimization.** We implemented QIEA from scratch in NumPy: every fleet
   decision is a "Q-bit" — a probability, not a fixed choice — nudged toward
   good solutions by quantum rotation gates. Speeds are handled by QPSO, whose
   heavy-tailed jumps mimic quantum tunneling. NSGA-II Pareto ranking keeps
   the best trade-offs.
4. **Proof.** We benchmarked against a genetic algorithm, particle swarm, and
   simulated annealing — same budgets, same rules, multiple seeds, fleet sizes
   from 5 to 100 vessels — plus a 4-scenario policy case study.
5. **Product.** A 5-page Streamlit platform with live optimization, scenario
   sweeps, an offline demo mode, and dual PDF report generation — backed by
   84 automated tests.

## Challenges we ran into

- **The data wall.** No public dataset has speed + load + weather + fuel
  together. Our fix became our proudest design decision: learn the *shape*
  from granular data, anchor the *magnitude* to real MRV records. Our
  calibration check showed the raw voyage data was off by 4–9× versus real
  ships — the calibration layer closed that gap.
- **The negative R².** Our first prediction models scored an R² near zero.
  Instead of hiding it, we diagnosed it (the synthetic dataset's power column
  barely correlates with speed), reported it honestly, and added an
  MRV-trained model on real data where the metrics actually mean something.
- **Constraint hell.** Early optimizer runs produced beautiful plans that
  delivered no cargo. Greedy repair operators plus adaptive penalties
  (violations get more expensive every generation) got us to 100% feasible
  populations within ~50 generations.
- **Honest benchmarking is hard.** It's easy to beat a crippled baseline. We
  forced every algorithm to share the same repair, objectives, and evaluation
  budget — and when our wall-time speedup settled at 1.1–1.4× across fleet scales,
  we updated every claim in the project to "1.1–1.4× faster than GA". The numbers
  had to survive an audit.
- **The 10-minute runtime target.** 60,000 plan evaluations initially took far
  too long. Vectorizing the hot path in NumPy (no Python loops over vessels)
  brought a full 300-generation run to ~9 minutes on a laptop.

## Accomplishments that we're proud of

- **A quantum-inspired engine built from scratch** — Q-bit encoding, rotation
  gates, QPSO tunneling — no metaheuristic framework shortcuts: converges to
  strong compromise solutions faster; on maritime fleet problems, cost and
  emissions move together, so QIEA's precise convergence outperforms GA's broad spread
- **Real-world grounding**: every fuel number traceable to 21,622 verified EU
  ship records; every emission factor traceable to IMO/FuelEU sources
- **A finding worth quoting**: green methanol becomes the *cheapest* fuel —
  not just the cleanest — once carbon prices pass **$85/tonne**
- **Two reports, one truth**: executive summary and technical report generated
  from a single shared data source, with an automated "jargon guard" test that
  fails the build if technical terms leak into the plain-language version
- **84/84 tests passing**, fully seeded and reproducible: same config + same
  seed = identical results, every time

## What we learned

- **Quantum-inspired ≠ hype — but honesty sells it.** The algorithms genuinely
  search better; saying "classical hardware, quantum math" upfront earned more
  credibility than any buzzword could
- **Calibration beats data volume.** 2,736 imperfect rows + 21,622 real
  anchors produced more trustworthy predictions than any amount of synthetic
  data alone
- **Repair beats punishment** for constraint handling: fixing infeasible
  solutions outperformed penalizing them into oblivion
- **The last mile is translation.** The optimizer was half the work; turning a
  Pareto front into "slow these 6 ships down, switch these 4 to methanol, save
  $1.86M" was the other half
- **Report failures, not just wins.** Our negative-R² story and the 2×→1.4×
  correction became strengths, because we could explain exactly why

## What's next for QGreenFleet

- **Real quantum hardware**: our Q-bit encoding maps naturally to QUBO form —
  the roadmap is hybrid solving on quantum annealers as they scale
- **Live data feeds**: AIS vessel tracking + weather APIs for dynamic
  re-optimization mid-voyage, not just annual planning
- **Fleet operator pilot**: validate against a real operator's private fuel
  logs under NDA — the data we couldn't get publicly
- **Beyond ships**: the same framework generalizes to trucking and rail green
  fleet transitions (EV/H₂/diesel mix)
- **FastAPI + modern frontend**: the API layer is designed; a Next.js
  interface follows for production deployment
- **Deeper regulation modeling**: full EU ETS phase-in schedules and FuelEU
  Maritime compliance pooling

---

*Built for Smart India Hackathon — Problem #26138 (Egreen Quanta).*
*From "can quantum-inspired search actually help?" to "−23% CO₂, proven,
reproducible, 84 tests green." That was the journey.*
