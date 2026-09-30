"""Regenerate the sample PDFs in docs/samples/ from the committed baseline case study.

The knee plan and the business-as-usual plan are rebuilt as real decision
matrices from outputs/case_study/baseline/*.json and re-evaluated with the
production predictor, so every number in the PDFs comes from the engine.
Run `make optimize` first; this script refuses to invent a result.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from src.emissions.factors import OPTIMIZER_FUELS  # noqa: E402
from src.optimization.constraints import evaluate_violations  # noqa: E402
from src.optimization.individual import Solution  # noqa: E402
from src.optimization.objectives import evaluate_objectives  # noqa: E402
from src.optimization.runner import load_fleet_data  # noqa: E402
from src.prediction.predictor import FuelPredictor  # noqa: E402
from ui.utils.pdf_export import generate_summary_pdf, generate_technical_pdf  # noqa: E402
from ui.utils.report_data import build_report_data  # noqa: E402

CASE = _PROJECT_ROOT / "outputs" / "case_study" / "baseline"
FLEET = _PROJECT_ROOT / "data" / "synthetic" / "fleet_20v_5r_seed42.json"
SAMPLES = _PROJECT_ROOT / "docs" / "samples"
PRICES = {"HFO": 650.0, "LNG_DIESEL": 800.0, "MEOH_GREEN": 1200.0, "H2_GREEN": 3000.0, "NH3_GREEN": 2500.0}


def rebuild(plan: dict, vessels: list, routes: list, predictor: FuelPredictor) -> Solution:
    """Decision matrices from a serialized plan, re-evaluated with the engine."""
    V, R = len(vessels), len(routes)
    route_idx = {r["id"]: i for i, r in enumerate(routes)}
    vessel_idx = {v["id"]: i for i, v in enumerate(vessels)}
    assignment = np.zeros((V, R), dtype=bool)
    fuel = np.zeros(V, dtype=int)
    shore = np.zeros((V, R), dtype=bool)
    speeds = np.array([[float(v.get("design_speed", 15.0))] * R for v in vessels])
    for row in plan["vessels"]:
        v = vessel_idx[row["vessel_id"]]
        fuel[v] = OPTIMIZER_FUELS.index(row["fuel"])
        r = route_idx.get(row["route_id"])
        if r is None:
            continue
        assignment[v, r] = True
        # Saved speeds are rounded; restore the schedule floor repair() enforces.
        sched = routes[r]["distance_nm"] / max(1.0, routes[r]["schedule_days"] * 24.0)
        speeds[v, r] = max(float(row["speed_kn"]), sched)
        shore[v, r] = bool(row.get("shore_power", False))
    sol = Solution(q_matrix=np.zeros((1, 2)), speeds=speeds)
    sol.observed = {"assignment": assignment, "fuel": fuel, "shore_power": shore}
    evaluate_violations(sol, vessels, routes)
    evaluate_objectives(sol, vessels, routes, predictor, PRICES, carbon_price=0.0)
    return sol


def main() -> None:
    for name in ("solution_knee.json", "bau_baseline.json", "pareto.csv"):
        if not (CASE / name).exists():
            raise SystemExit(f"Missing {CASE / name}. Run `make optimize` first.")

    vessels, routes = load_fleet_data(FLEET)
    predictor = FuelPredictor()
    knee = rebuild(json.loads((CASE / "solution_knee.json").read_text()), vessels, routes, predictor)
    bau = rebuild(json.loads((CASE / "bau_baseline.json").read_text()), vessels, routes, predictor)

    pareto = []
    for _, row in pd.read_csv(CASE / "pareto.csv").iterrows():
        s = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
        s.objectives = row[["fuel_cost_usd", "ghg_wtw_tco2e", "opex_usd"]].to_numpy(dtype=float)
        s.raw_objectives = s.objectives.copy()
        s.feasible = True
        pareto.append(s)

    sweep_csv = CASE.parent / "carbon_sweep.csv"
    history_json = CASE / "history.json"
    data = build_report_data(
        solution=knee,
        pareto=pareto,
        history=json.loads(history_json.read_text()) if history_json.exists() else None,
        fleet={"vessels": vessels, "routes": routes},
        bau=bau,
        sweep_results=pd.read_csv(sweep_csv) if sweep_csv.exists() else None,
        predictor=predictor,
        fuel_prices=PRICES,
        carbon_price=0.0,
    )

    SAMPLES.mkdir(parents=True, exist_ok=True)
    for label, fn, fname in (
        ("Executive Summary", generate_summary_pdf, "QGreenFleet_Executive_Summary.pdf"),
        ("Technical Report", generate_technical_pdf, "QGreenFleet_Technical_Report.pdf"),
    ):
        pdf = fn(data)
        (SAMPLES / fname).write_bytes(pdf)
        print(f"Saved {label} ({len(pdf):,} bytes) to {SAMPLES / fname}")


if __name__ == "__main__":
    main()
