"""Case Study Execution Engine for QGreenFleet (SIH #26138 Deliverable 5).

Executes four realistic fleet decarbonization scenarios end-to-end:
    a) Baseline: standard marine fuel prices, $0 carbon tax
    b) Carbon Tax: $100/t-CO2e carbon levy (EU ETS / IMO global levy)
    c) Tightened CII: 2030 emission caps (tighten annual CII limit one rating band)
    d) Green Methanol Subsidy: 20% clean fuel price reduction ($960/t)
    e) Green Corridor (what-if): hypothetical H2/NH3 bunkering on one route and
       dual-fuel H2/NH3 capability on the container ships — infrastructure the
       committed fleet does not have, so hydrogen and ammonia can be evaluated

Also executes a carbon-price sweep across [0, 25, 50, ..., 200] $/t to locate
the clean fuel economic crossover tipping point.

Usage::

    python -m src.case_study.run
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd

from src.emissions.factors import OPTIMIZER_FUELS
from src.optimization.individual import Solution
from src.optimization.qiea import run as run_qiea
from src.optimization.runner import load_fleet_data
from src.prediction.predictor import FuelPredictor
from ui.utils.chart_helpers import carbon_sweep, fig_to_base64_png
from ui.utils.fleet_loader import compute_bau_baseline
from ui.utils.report_data import _find_knee_solution

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
cache_dir = _PROJECT_ROOT / ".cache" / "matplotlib"
cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))

DEFAULT_FLEET = _PROJECT_ROOT / "data" / "synthetic" / "fleet_20v_5r_seed42.json"
DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "outputs" / "case_study"


def _serialize_solution(sol: Solution, vessels: list[dict[str, Any]], routes: list[dict[str, Any]]) -> dict[str, Any]:
    """Serialize Solution instance to clean JSON dictionary."""
    obs = getattr(sol, "observed", {})
    assign = obs.get("assignment", np.zeros((len(vessels), len(routes)), dtype=bool))
    fuels = obs.get("fuel", np.zeros(len(vessels), dtype=int))
    sp = obs.get("shore_power", np.zeros((len(vessels), len(routes)), dtype=bool))

    vessel_deployments = []
    for v_idx, v in enumerate(vessels):
        assigned_r = np.where(assign[v_idx])[0] if assign.ndim == 2 else []
        r_str = f"R{assigned_r[0]}" if len(assigned_r) > 0 else "Unassigned"
        spd = float(sol.speeds[v_idx, assigned_r[0]]) if len(assigned_r) > 0 else float(v.get("design_speed", 15.0))
        f_code = int(fuels[v_idx]) if v_idx < len(fuels) else 0
        f_name = OPTIMIZER_FUELS[f_code] if f_code < len(OPTIMIZER_FUELS) else "HFO"
        sp_conn = bool(sp[v_idx, assigned_r[0]]) if len(assigned_r) > 0 and sp.ndim == 2 else False

        vessel_deployments.append({
            "vessel_id": v.get("id", f"V{v_idx:03d}"),
            "type": v.get("type", "container"),
            "route_id": r_str,
            "speed_kn": round(spd, 4),  # 2 dp could drop a schedule-minimum speed below the window
            "fuel": f_name,
            "shore_power": sp_conn,
        })

    objs = sol.raw_objectives if sol.raw_objectives is not None else sol.objectives
    objs = objs if objs is not None else np.array([0.0, 0.0, 0.0])
    return {
        "objectives": {
            "fuel_cost_usd": float(objs[0]),
            "ghg_wtw_tco2e": float(objs[1]),
            "opex_usd": float(objs[2]),
        },
        "feasible": bool(sol.feasible),
        "violations": getattr(sol, "violations", {}),
        "vessels": vessel_deployments,
    }


def run_scenario(
    name: str,
    vessels: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    predictor: FuelPredictor,
    fuel_prices: dict[str, float],
    carbon_price: float,
    pop_size: int,
    generations: int,
    output_dir: Path,
) -> dict[str, Any]:
    """Execute a single scenario end-to-end, recording BAU, Knee, deltas, and saving artifacts."""
    print(f"\n{'='*70}\n[Scenario: {name}] Carbon Tax: ${carbon_price}/t | Methanol: ${fuel_prices.get('MEOH_GREEN')}/t\n{'='*70}")

    scen_dir = output_dir / name
    scen_dir.mkdir(parents=True, exist_ok=True)

    # 1. Compute BAU baseline
    bau_sol = compute_bau_baseline(vessels, routes, predictor, fuel_prices, carbon_price)
    bau_objs = bau_sol.raw_objectives if bau_sol.raw_objectives is not None else bau_sol.objectives
    bau_fc, bau_ghg, bau_opex = float(bau_objs[0]), float(bau_objs[1]), float(bau_objs[2])

    # 2. Run QIEA+QPSO optimizer
    opt_cfg = {
        "pop_size": pop_size,
        "generations": generations,
        "theta_start": 0.05 * np.pi,
        "theta_end": 0.005 * np.pi,
        "mutation_prob": 0.02,
        "lambda0": 10.0,
        "fuel_prices": fuel_prices,
        "carbon_price": carbon_price,
        "archive_max": 100,
        "seed": 42,
    }

    t0 = time.perf_counter()
    archive, history = run_qiea(vessels, routes, opt_cfg, predictor)
    elapsed = time.perf_counter() - t0

    # 3. Identify Knee Solution
    knee_sol, knee_idx = _find_knee_solution(archive)
    knee_objs = knee_sol.raw_objectives if knee_sol.raw_objectives is not None else knee_sol.objectives
    knee_fc, knee_ghg, knee_opex = float(knee_objs[0]), float(knee_objs[1]), float(knee_objs[2])

    # 4. Deltas & Operational Metrics
    delta_fc = knee_fc - bau_fc
    delta_fc_pct = (delta_fc / bau_fc) * 100.0 if bau_fc else 0.0
    delta_ghg = knee_ghg - bau_ghg
    delta_ghg_pct = (delta_ghg / bau_ghg) * 100.0 if bau_ghg else 0.0
    delta_opex = knee_opex - bau_opex
    delta_opex_pct = (delta_opex / bau_opex) * 100.0 if bau_opex else 0.0

    # Fuel mix & switches — over DEPLOYED vessels only. Idle vessels keep an
    # unrepaired fuel bit that means nothing and would pollute the mix.
    knee_assign = getattr(knee_sol, "observed", {}).get("assignment", np.zeros((len(vessels), len(routes)), dtype=bool))
    deployed = knee_assign.any(axis=1)
    f_indices = getattr(knee_sol, "observed", {}).get("fuel", np.zeros(len(vessels), dtype=int))[deployed]
    fuel_counts: dict[str, int] = {}
    switches = 0
    for idx in f_indices:
        fn = OPTIMIZER_FUELS[idx] if idx < len(OPTIMIZER_FUELS) else "HFO"
        fuel_counts[fn] = fuel_counts.get(fn, 0) + 1
        if fn != "HFO":
            switches += 1

    n_deployed = max(1, int(deployed.sum()))
    fuel_mix_pct = {k: round(v / n_deployed * 100.0, 1) for k, v in fuel_counts.items()}

    # Average speed change vs BAU
    bau_speeds = getattr(bau_sol, "speeds", np.full((len(vessels), len(routes)), 15.0))
    opt_speeds = getattr(knee_sol, "speeds", np.full((len(vessels), len(routes)), 15.0))
    opt_assign = getattr(knee_sol, "observed", {}).get("assignment", np.zeros((len(vessels), len(routes)), dtype=bool))

    speed_diffs = []
    for v_i in range(len(vessels)):
        assigned_r = np.where(opt_assign[v_i])[0] if opt_assign.ndim == 2 else []
        if len(assigned_r) > 0:
            r = assigned_r[0]
            speed_diffs.append(opt_speeds[v_i, r] - bau_speeds[v_i, r])

    avg_speed_delta = float(np.mean(speed_diffs)) if speed_diffs else 0.0

    # 5. Persist scenario artifacts
    # a) pareto.csv
    pareto_rows = []
    for idx, s in enumerate(archive):
        o = s.raw_objectives if s.raw_objectives is not None else s.objectives
        pareto_rows.append({
            "solution_id": f"sol_{idx:03d}",
            "fuel_cost_usd": float(o[0]),
            "ghg_wtw_tco2e": float(o[1]),
            "opex_usd": float(o[2]),
            "is_knee": idx == knee_idx,
        })
    df_p = pd.DataFrame(pareto_rows)
    df_p.to_csv(scen_dir / "pareto.csv", index=False)

    # b) solution_knee.json
    knee_dict = _serialize_solution(knee_sol, vessels, routes)
    knee_dict["solution_id"] = f"sol_{knee_idx:03d}"
    (scen_dir / "solution_knee.json").write_text(json.dumps(knee_dict, indent=2), encoding="utf-8")

    # c) bau_baseline.json
    bau_dict = _serialize_solution(bau_sol, vessels, routes)
    (scen_dir / "bau_baseline.json").write_text(json.dumps(bau_dict, indent=2), encoding="utf-8")

    # d) history.json
    (scen_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")

    # e) summary.json
    bau_deployed = int(bau_sol.observed["assignment"].any(axis=1).sum())
    summary_data = {
        "scenario_name": name,
        "carbon_price": carbon_price,
        "elapsed_seconds": round(elapsed, 2),
        "pop_size": pop_size,
        "generations": generations,
        "pareto_size": len(archive),
        "knee_feasible": bool(knee_sol.feasible),
        "knee_violations": {k: float(v) for k, v in getattr(knee_sol, "violations", {}).items()},
        "bau_feasible": bool(bau_sol.feasible),
        "bau_violations": {k: float(v) for k, v in getattr(bau_sol, "violations", {}).items()},
        "vessels_deployed": int(deployed.sum()),
        "bau_vessels_deployed": bau_deployed,
        "fleet_size": len(vessels),
        "routes_count": len(routes),
        "bau_kpis": {"fuel_cost_usd": bau_fc, "ghg_wtw_tco2e": bau_ghg, "opex_usd": bau_opex},
        "knee_kpis": {"fuel_cost_usd": knee_fc, "ghg_wtw_tco2e": knee_ghg, "opex_usd": knee_opex},
        "deltas": {
            "fuel_cost_delta": delta_fc,
            "fuel_cost_pct": delta_fc_pct,
            "ghg_delta": delta_ghg,
            "ghg_pct": delta_ghg_pct,
            "opex_delta": delta_opex,
            "opex_pct": delta_opex_pct,
        },
        "fuel_mix_pct": fuel_mix_pct,
        "fuel_switches_count": switches,
        "avg_speed_delta_kn": round(avg_speed_delta, 2),
    }
    (scen_dir / "summary.json").write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    print(f"Scenario '{name}' finished in {elapsed:.1f}s | Saved artifacts to {scen_dir}")
    return summary_data


def sustained_crossover(sweep_df: pd.DataFrame) -> float | None:
    """Lowest price from which green methanol's share stays >= HFO's at every higher price.

    A single noisy point where the shares happen to cross is not a crossover.
    """
    ok = ((sweep_df["meoh_pct"] > 0) & (sweep_df["meoh_pct"] >= sweep_df["hfo_pct"])).to_numpy()
    prices = sweep_df["carbon_price"].to_numpy()
    for i in range(len(ok)):
        if ok[i:].all():
            return float(prices[i])
    return None


def run_carbon_price_sweep(
    vessels: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    predictor: FuelPredictor,
    output_dir: Path,
    prices: list[float] | None = None,
    pop_size: int = 100,
    generations: int = 100,
) -> tuple[pd.DataFrame, float | None]:
    """Carbon-price sweep: fuel shares of the deployed fleet at each price.

    Every price runs with the same seed and budget, so differences between
    prices come from the price, not from sampling noise. Returns the first price
    at which green methanol's share of deployed ships reaches HFO's, or None
    when that never happens inside the swept range.
    """
    if prices is None:
        prices = [0.0, 25.0, 50.0, 75.0, 100.0, 125.0, 150.0, 175.0, 200.0]

    print(f"\n{'='*70}\n[Sensitivity Analysis] Carbon-price sweep {prices} ({pop_size}x{generations})\n{'='*70}")

    records = []
    base_fuel_prices = {"HFO": 650.0, "LNG_DIESEL": 800.0, "MEOH_GREEN": 1200.0, "H2_GREEN": 3000.0, "NH3_GREEN": 2500.0}

    for c_price in prices:
        cfg = {
            "pop_size": pop_size,
            "generations": generations,
            "theta_start": 0.05 * np.pi,
            "theta_end": 0.005 * np.pi,
            "mutation_prob": 0.02,
            "lambda0": 10.0,
            "fuel_prices": base_fuel_prices,
            "carbon_price": c_price,
            "archive_max": 100,
            "seed": 42,
        }
        arch, _ = run_qiea(vessels, routes, cfg, predictor)
        knee_s, _ = _find_knee_solution(arch)

        obs = getattr(knee_s, "observed", {})
        deployed = obs.get("assignment", np.zeros((len(vessels), len(routes)), dtype=bool)).any(axis=1)
        f_indices = obs.get("fuel", np.zeros(len(vessels), dtype=int))[deployed]
        tot = max(1, len(f_indices))
        share = lambda i: round(float(np.sum(f_indices == i)) / tot * 100.0, 1)  # noqa: E731
        raw = knee_s.raw_objectives if knee_s.raw_objectives is not None else knee_s.objectives

        records.append({
            "carbon_price": c_price,
            "hfo_pct": share(0),
            "lng_pct": share(1),
            "meoh_pct": share(2),
            "vessels_deployed": int(deployed.sum()),
            "ghg_wtw_tco2e": float(raw[1]),
            "opex_usd": float(raw[2]),
        })
        print(f"Carbon ${c_price:03.0f}/t | HFO {share(0)}% | LNG {share(1)}% | MeOH {share(2)}% of {tot} deployed")

    sweep_df = pd.DataFrame(records)

    crossover_price = sustained_crossover(sweep_df)

    fig_sweep = carbon_sweep(sweep_df)
    fig_to_base64_png(fig_sweep, save_filename="carbon_sweep.png")
    out_chart = _PROJECT_ROOT / "outputs" / "carbon_sweep.png"
    fig_to_base64_png(fig_sweep, save_filename=str(out_chart))

    csv_out = output_dir / "carbon_sweep.csv"
    sweep_df.to_csv(csv_out, index=False)
    print(
        f"Carbon sweep done: "
        + (f"methanol reaches HFO's share at ${crossover_price:.0f}/t" if crossover_price is not None else "no methanol/HFO crossover in range")
        + f" (saved {csv_out})"
    )
    return sweep_df, crossover_price


def _pct(v: float) -> str:
    return f"{v:+.1f}%"


def write_case_study_markdown(
    summaries: list[dict[str, Any]],
    crossover_price: float | None,
    output_path: Path,
    sweep_df: pd.DataFrame | None = None,
) -> None:
    """Write the case-study report. Every number in it is read from the run results."""
    by_name = {s["scenario_name"]: s for s in summaries}
    first = summaries[0]
    evals = first["pop_size"] * first["generations"]
    lines: list[str] = [
        "# QGreenFleet Case Study Results",
        "",
        "*Generated by `python -m src.case_study.run` — every figure below is computed from "
        "`outputs/case_study/*/summary.json`; nothing is typed in by hand.*",
        "",
        f"Reference fleet: {first['fleet_size']} vessels on {first['routes_count']} route corridors. "
        f"Search budget per scenario: population {first['pop_size']} × {first['generations']} generations "
        f"({evals:,} evaluations), seed 42.",
        "",
        "## Recommended (knee) plan vs business-as-usual",
        "",
        "| Scenario | Carbon price | Fuel cost | Δ vs BAU | WtW CO₂e | Δ vs BAU | OPEX Δ | Ships deployed | Fuel switches | Avg speed Δ | Feasible |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for s in summaries:
        d = s["deltas"]
        lines.append(
            f"| {s['scenario_name']} | ${s['carbon_price']:.0f}/t | ${s['knee_kpis']['fuel_cost_usd']/1e6:.2f}M | "
            f"{_pct(d['fuel_cost_pct'])} | {s['knee_kpis']['ghg_wtw_tco2e']:,.0f} t | {_pct(d['ghg_pct'])} | "
            f"{_pct(d['opex_pct'])} | {s['vessels_deployed']} (BAU {s['bau_vessels_deployed']}) | "
            f"{s['fuel_switches_count']} | {s['avg_speed_delta_kn']:+.2f} kn | {'yes' if s['knee_feasible'] else 'NO'} |"
        )

    lines += ["", "## Findings", ""]
    base = by_name.get("baseline", first)
    bd = base["deltas"]
    verb = lambda v: "cuts" if v < 0 else "raises"  # noqa: E731
    lines.append(
        f"1. **Baseline.** The recommended plan {verb(bd['fuel_cost_pct'])} fuel cost by {abs(bd['fuel_cost_pct']):.1f}% "
        f"(${abs(bd['fuel_cost_delta'])/1e6:.2f}M) and {verb(bd['ghg_pct'])} well-to-wake CO₂e by {abs(bd['ghg_pct']):.1f}% "
        f"({abs(bd['ghg_delta']):,.0f} t) against business-as-usual, deploying {base['vessels_deployed']} ships "
        f"at an average of {base['avg_speed_delta_kn']:+.2f} kn versus BAU speed."
    )
    mix = ", ".join(f"{k} {v:.0f}%" for k, v in sorted(base["fuel_mix_pct"].items(), key=lambda kv: -kv[1]))
    lines.append(f"2. **Fuel mix of deployed ships (baseline):** {mix}.")
    if sweep_df is not None and not sweep_df.empty:
        lo, hi = sweep_df.iloc[0], sweep_df.iloc[-1]
        cross = (
            f"from ${crossover_price:.0f}/t-CO₂e upward, green methanol's share of deployed ships stays at or above HFO's"
            if crossover_price is not None
            else "there is no sustained crossover — green methanol's share never stays at or above HFO's across the rest of the range"
        )
        lines.append(
            f"3. **Carbon price sweep (${lo['carbon_price']:.0f}–${hi['carbon_price']:.0f}/t):** {cross}. "
            f"Methanol share goes {lo['meoh_pct']:.0f}% → {hi['meoh_pct']:.0f}%, HFO {lo['hfo_pct']:.0f}% → {hi['hfo_pct']:.0f}%."
        )
    cii = by_name.get("cii_tightened")
    if cii is not None:
        same = abs(cii["knee_kpis"]["opex_usd"] - base["knee_kpis"]["opex_usd"]) < 1.0
        lines.append(
            "4. **Tightened CII (−11% limit):** "
            + ("the recommended plan is unchanged — the tighter limit does not bind for this fleet at the chosen speeds."
               if same else
               f"the plan changes: OPEX {_pct(cii['deltas']['opex_pct'])} and CO₂e {_pct(cii['deltas']['ghg_pct'])} vs BAU; "
               f"BAU itself {'meets' if cii['bau_feasible'] else 'violates'} the tightened limit.")
        )
    corridor = by_name.get("green_corridor")
    if corridor is not None:
        cmix = ", ".join(f"{k} {v:.0f}%" for k, v in sorted(corridor["fuel_mix_pct"].items(), key=lambda kv: -kv[1]))
        lines.append(
            "5. **Green corridor what-if** (hypothetical H₂/NH₃ bunkering on one route, dual-fuel container ships, "
            f"$100/t carbon): deployed fuel mix {cmix}; CO₂e {_pct(corridor['deltas']['ghg_pct'])} and OPEX "
            f"{_pct(corridor['deltas']['opex_pct'])} vs BAU."
        )
    infeasible = [s["scenario_name"] for s in summaries if not s["knee_feasible"]]
    lines.append(
        f"{6 if corridor is not None else 5}. **Constraints:** "
        + ("every recommended plan meets route demand, schedules, fuel availability, vessel availability and CII."
           if not infeasible else f"recommended plans still violating a constraint: {', '.join(infeasible)}.")
    )
    lines += [
        "",
        "## Modelling limits",
        "- Route demand and vessel capacity share one unit: TEU for container ships, deadweight tonnes for bulk "
        "carriers and tankers. Treat capacity coverage as indicative across ship types.",
        "- Hydrogen and ammonia need bunkering infrastructure and engines the committed fleet does not have; they "
        "are only selectable in the green-corridor what-if, whose infrastructure is hypothetical.",
        "- Fuel consumption comes from the EU MRV model with admiralty-law speed scaling; see "
        "`outputs/mrv_model_report.md` for its measured accuracy.",
        "",
        "![Carbon price sweep](../outputs/carbon_sweep.png)",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nGenerated case study report at {output_path}")


def main() -> None:
    """CLI Entry point."""
    parser = argparse.ArgumentParser(description="Execute QGreenFleet Case Study Suite.")
    parser.add_argument("--fleet", type=Path, default=DEFAULT_FLEET, help="Path to fleet JSON")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--pop", type=int, default=200, help="Population size")
    parser.add_argument("--gens", type=int, default=300, help="Generations")
    parser.add_argument("--fast", action="store_true", help="Fast execution mode")
    parser.add_argument("--skip-sweep", action="store_true", help="Skip carbon price sweep")
    args = parser.parse_args()

    vessels, routes = load_fleet_data(args.fleet)
    predictor = FuelPredictor()

    pop_size = args.pop if not args.fast else 30
    generations = args.gens if not args.fast else 25

    args.output_dir.mkdir(parents=True, exist_ok=True)

    base_prices = {"HFO": 650.0, "LNG_DIESEL": 800.0, "MEOH_GREEN": 1200.0, "H2_GREEN": 3000.0, "NH3_GREEN": 2500.0}
    subsidized_prices = copy.deepcopy(base_prices)
    subsidized_prices["MEOH_GREEN"] = 960.0  # -20% discount

    # Tightened CII fleet copy
    vessels_tightened = copy.deepcopy(vessels)
    for v in vessels_tightened:
        dwt = float(v.get("dwt", 50000))
        base_cii = float(v.get("cii_limit", 1984.0 * (dwt ** -0.489)))
        v["cii_limit"] = base_cii * 0.89  # Tighten by one rating band (11% reduction)

    # Green-corridor what-if: the last route gains H2/NH3 bunkering and the
    # container ships gain dual-fuel H2/NH3 capability. Hypothetical by design.
    vessels_corridor = copy.deepcopy(vessels)
    for v in vessels_corridor:
        if v.get("type") == "container":
            v["fuels_allowed"] = list(dict.fromkeys(list(v.get("fuels_allowed", ["HFO"])) + ["H2_GREEN", "NH3_GREEN"]))
    routes_corridor = copy.deepcopy(routes)
    routes_corridor[-1]["h2_available"] = True
    routes_corridor[-1]["nh3_available"] = True

    scenarios_config = [
        ("baseline", vessels, routes, base_prices, 0.0),
        ("carbon_100", vessels, routes, base_prices, 100.0),
        ("cii_tightened", vessels_tightened, routes, base_prices, 0.0),
        ("meoh_subsidized", vessels, routes, subsidized_prices, 0.0),
        ("green_corridor", vessels_corridor, routes_corridor, base_prices, 100.0),
    ]

    summaries = []
    for name, v_list, r_list, p_dict, c_tax in scenarios_config:
        s_res = run_scenario(
            name=name,
            vessels=v_list,
            routes=r_list,
            predictor=predictor,
            fuel_prices=p_dict,
            carbon_price=c_tax,
            pop_size=pop_size,
            generations=generations,
            output_dir=args.output_dir,
        )
        summaries.append(s_res)

    # Carbon Price Sensitivity Sweep
    crossover_price: float | None = None
    sweep_df = None
    if not args.skip_sweep:
        sweep_pop, sweep_gens = (30, 25) if args.fast else (100, 100)
        sweep_df, crossover_price = run_carbon_price_sweep(
            vessels, routes, predictor, args.output_dir, pop_size=sweep_pop, generations=sweep_gens
        )

    # Write Case Study Markdown
    doc_out = _PROJECT_ROOT / "docs" / "case-study-results.md"
    write_case_study_markdown(summaries, crossover_price, doc_out, sweep_df=sweep_df)

    print("\n" + "=" * 70)
    print(f"All {len(summaries)} case-study scenarios and the sensitivity sweep completed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
