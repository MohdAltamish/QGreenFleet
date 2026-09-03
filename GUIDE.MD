# 📘 QGreenFleet — Complete User Guide

Welcome! This guide walks you through downloading, installing, and using
QGreenFleet — a quantum-inspired platform for ship fuel prediction and green
fleet optimization. No prior knowledge of the project is required.

---

## Table of Contents
1. [What is QGreenFleet?](#1-what-is-qgreenfleet)
2. [System Requirements](#2-system-requirements)
3. [Installation](#3-installation)
4. [Getting the Data](#4-getting-the-data)
5. [Quick Start (5 Minutes)](#5-quick-start-5-minutes)
6. [Full Pipeline Walkthrough](#6-full-pipeline-walkthrough)
7. [Using the Web App](#7-using-the-web-app)
8. [Understanding Your Results](#8-understanding-your-results)
9. [Using Your Own Fleet Data](#9-using-your-own-fleet-data)
10. [Command Reference](#10-command-reference)
11. [Project Structure](#11-project-structure)
12. [Troubleshooting](#12-troubleshooting)
13. [FAQ](#13-faq)

---

## 1. What is QGreenFleet?

QGreenFleet answers two questions for fleet operators:

1. **How much fuel will my ships burn?** — an ML model trained on operational
   data and calibrated against 21,622 real, verified EU ship records.
2. **What is the best way to deploy my fleet?** — a quantum-inspired optimizer
   (QIEA + QPSO) that finds fleet plans minimizing fuel cost, CO₂ emissions,
   and operating cost simultaneously, while delivering all cargo on time.

You get a menu of optimized plans (cheapest ↔ greenest), what-if scenario
analysis (carbon taxes, fuel prices), and downloadable PDF reports.

**Note:** the algorithms are *quantum-inspired* — they borrow mathematical
ideas from quantum physics but run entirely on your normal computer.

---

## 2. System Requirements

| Requirement | Minimum |
|---|---|
| OS | Windows 10+, macOS 12+, or Linux |
| Python | 3.11 or newer |
| RAM | 8 GB (16 GB recommended for 100+ vessel runs) |
| Disk | ~2 GB (including datasets) |
| Internet | Only for initial download of datasets |

No GPU or quantum computer required.

---

## 3. Installation

```bash
# 1. Clone the repository
git clone <REPO_URL>
cd qgreenfleet

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify everything works
pytest -q
```

All tests should pass. If not, see [Troubleshooting](#12-troubleshooting).

> **Extra step for PDF reports (WeasyPrint):** on macOS run
> `brew install pango`, on Ubuntu/Debian run
> `sudo apt install libpango-1.0-0 libpangocairo-1.0-0`. Windows users: see
> the WeasyPrint documentation for GTK installation.

---

## 4. Getting the Data

You can **skip this section entirely** if you just want to try the app —
pre-computed results and synthetic fleets are included. Download the real
datasets only if you want to retrain models from scratch.

### 4.1 EU MRV ship emissions data (for model calibration)
1. Go to https://mrv.emsa.europa.eu/#public/emission-report
2. Export reporting years 2022, 2023, 2024 (and 2025 if available) as Excel
3. Save them as:
   ```
   data/raw/mrv_2022.xlsx
   data/raw/mrv_2023.xlsx
   data/raw/mrv_2024.xlsx
   data/raw/mrv_2025.xlsx
   ```

### 4.2 Ship performance voyage data (for model training)
1. Download the "Ship Performance Clustering Dataset" from Kaggle
2. Save as: `data/raw/ship_performance.csv`

### 4.3 Emission factors
Nothing to download — official IMO / FuelEU emission factors are built into
the code (`src/emissions/factors.py`) with citations.

### 4.4 Process the data
```bash
python -m src.data.prepare
```
This cleans both datasets into `data/processed/` and prints row counts at
every step. Expect roughly: MRV ~57,000 → ~21,600 rows; voyages 2,736 rows.

---

## 5. Quick Start (5 Minutes)

The fastest way to see everything working — no datasets needed:

```bash
make demo
# or: streamlit run ui/app.py
```

Then in the browser:
1. **Data page** → tab "Generate Synthetic" → set 20 vessels, 5 routes →
   Generate → "Use this fleet"
2. **Optimize page** → open "Load previous results" → select `baseline` →
   the pre-computed Pareto front, convergence chart, and recommended plan
   load instantly
3. Click the **★ starred point** on the scatter chart (the recommended plan)
4. **Report page** → download both the **Executive Summary** and the
   **Technical Report** PDFs

That's the complete product in 5 minutes.

---

## 6. Full Pipeline Walkthrough

To run everything from scratch (after completing section 4):

```bash
# Step 1 — Clean data (~1 min)
python -m src.data.prepare

# Step 2 — Generate a synthetic fleet calibrated to real MRV statistics
python -m src.data.generate_synthetic --vessels 20 --routes 5 --seed 42

# Step 3 — Train prediction models (~5-10 min)
python -m src.prediction.train --model all --seed 42
# Results: outputs/prediction_report.md, models/best.pkl

# Step 4 — Run the optimizer (~9 min for 20 vessels, 300 generations)
python -m src.optimization.run --config configs/case_study.yaml
# Results: outputs/pareto.csv, outputs/convergence.png

# Step 5 — (Optional) Benchmark against classical algorithms (~30-120 min)
python -m src.benchmark.run_all --config configs/benchmark.yaml --seeds 5
# Results: outputs/benchmark_report.md

# Step 6 — (Optional) Run the full policy case study
python -m src.case_study.run
# Results: docs/case-study-results.md, outputs/case_study/

# Step 7 — Launch the app
streamlit run ui/app.py
```

Or simply: `make all`

---

## 7. Using the Web App

The app has 5 pages (left sidebar):

### 📁 Page 1 — Data
Load your fleet. Either upload a fleet JSON file (format in section 9) or
generate a synthetic fleet with the sliders. You'll see vessel/route tables
and a route map. Click **"Use this fleet"** before moving on.

### 📈 Page 2 — Predict
Explore the fuel model. Move the sliders (speed, draft/load, weather, ship
type) and watch predicted fuel consumption change. The curve shows why
slowing down saves fuel — consumption rises roughly with the **cube** of speed.

### ⚙️ Page 3 — Optimize
The core. Set fuel prices and an optional carbon price, then **Run
Optimization** (a few minutes) — or use **"Load previous results"** for
instant pre-computed runs. The result is a scatter chart where **every dot
is a complete fleet plan**: further left = cheaper, further down = greener.
The ★ marks the recommended balance. Click any dot to see its full
deployment table, including what changed versus business-as-usual.

### 🔀 Page 4 — Scenarios
What-if analysis. Create scenarios with different fuel prices or carbon
taxes and compare them side by side. **"Run price sweep"** finds the carbon
price at which green fuel becomes the cheapest option.

### 📄 Page 5 — Report
Download results as PDF:
- **Executive Summary** (2–3 pages, plain language — for management)
- **Technical Report** (12+ pages, full methodology — for engineers)

---

## 8. Understanding Your Results

| Term you'll see | Meaning |
|---|---|
| **BAU** | Business-as-usual — your fleet today; the baseline all savings are measured against |
| **The dot chart (Pareto front)** | Each dot = one complete fleet plan; there is no single "best", only best trade-offs |
| **★ Knee point** | The recommended plan — most emission savings for the least extra cost |
| **Feasible** | Plan breaks no rules: all cargo delivered, on schedule, within emission limits |
| **WtW CO₂e** | Full lifecycle emissions, including producing the fuel — not just burning it |
| **CII (A–E)** | The IMO's carbon report card per ship; D–E means regulatory trouble |
| **Slow steaming** | Sailing slower to save fuel (fuel ∝ speed³) |
| **Shore power** | Plugging into the port grid while docked instead of running engines |

Typical result on the demo fleet: **−16% fuel cost, −23% CO₂**, with 100% of
cargo delivered on time.

---

## 9. Using Your Own Fleet Data

Create a JSON file with this structure and upload it on the Data page:

```json
{
  "vessels": [
    {
      "id": "V001", "type": "container", "dwt": 85000,
      "capacity_teu": 7000, "engine_kw": 30000,
      "design_speed": 20.0, "vmin": 8.0, "vmax": 24.0,
      "fuel_per_nm_kg": 210.0,
      "fuels_allowed": ["HFO", "LNG_DIESEL", "MEOH_GREEN"],
      "charter_per_day": 21000
    }
  ],
  "routes": [
    {
      "id": "R0", "distance_nm": 8300, "schedule_days": 32.0,
      "demand_teu": 12000, "weather_severity": 1,
      "lng_available": true, "meoh_available": false,
      "shore_power": true
    }
  ]
}
```

Field notes: `type` ∈ container/bulk/tanker; `weather_severity` 0=calm,
1=moderate, 2=rough; fuels ∈ HFO, LNG_DIESEL, MEOH_GREEN, H2_GREEN, NH3_GREEN.
The app validates your file and lists any problems on upload.

---

## 10. Command Reference

| Command | What it does |
|---|---|
| `make demo` | Launch the web app |
| `make test` | Run the full test suite |
| `make data` | Clean datasets + generate synthetic fleet |
| `make train` | Train prediction models |
| `make optimize` | Run the baseline optimization |
| `make benchmark` | Run the algorithm comparison suite |
| `make all` | Everything, in order |
| `python -m src.data.generate_synthetic --vessels N --routes R --seed S` | Custom synthetic fleet |
| `python -m src.optimization.run --config configs/<file>.yaml` | Optimize with custom config |

---

## 11. Project Structure

```
qgreenfleet/
├── configs/          # YAML run configurations
├── data/
│   ├── raw/          # downloaded datasets (you provide, gitignored)
│   ├── processed/    # cleaned parquet files (generated)
│   └── synthetic/    # generated fleets (included)
├── src/
│   ├── data/         # cleaning + synthetic fleet generation
│   ├── prediction/   # fuel models (physics, XGBoost, QPSO-tuned, MRV)
│   ├── optimization/ # QIEA + QPSO engine, constraints, objectives
│   ├── emissions/    # IMO/FuelEU emission factors, CII rules
│   ├── benchmark/    # GA/MOPSO/SA baselines + metrics
│   └── case_study/   # policy scenario runner
├── ui/               # Streamlit app (5 pages + utils)
├── outputs/          # generated results, charts, reports
├── docs/             # full documentation + sample PDFs
├── models/           # trained model files
├── tests/            # pytest suite
├── Makefile
└── GUIDE.md          # ← you are here
```

Deeper documentation: `docs/architecture.md`, `docs/algorithms.md`,
`docs/mathematical-model.md`, `docs/implementation-guide.md`.

---

## 12. Troubleshooting

**`pytest` fails after install**
→ Check Python version: `python --version` must be 3.11+. Recreate the venv.

**WeasyPrint / PDF errors**
→ Missing system libraries. macOS: `brew install pango`.
Ubuntu: `sudo apt install libpango-1.0-0 libpangocairo-1.0-0`. The rest of
the app works without PDFs.

**`prepare.py` crashes on MRV files**
→ The Excel header row can shift between years. Open the file, count header
rows, adjust `header=` in `src/data/prepare.py::load_mrv_year`. Column names
are matched by substring, so small naming changes are tolerated.

**"models/best.pkl not found" in the app**
→ Run `python -m src.prediction.train --model all` first (or `make train`).

**Optimization is slow**
→ Reduce `pop_size` and `generations` in the config or the UI sliders. For a
quick look use pop 50 / gens 50 (~1 min). Or use "Load previous results".

**Charts missing from PDFs**
→ Ensure `kaleido` is installed: `pip install kaleido`.

**Port already in use for Streamlit**
→ `streamlit run ui/app.py --server.port 8502`

---

## 13. FAQ

**Q: Do I need a quantum computer?**
No. The algorithms are quantum-*inspired* — classical code borrowing quantum
math ideas (superposition-style encoding, tunneling-style jumps) for better
search. Everything runs on a laptop.

**Q: Is the data real?**
The fuel model's absolute levels are calibrated against 21,622 real, verified
EU MRV ship records. Operational patterns come from a voyage-level dataset,
and emission factors are the official IMO/FuelEU values.

**Q: How do I know the optimizer is good?**
It was benchmarked against a genetic algorithm, particle swarm, and simulated
annealing under identical budgets across fleet sizes of 5–100 vessels: high-compliance
knee solutions and 1.1–1.4× faster. See `outputs/benchmark_report.md`.

**Q: Can I use this for trucks or trains instead of ships?**
The framework generalizes (replace vessels with vehicles, fuels with
EV/H₂/diesel), but the prediction model and emission factors are
maritime-specific — you'd retrain and swap those.

**Q: Can I add a new fuel type?**
Yes — add one entry to `FUEL_FACTORS` in `src/emissions/factors.py` (LHV +
emission factors with a source), and include it in vessels' `fuels_allowed`.

**Q: Is it reproducible?**
Fully. All randomness is seeded; every run is driven by a config file. Same
seed + same config = identical results.

---

*QGreenFleet v0.3 — SIH Problem #26138 | Egreen Quanta*
*Questions or issues: open an issue in the repository.*
