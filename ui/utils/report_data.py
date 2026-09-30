"""Single source of truth for QGreenFleet dual reporting (Executive Summary & Technical Report).

Every figure in the returned dictionary is computed from the data passed in (or
from committed model/benchmark artefacts on disk). When the inputs needed for a
figure are missing, the figure is ``None`` and the report templates show "—" or
omit the sentence. Nothing here invents a fallback number.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.emissions.factors import OPTIMIZER_FUELS, lhv_mj_per_kg, ttw_co2_tons
from src.optimization.constraints import evaluate_violations
from src.optimization.individual import Solution
from src.optimization.objectives import compute_voyage_metrics
from ui.utils.chart_helpers import sweep_crossover

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# IMO CII rating boundaries d1..d4 (MEPC.354(78)). These are the bulk-carrier
# d-vectors, used here as a common approximation for every ship type:
# A <= d1 < B <= d2 < C <= d3 < D <= d4 < E, applied to attained/required CII.
_CII_D = (0.86, 0.94, 1.06, 1.18)

# US EPA: a typical passenger vehicle emits about 4.6 t CO2 per year
# (EPA "Greenhouse Gas Emissions from a Typical Passenger Vehicle").
_T_CO2_PER_CAR_YEAR = 4.6


# --------------------------------------------------------------------- #
#  Small helpers                                                         #
# --------------------------------------------------------------------- #
def _objs(s: Any) -> tuple[float, float, float] | None:
    """[fuel_cost, ghg, opex] of a solution: raw (unpenalised) when available, else None."""
    if isinstance(s, Solution):
        arr = s.raw_objectives if s.raw_objectives is not None else s.objectives
        return None if arr is None else (float(arr[0]), float(arr[1]), float(arr[2]))
    if isinstance(s, dict):
        o = s.get("objectives") if isinstance(s.get("objectives"), dict) else s
        keys = ("fuel_cost_usd", "ghg_wtw_tco2e", "opex_usd")
        if all(o.get(k) is not None for k in keys):
            return tuple(float(o[k]) for k in keys)  # type: ignore[return-value]
    return None


def _decisions(s: Any, n_vessels: int, n_routes: int) -> Solution | None:
    """The solution if it carries decoded decisions matching the fleet, else None."""
    if not isinstance(s, Solution):
        return None
    obs = s.observed or {}
    x = obs.get("assignment")
    if x is None or "fuel" not in obs or np.shape(x) != (n_vessels, n_routes):
        return None
    if np.shape(s.speeds) != (n_vessels, n_routes):
        return None
    return s


def _variant(
    sol: Solution,
    *,
    assignment: np.ndarray | None = None,
    fuel: np.ndarray | None = None,
    speeds: np.ndarray | None = None,
    shore_off: bool = False,
) -> Solution:
    """Copy of *sol* with some decisions replaced (never mutates *sol*)."""
    obs = dict(sol.observed)
    obs["assignment"] = np.array(obs["assignment"] if assignment is None else assignment, dtype=bool)
    obs["fuel"] = np.array(obs["fuel"] if fuel is None else fuel, dtype=int)
    if obs.get("shore_power") is not None:
        obs["shore_power"] = np.zeros_like(obs["shore_power"]) if shore_off else np.array(obs["shore_power"])
    return Solution(
        q_matrix=sol.q_matrix,
        speeds=np.array(sol.speeds if speeds is None else speeds, dtype=float),
        observed=obs,
    )


def _cii_ratio(sol: Solution, v: int, vessels: list[Any], routes: list[Any]) -> float | None:
    """Attained / required CII of vessel v, mirroring constraints.evaluate_violations (C4)."""
    x = sol.observed["assignment"]
    assigned = np.where(x[v])[0]
    if len(assigned) == 0:
        return None
    ves = vessels[v]
    dwt = float(ves.get("dwt", 50000.0))
    dists = np.array([float(routes[r].get("distance_nm", 1000.0)) for r in assigned])
    if dists.sum() <= 0 or dwt <= 0:
        return None
    limit = float(ves.get("cii_limit", 1984.0 * dwt ** -0.489))
    f_i = int(sol.observed["fuel"][v])
    fuel_name = OPTIMIZER_FUELS[f_i] if f_i < len(OPTIMIZER_FUELS) else OPTIMIZER_FUELS[0]
    design = max(1.0, float(ves.get("design_speed", 15.0)))
    ratio = (sol.speeds[v, assigned] / design) ** 2
    fuel_kg = float(np.sum(dists * float(ves.get("fuel_per_nm_kg", 150.0)) * ratio))
    fuel_kg *= lhv_mj_per_kg("HFO") / lhv_mj_per_kg(fuel_name)
    attained = ttw_co2_tons(fuel_name, fuel_kg) * 1000.0 / (dwt * dists.sum())
    return attained / limit


def _cii_band(ratio: float | None) -> str | None:
    if ratio is None:
        return None
    for band, d in zip("ABCD", _CII_D):
        if ratio <= d:
            return band
    return "E"


def _constraint_status(sol: Solution | None, vessels: list[Any], routes: list[Any]) -> dict[str, Any] | None:
    """Violations, demand coverage and CII bands of a solution with decisions."""
    if sol is None:
        return None
    probe = _variant(sol)
    viol = evaluate_violations(probe, vessels, routes)
    total_demand = sum(float(r.get("demand_teu", 0.0)) for r in routes)
    bands = [_cii_band(_cii_ratio(sol, v, vessels, routes)) for v in range(len(vessels))]
    deployed = [b for b in bands if b is not None]
    return {
        "feasible": bool(probe.feasible),
        "violations": {k: float(val) for k, val in viol.items()},
        "demand_met_pct": (100.0 * (1.0 - viol["demand_deficit"] / total_demand)) if total_demand > 0 else None,
        "cii_bands": bands,
        "deployed": len(deployed),
        "cii_a_to_c": sum(1 for b in deployed if b in "ABC"),
    }


def _ghg(sol: Solution, vessels: list[Any], routes: list[Any], predictor: Any, fuel_prices: dict[str, float]) -> float:
    return compute_voyage_metrics(sol, vessels, routes, predictor, fuel_prices)[1]


def _decompose_ghg(
    plan: Solution, bau: Solution, vessels: list[Any], routes: list[Any], predictor: Any, fuel_prices: dict[str, float]
) -> dict[str, float]:
    """Exact additive attribution of the GHG change BAU -> plan (positive = reduction).

    A = plan assignment, all HFO, BAU speeds, no shore power
    B = plan assignment, all HFO, plan speeds, no shore power
    D = plan with shore power off
    C = plan
    """
    hfo = np.zeros(len(vessels), dtype=int)
    g_bau = _ghg(bau, vessels, routes, predictor, fuel_prices)
    g_a = _ghg(_variant(plan, fuel=hfo, speeds=bau.speeds, shore_off=True), vessels, routes, predictor, fuel_prices)
    g_b = _ghg(_variant(plan, fuel=hfo, shore_off=True), vessels, routes, predictor, fuel_prices)
    g_d = _ghg(_variant(plan, shore_off=True), vessels, routes, predictor, fuel_prices)
    g_c = _ghg(plan, vessels, routes, predictor, fuel_prices)
    return {
        "bau_t": g_bau,
        "plan_t": g_c,
        "deployment_t": g_bau - g_a,
        "slow_steaming_t": g_a - g_b,
        "fuel_switch_t": g_b - g_d,
        "shore_power_t": g_d - g_c,
        "total_reduction_t": g_bau - g_c,
    }


def _find_knee_solution(pareto_solutions: list[Solution | dict[str, Any]]) -> tuple[Any, int]:
    """Knee = minimum normalised Euclidean distance to the utopia point (raw objectives)."""
    if not pareto_solutions:
        raise ValueError("Cannot find knee of empty Pareto set.")
    idx = [i for i, s in enumerate(pareto_solutions) if _objs(s) is not None]
    if not idx:
        raise ValueError("No Pareto solution carries objective values.")
    arr = np.array([_objs(pareto_solutions[i]) for i in idx])
    span = np.maximum(arr.max(axis=0) - arr.min(axis=0), 1e-6)
    dists = np.sqrt((((arr - arr.min(axis=0)) / span) ** 2).sum(axis=1))
    knee_idx = idx[int(np.argmin(dists))]
    return pareto_solutions[knee_idx], knee_idx


# --------------------------------------------------------------------- #
#  Disk artefacts: model metrics and benchmark CSV                       #
# --------------------------------------------------------------------- #
def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _model_metrics(models_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Rows for the prediction-model table, straight from models/*_meta.json."""
    def row(model: str, m: dict[str, Any] | None, unit: str, cv: str = "—", selected: str = "") -> dict[str, Any]:
        m = m or {}
        return {
            "model": model,
            "cv_rmse": cv,
            "test_rmse": f"{m['rmse']:.2f} {unit}" if m.get("rmse") is not None else "—",
            "test_mape": f"{m['mape']:.1f}%" if m.get("mape") is not None else "—",
            "test_r2": f"{m['r2']:.3f}" if m.get("r2") is not None else "—",
            "selected": selected,
        }

    rows: list[dict[str, Any]] = []
    mrv = _read_json(models_dir / "mrv_best_meta.json")
    mrv_info = None
    if mrv:
        cv = mrv.get("cv_5fold") or {}
        cv_str = (
            f"{cv['rmse_mean']:.2f} ± {cv['rmse_std']:.2f} kg/nm"
            if cv.get("rmse_mean") is not None and cv.get("rmse_std") is not None else "—"
        )
        name = mrv.get("model_type", "MRV model")
        rows.append(row(f"Stage 1: MRV {name} (held-out ships)", mrv.get("test_metrics"), "kg/nm", cv_str, "★ used"))
        if mrv.get("fleet_inference_metrics"):
            rows.append(row(f"Stage 1: MRV {name} (fleet-inference features)", mrv["fleet_inference_metrics"], "kg/nm"))
        if mrv.get("default_xgb_metrics"):
            rows.append(row("MRV XGBoost, default hyper-parameters", mrv["default_xgb_metrics"], "kg/nm"))
        if mrv.get("category_median_baseline_metrics"):
            rows.append(row("Per-category median (no model)", mrv["category_median_baseline_metrics"], "kg/nm"))
        n = sum(int(mrv.get(k) or 0) for k in ("train_samples", "test_samples"))
        mrv_info = {"records": n or None, "dataset": mrv.get("dataset"), "test_metrics": mrv.get("test_metrics")}
    voy = _read_json(models_dir / "best_meta.json")
    if voy and voy.get("metrics"):
        m = voy["metrics"]
        cv_str = (
            f"{m['cv_rmse_mean']:.2f} ± {m['cv_rmse_std']:.2f} t/d"
            if m.get("cv_rmse_mean") is not None and m.get("cv_rmse_std") is not None else "—"
        )
        rows.append(row(
            f"Stage 2: voyage {voy.get('model_name', 'model')}",
            {"rmse": m.get("test_rmse"), "mape": m.get("test_mape"), "r2": m.get("test_r2")},
            "t/d", cv_str, "not used — dataset has no learnable signal",
        ))
    return rows, mrv_info


_INSTANCE_ORDER = {"S": 1, "M": 2, "L": 3, "XL": 4}


def _instance_sizes() -> dict[str, int]:
    """Vessel count per benchmark instance, parsed from configs/benchmark.yaml fleet file names."""
    try:
        import yaml
        cfg = yaml.safe_load((_PROJECT_ROOT / "configs" / "benchmark.yaml").read_text(encoding="utf-8"))
        out = {}
        for name, spec in (cfg.get("instances") or {}).items():
            m = re.search(r"_(\d+)v_", str(spec.get("fleet", "")))
            if m:
                out[str(name)] = int(m.group(1))
        return out
    except Exception:
        return {}


def _compute_method_comparison(csv_path: str | Path | None = None) -> dict[str, Any] | None:
    """Per-instance / per-algorithm benchmark means from outputs/benchmark_results.csv.

    Returns None when the CSV is missing or unusable.
    """
    path = Path(csv_path) if csv_path is not None else _PROJECT_ROOT / "outputs" / "benchmark_results.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if df.empty or not {"algo", "instance", "wall_time_s"}.issubset(df.columns):
        return None

    instances = sorted(df["instance"].astype(str).unique(), key=lambda x: _INSTANCE_ORDER.get(x, 99))
    algos = list(dict.fromkeys(df["algo"].astype(str)))
    metric_cols = [c for c in ("wall_time_s", "hv", "igd", "archive_size", "feasible_count") if c in df.columns]
    means = df.groupby([df["instance"].astype(str), df["algo"].astype(str)])[metric_cols].mean()

    def mean(inst: str, algo: str, col: str) -> float | None:
        try:
            v = means.loc[(inst, algo), col]
        except KeyError:
            return None
        return None if pd.isna(v) else float(v)

    per_instance = []
    hv_best = 0
    hv_compared = 0
    sizes = _instance_sizes()
    for inst in instances:
        entry: dict[str, Any] = {"instance": inst, "n_vessels": sizes.get(inst), "algos": {}}
        for a in algos:
            entry["algos"][a] = {c: mean(inst, a, c) for c in metric_cols}
        q_t, g_t = mean(inst, "QIEA", "wall_time_s"), mean(inst, "GA", "wall_time_s")
        entry["speedup_vs_ga"] = (g_t / q_t) if q_t and g_t else None
        if "hv" in metric_cols:
            hvs = {a: mean(inst, a, "hv") for a in algos}
            hvs = {a: v for a, v in hvs.items() if v is not None}
            if "QIEA" in hvs and len(hvs) > 1:
                hv_compared += 1
                entry["hv_best_algo"] = max(hvs, key=hvs.get)
                hv_best += int(entry["hv_best_algo"] == "QIEA")
        per_instance.append(entry)

    return {
        "algos": algos,
        "instances": per_instance,
        "n_seeds": int(df["seed"].nunique()) if "seed" in df.columns else None,
        "qiea_hv_best_count": hv_best if hv_compared else None,
        "hv_instances_compared": hv_compared or None,
    }


def _sensitivity(sweep_results: Any) -> dict[str, Any] | None:
    """Carbon-price sweep series plus the crossover derived from them (None without series)."""
    if sweep_results is None:
        return None
    cols = ("carbon_price", "hfo_pct", "lng_pct", "meoh_pct")
    if isinstance(sweep_results, pd.DataFrame):
        if sweep_results.empty or not set(cols).issubset(sweep_results.columns):
            return None
        series = {c: [float(v) for v in sweep_results[c]] for c in cols}
    elif isinstance(sweep_results, dict) and all(isinstance(sweep_results.get(c), (list, tuple)) for c in cols):
        series = {c: [float(v) for v in sweep_results[c]] for c in cols}
    else:
        return None
    if not series["carbon_price"]:
        return None
    return {**series, "crossover_carbon_price": sweep_crossover(series)}


# --------------------------------------------------------------------- #
#  Main entry point                                                      #
# --------------------------------------------------------------------- #
def build_report_data(
    solution: Solution | dict[str, Any],
    pareto: list[Solution | dict[str, Any]],
    history: dict[str, list[Any]] | None,
    fleet: dict[str, Any],
    bau: Solution | dict[str, Any] | None,
    scenarios: list[dict[str, Any]] | None = None,
    sweep_results: pd.DataFrame | dict[str, Any] | None = None,
    benchmark_csv_path: str | Path | None = None,
    *,
    predictor: Any = None,
    fuel_prices: dict[str, float] | None = None,
    carbon_price: float = 0.0,
    models_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Construct the unified report dictionary for both report templates.

    Args:
        solution: Selected recommended solution (typically the knee).
        pareto: Non-dominated archive.
        history: Convergence history (unused by the templates; kept for callers).
        fleet: Fleet catalog with "vessels" and "routes".
        bau: Business-as-usual baseline solution.
        scenarios: Unused; kept for callers.
        sweep_results: Carbon sweep with carbon_price/hfo_pct/lng_pct/meoh_pct series.
        benchmark_csv_path: Benchmark CSV (defaults to outputs/benchmark_results.csv).
        predictor: Fuel predictor. Required for per-vessel cost/GHG and the GHG decomposition.
        fuel_prices: Fuel prices ($/t). Required for per-vessel fuel cost.
        carbon_price: Carbon price used for the run ($/t CO2e), reported as metadata.
        models_dir: Directory holding *_meta.json (defaults to models/).

    Returns:
        Report dictionary. Any figure that cannot be computed from the inputs is None.
    """
    vessels = list(fleet.get("vessels", []))
    routes = list(fleet.get("routes", []))
    V, R = len(vessels), len(routes)

    bau_o = _objs(bau)
    opt_o = _objs(solution)

    def kpi(i: int) -> dict[str, float | None]:
        b = bau_o[i] if bau_o else None
        o = opt_o[i] if opt_o else None
        d = (o - b) if (b is not None and o is not None) else None
        return {"bau": b, "opt": o, "delta": d, "delta_pct": (100.0 * d / b) if (d is not None and b) else None}

    fc_k, ghg_k, opex_k = kpi(0), kpi(1), kpi(2)
    ghg_delta = ghg_k["delta"]
    cars_equivalent = (
        int(round(-ghg_delta / _T_CO2_PER_CAR_YEAR)) if ghg_delta is not None and ghg_delta < 0 else None
    )

    # Pareto points, knee and three options
    valid = [(i, s) for i, s in enumerate(pareto or []) if _objs(s) is not None]
    pareto_points = [
        {"solution_id": f"sol_{i:03d}", "fuel_cost_usd": o[0], "ghg_wtw_tco2e": o[1], "opex_usd": o[2]}
        for i, s in valid for o in [_objs(s)]
    ]
    knee_id = None
    knee_idx = None
    three_options: list[dict[str, Any]] = []
    if valid:
        knee_sol, knee_idx = _find_knee_solution(pareto)
        knee_id = f"sol_{knee_idx:03d}"
        cheapest = min(valid, key=lambda t: _objs(t[1])[0])[1]
        greenest = min(valid, key=lambda t: _objs(t[1])[1])[1]
        c_o = _objs(cheapest)
        for tier, name, s, best_for in (
            ("Cheapest", "💵 Cheapest", cheapest, "Tight budgets"),
            ("Recommended", "⭐ Recommended", knee_sol, "Balanced"),
            ("Greenest", "🌱 Greenest", greenest, "Emission targets"),
        ):
            o = _objs(s)
            extra = o[0] - c_o[0]
            three_options.append({
                "tier": tier,
                "name": name,
                "fuel_cost_usd": o[0],
                "ghg_wtw_tco2e": o[1],
                "opex_usd": o[2],
                "extra_cost_vs_cheapest_usd": extra,
                "extra_cost_vs_cheapest": f"{'+' if extra >= 0 else '−'}${abs(extra) / 1e6:.2f}M",
                "best_for": best_for,
            })
    solution_is_knee = knee_idx is not None and pareto[knee_idx] is solution

    # Share of the cheapest -> greenest GHG gap closed by the recommended option
    recommended_share = None
    if len(three_options) == 3:
        gap = three_options[0]["ghg_wtw_tco2e"] - three_options[2]["ghg_wtw_tco2e"]
        cost_gap = three_options[2]["fuel_cost_usd"] - three_options[0]["fuel_cost_usd"]
        if gap > 0:
            recommended_share = {
                "ghg_pct": 100.0 * (three_options[0]["ghg_wtw_tco2e"] - three_options[1]["ghg_wtw_tco2e"]) / gap,
                "cost_pct": (100.0 * three_options[1]["extra_cost_vs_cheapest_usd"] / cost_gap) if cost_gap > 0 else None,
            }

    # Decisions (only Solution objects carry them)
    plan = _decisions(solution, V, R)
    bau_d = _decisions(bau, V, R)
    plan_status = _constraint_status(plan, vessels, routes)
    bau_status = _constraint_status(bau_d, vessels, routes)

    decomposition = None
    if predictor is not None and plan is not None and bau_d is not None:
        decomposition = _decompose_ghg(plan, bau_d, vessels, routes, predictor, fuel_prices or {})

    # Per-vessel plan
    per_vessel_plan: list[dict[str, Any]] = []
    fuel_counts: dict[str, int] = {}
    if plan is not None:
        x = plan.observed["assignment"]
        for v_idx, v in enumerate(vessels):
            assigned = np.where(x[v_idx])[0]
            deployed = len(assigned) > 0
            f_code = int(plan.observed["fuel"][v_idx])
            fuel_name = OPTIMIZER_FUELS[f_code] if f_code < len(OPTIMIZER_FUELS) else OPTIMIZER_FUELS[0]
            r0 = int(assigned[0]) if deployed else None
            speed = float(plan.speeds[v_idx, r0]) if deployed else None
            bau_speed = float(bau_d.speeds[v_idx, r0]) if (deployed and bau_d is not None) else None
            bau_assigned = bool(bau_d.observed["assignment"][v_idx].any()) if bau_d is not None else None

            changes = []
            if deployed:
                fuel_counts[fuel_name] = fuel_counts.get(fuel_name, 0) + 1
                if bau_assigned is False:
                    changes.append("deployed (reserve in BAU)")
                if fuel_name != "HFO":
                    changes.append(f"switched to {fuel_name}")
                if speed is not None and bau_speed is not None and abs(speed - bau_speed) >= 0.5:
                    changes.append(f"{'slowed' if speed < bau_speed else 'sped up'} {abs(speed - bau_speed):.1f} kn")
            elif bau_assigned:
                changes.append("held in reserve (deployed in BAU)")

            v_cost = v_ghg = None
            if predictor is not None and deployed:
                keep = np.zeros_like(x)
                keep[v_idx] = x[v_idx]
                fc, g, _ = compute_voyage_metrics(_variant(plan, assignment=keep), vessels, routes, predictor, fuel_prices or {})
                v_ghg = round(g, 0)
                v_cost = round(fc, 0) if fuel_prices else None

            per_vessel_plan.append({
                "vessel_id": v.get("id", f"V{v_idx:03d}"),
                "type": v.get("type"),
                "dwt": v.get("dwt"),
                "route_id": routes[r0].get("id", f"R{r0}") if deployed else "Reserve",
                "speed_kn": round(speed, 1) if speed is not None else None,
                "bau_speed_kn": round(bau_speed, 1) if bau_speed is not None else None,
                "fuel": fuel_name if deployed else None,
                "fuel_cost": v_cost,
                "ghg_tco2e": v_ghg,
                "cii_band": plan_status["cii_bands"][v_idx] if plan_status else None,
                "change_vs_bau": ", ".join(changes) if changes else "no change",
            })

    total_deployed = sum(fuel_counts.values())
    fuel_mix_pct = {k: round(100.0 * n / total_deployed, 1) for k, n in fuel_counts.items()} if total_deployed else {}
    changed = [p for p in per_vessel_plan if p["change_vs_bau"] != "no change"]
    top_5_ships = changed[:5]

    # Predictor curves for the technical report (draft 10 m, moderate weather)
    speed_fuel_points = None
    if predictor is not None and hasattr(predictor, "predict_tpd"):
        grid = np.linspace(5.0, 25.0, 41)
        try:
            speed_fuel_points = {
                st: {"speed": grid.tolist(), "tpd": np.atleast_1d(predictor.predict_tpd(grid, 10.0, 1, st)).astype(float).tolist()}
                for st in sorted({str(v.get("type")) for v in vessels if v.get("type")})
            } or None
        except Exception:
            speed_fuel_points = None

    mdir = Path(models_dir) if models_dir is not None else _PROJECT_ROOT / "models"
    model_metrics, mrv_info = _model_metrics(mdir)
    method_comparison = _compute_method_comparison(benchmark_csv_path)

    def cii_str(st: dict[str, Any] | None) -> str | None:
        return f"{st['cii_a_to_c']}/{st['deployed']} deployed in A–C" if st and st["deployed"] else None

    now = datetime.now()
    digest_src = json.dumps([opt_o, bau_o, V, R, now.isoformat()], default=str)
    report_id = f"QGF-{now:%Y%m%d}-{hashlib.sha1(digest_src.encode()).hexdigest()[:8].upper()}"

    return {
        "report_id": report_id,
        "date": now.date().isoformat(),
        "fleet_size": V,
        "routes_count": R,
        "carbon_price": float(carbon_price),
        "routes": [
            {k: r.get(k) for k in ("id", "from", "to", "distance_nm", "shore_power")} for r in routes
        ],
        "kpi_deltas": {
            "fuel_cost": fc_k,
            "ghg_wtw": ghg_k,
            "opex": opex_k,
            "demand_satisfied": f"{plan_status['demand_met_pct']:.1f}%" if plan_status and plan_status["demand_met_pct"] is not None else None,
            "schedule_delay_h": plan_status["violations"]["schedule_delay"] if plan_status else None,
            "cii_bands": cii_str(plan_status),
            "bau_cii_bands": cii_str(bau_status),
        },
        "constraints": {"plan": plan_status, "bau": bau_status},
        "cars_equivalent": cars_equivalent,
        "three_options": three_options,
        "recommended_share": recommended_share,
        "pareto_points": pareto_points,
        "savings_decomposition": decomposition,
        "per_vessel_plan": per_vessel_plan,
        "speed_fuel_points": speed_fuel_points,
        "top_5_ships": top_5_ships,
        "fuel_mix_pct": fuel_mix_pct,
        "model_metrics": model_metrics,
        "mrv_info": mrv_info,
        "benchmark_summary": method_comparison,
        "method_comparison": method_comparison,
        "sensitivity": _sensitivity(sweep_results),
        "selected_knee_id": knee_id,
        "solution_is_knee": solution_is_knee,
        "generations": len(history.get("hypervolume", [])) if isinstance(history, dict) and history.get("hypervolume") else None,
    }
