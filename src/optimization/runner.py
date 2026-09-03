"""Execution runner and CLI entry point for fleet optimization.

Loads configuration YAML, initializes the predictive machine learning surrogate,
executes the hybrid QIEA + QPSO search, logs generational convergence metrics,
and saves Pareto front artifacts.

Usage::

    python -m src.optimization.run --config configs/case_study.yaml
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from typing import Any

# Ensure headless matplotlib configuration
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import numpy as np
import pandas as pd
import yaml

from src.emissions.factors import OPTIMIZER_FUELS
from src.optimization.individual import Solution
from src.optimization.qiea import run
from src.prediction.predictor import FuelPredictor

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = _PROJECT_ROOT / "configs" / "case_study.yaml"
DEFAULT_OUTPUTS = _PROJECT_ROOT / "outputs"


def load_yaml_config(path: Path) -> dict[str, Any]:
    """Load configuration YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found at {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_fleet_data(fleet_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load fleet and route JSON."""
    if not fleet_path.exists():
        raise FileNotFoundError(f"Fleet JSON not found at {fleet_path}")
    data = json.loads(fleet_path.read_text(encoding="utf-8"))
    return data.get("vessels", []), data.get("routes", [])


def plot_convergence(history: dict[str, list[Any]], output_path: Path) -> None:
    """Save dual-axis convergence plot (Hypervolume and Feasible Count vs Generation).

    Args:
        history: Optimization progress dictionary.
        output_path: Destination image path.
    """
    gens = history["generation"]
    hv = history["hypervolume"]
    feas = history["feasible_count"]

    fig, ax1 = plt.subplots(figsize=(8, 5))

    color_hv = "#2ca02c"
    ax1.set_xlabel("Generation")
    ax1.set_ylabel("Hypervolume (Archive)", color=color_hv)
    line1 = ax1.plot(gens, hv, color=color_hv, lw=2, label="Hypervolume")
    ax1.tick_params(axis="y", labelcolor=color_hv)
    ax1.grid(True, linestyle=":", alpha=0.6)

    ax2 = ax1.twinx()
    color_feas = "#1f77b4"
    ax2.set_ylabel("Feasible Population Count", color=color_feas)
    line2 = ax2.plot(gens, feas, color=color_feas, lw=1.5, linestyle="--", alpha=0.8, label="Feasible Count")
    ax2.tick_params(axis="y", labelcolor=color_feas)

    # Combined legend
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="lower right")

    plt.title("QGreenFleet Optimization Convergence (QIEA + QPSO)")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def save_pareto_artifacts(
    archive: list[Solution],
    vessels: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    outputs_dir: Path,
    fuels: tuple[str, ...] = OPTIMIZER_FUELS,
) -> None:
    """Save pareto.csv and individual solution JSON files."""
    outputs_dir.mkdir(parents=True, exist_ok=True)
    csv_rows: list[dict[str, Any]] = []

    for idx, sol in enumerate(archive):
        sol_id = f"sol_{idx:03d}"
        z1 = float(sol.objectives[0]) if sol.objectives is not None else 0.0
        z2 = float(sol.objectives[1]) if sol.objectives is not None else 0.0
        z3 = float(sol.objectives[2]) if sol.objectives is not None else 0.0

        assignments_detail: list[dict[str, Any]] = []
        assignment_summary: list[str] = []

        x = sol.observed.get("assignment", np.zeros((len(vessels), len(routes)), dtype=bool))
        f_idx = sol.observed.get("fuel", np.zeros(len(vessels), dtype=int))
        sp = sol.observed.get("shore_power")

        for v_idx in range(len(vessels)):
            v_id = vessels[v_idx].get("id", f"V{v_idx:03d}")
            f_name = fuels[f_idx[v_idx]] if f_idx[v_idx] < len(fuels) else fuels[0]

            for r_idx in range(len(routes)):
                if x[v_idx, r_idx]:
                    r_id = routes[r_idx].get("id", f"R{r_idx}")
                    speed = float(sol.speeds[v_idx, r_idx])
                    assignments_detail.append({
                        "vessel_id": v_id,
                        "route_id": r_id,
                        "speed_kn": round(speed, 2),
                        "fuel": f_name,
                    })
                    assignment_summary.append(f"{v_id}->{r_id}@{speed:.1f}kn({f_name})")

        shore_power_detail: list[dict[str, Any]] = []
        if sp is not None:
            for v_idx in range(len(vessels)):
                v_id = vessels[v_idx].get("id", f"V{v_idx:03d}")
                for p_idx in range(sp.shape[1]):
                    if sp[v_idx, p_idx]:
                        shore_power_detail.append({
                            "vessel_id": v_id,
                            "port_index": p_idx,
                            "connected": True,
                        })

        # Record CSV row
        csv_rows.append({
            "solution_id": sol_id,
            "fuel_cost_usd": round(z1, 2),
            "ghg_wtw_tco2e": round(z2, 2),
            "opex_usd": round(z3, 2),
            "feasible": sol.feasible,
            "deployments_count": len(assignments_detail),
            "assignments": "; ".join(assignment_summary),
        })

        # Detailed individual JSON
        sol_payload = {
            "id": sol_id,
            "objectives": {
                "fuel_cost_usd": z1,
                "ghg_wtw_tco2e": z2,
                "opex_usd": z3,
            },
            "feasible": sol.feasible,
            "violations": sol.violations,
            "assignments": assignments_detail,
            "shore_power": shore_power_detail,
        }
        (outputs_dir / f"solution_{sol_id}.json").write_text(json.dumps(sol_payload, indent=2))

    df_pareto = pd.DataFrame(csv_rows)
    csv_path = outputs_dir / "pareto.csv"
    df_pareto.to_csv(csv_path, index=False)
    print(f"Saved {len(df_pareto)} Pareto solutions to {csv_path}")


def main() -> None:
    """CLI execution function."""
    parser = argparse.ArgumentParser(description="Run QGreenFleet fleet deployment optimization.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to case study YAML configuration",
    )
    parser.add_argument(
        "--outputs-dir",
        type=Path,
        default=DEFAULT_OUTPUTS,
        help="Path to outputs directory",
    )
    args = parser.parse_args()

    t0 = time.time()
    print("=" * 65)
    print("QGreenFleet Optimization Engine (QIEA + QPSO)")
    print("=" * 65)

    # 1. Load config
    cfg = load_yaml_config(args.config)
    fleet_rel = cfg.get("fleet_file", "data/synthetic/fleet_20v_5r_seed42.json")
    fleet_path = _PROJECT_ROOT / fleet_rel if not Path(fleet_rel).is_absolute() else Path(fleet_rel)

    # 2. Load fleet data
    vessels, routes = load_fleet_data(fleet_path)
    print(f"Loaded {len(vessels)} vessels and {len(routes)} commercial routes from {fleet_path.name}")

    # 3. Load FuelPredictor surrogate
    print("Initializing FuelPredictor machine learning surrogate...")
    predictor = FuelPredictor()
    print(f"Surrogate model active: {predictor.model_name}")

    # 4. Progress callback
    def on_progress(gen: int, total_gens: int, n_archive: int, hv: float, n_feasible: int) -> None:
        if gen % 10 == 0 or gen == total_gens:
            print(f"Gen {gen:03d}/{total_gens:03d} | Archive: {n_archive:02d} | HV: {hv:.4f} | Feasible: {n_feasible:03d}/{cfg.get('pop_size', 200)}")

    # 5. Run QIEA + QPSO
    print("\nStarting QIEA (discrete) + QPSO (speeds) optimization run...")
    archive, history = run(
        vessels=vessels,
        routes=routes,
        config=cfg,
        predictor=predictor,
        progress_callback=on_progress,
    )

    elapsed = time.time() - t0
    print(f"\nOptimization completed in {elapsed:.2f} seconds ({elapsed/60.0:.2f} min).")
    print(f"Non-dominated Pareto solutions discovered: {len(archive)}")

    # 6. Save outputs
    save_pareto_artifacts(archive, vessels, routes, args.outputs_dir)
    conv_path = args.outputs_dir / "convergence.png"
    plot_convergence(history, conv_path)
    print(f"Convergence history plot saved to {conv_path}")
    print("=" * 65)


if __name__ == "__main__":
    main()
