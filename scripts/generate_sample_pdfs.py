"""Regenerate publication-grade sample PDFs into docs/samples/."""

import json
from pathlib import Path

from src.optimization.individual import Solution
from src.prediction.predictor import FuelPredictor
from ui.utils.pdf_export import generate_summary_pdf, generate_technical_pdf
from ui.utils.report_data import build_report_data

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
samples_dir = _PROJECT_ROOT / "docs" / "samples"
samples_dir.mkdir(parents=True, exist_ok=True)

# Load case study data if available
baseline_dir = _PROJECT_ROOT / "outputs" / "case_study" / "baseline"
fleet_path = _PROJECT_ROOT / "data" / "synthetic" / "fleet_20v_5r_seed42.json"

fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
pred = FuelPredictor()

# Load knee and bau solutions from case study if present
import numpy as np
n_v = len(fleet["vessels"])
if (baseline_dir / "solution_knee.json").exists() and (baseline_dir / "bau_baseline.json").exists():
    knee_dict = json.loads((baseline_dir / "solution_knee.json").read_text(encoding="utf-8"))
    bau_dict = json.loads((baseline_dir / "bau_baseline.json").read_text(encoding="utf-8"))

    knee_sol = Solution(
        q_matrix=np.zeros((n_v, 2)),
        speeds=np.full((n_v, 1), 14.0),
    )
    knee_obj = knee_dict["objectives"]
    knee_sol.objectives = np.array([knee_obj["fuel_cost_usd"], knee_obj["ghg_wtw_tco2e"], knee_obj["opex_usd"]])

    bau_sol = Solution(
        q_matrix=np.zeros((n_v, 2)),
        speeds=np.full((n_v, 1), 16.0),
    )
    bau_obj = bau_dict["objectives"]
    bau_sol.objectives = np.array([bau_obj["fuel_cost_usd"], bau_obj["ghg_wtw_tco2e"], bau_obj["opex_usd"]])

    pareto_sols = [knee_sol]
    if (baseline_dir / "pareto.csv").exists():
        import pandas as pd
        df_p = pd.read_csv(baseline_dir / "pareto.csv")
        pareto_sols = []
        for _, r in df_p.iterrows():
            s = Solution(q_matrix=knee_sol.q_matrix, speeds=knee_sol.speeds)
            s.objectives = r[["fuel_cost_usd", "ghg_wtw_tco2e", "opex_usd"]].to_numpy(dtype=float)
            pareto_sols.append(s)
else:
    knee_sol = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    knee_sol.objectives = np.array([9624000.0, 44610.0, 17105000.0])
    bau_sol = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau_sol.objectives = np.array([11486000.0, 58140.0, 18930000.0])
    pareto_sols = [knee_sol]

data = build_report_data(
    solution=knee_sol,
    pareto=pareto_sols,
    history=None,
    fleet=fleet,
    bau=bau_sol,
    sweep_results={"crossover_carbon_price": 85.0},
)

print("Compiling Executive Summary PDF...")
pdf_exec = generate_summary_pdf(data)
exec_path = samples_dir / "QGreenFleet_Executive_Summary.pdf"
exec_path.write_bytes(pdf_exec)
print(f"Saved Executive Summary PDF ({len(pdf_exec):,} bytes) to {exec_path}")

print("Compiling Technical Report PDF...")
pdf_tech = generate_technical_pdf(data)
tech_path = samples_dir / "QGreenFleet_Technical_Report.pdf"
tech_path.write_bytes(pdf_tech)
print(f"Saved Technical Report PDF ({len(pdf_tech):,} bytes) to {tech_path}")
