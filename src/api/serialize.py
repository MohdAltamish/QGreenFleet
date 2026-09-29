"""Conversion of internal optimizer objects into JSON-serializable payloads.

The optimizer works with numpy-backed `Solution` dataclasses; the persisted
case-study artifacts are plain dicts loaded from JSON. Both shapes reach the
API, so every helper here accepts either.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from src.emissions.factors import OPTIMIZER_FUELS
from src.optimization.individual import Solution

OBJECTIVE_KEYS: tuple[str, str, str] = ("fuel_cost_usd", "ghg_wtw_tco2e", "opex_usd")


def to_jsonable(value: Any) -> Any:
    """Recursively convert numpy scalars/arrays and pandas NaN into JSON types."""
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return to_jsonable(value.tolist())
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        # JSON has no NaN/Infinity — surface them as null instead.
        return None if (np.isnan(f) or np.isinf(f)) else f
    return value


def objectives_of(sol: Any) -> tuple[float, float, float]:
    """Extract (fuel_cost_usd, ghg_wtw_tco2e, opex_usd) from a Solution or dict."""
    if isinstance(sol, Solution) and sol.objectives is not None:
        return float(sol.objectives[0]), float(sol.objectives[1]), float(sol.objectives[2])
    if isinstance(sol, dict):
        nested = sol.get("objectives", {})
        return tuple(  # type: ignore[return-value]
            float(nested.get(key, sol.get(key, 0.0))) for key in OBJECTIVE_KEYS
        )
    return 0.0, 0.0, 0.0


def _observed(sol: Any) -> dict[str, Any]:
    if isinstance(sol, Solution):
        return sol.observed or {}
    return sol if isinstance(sol, dict) else {}


def fuel_name(index: Any) -> str:
    """Map a fuel decision index onto its canonical fuel name."""
    idx = int(index)
    return OPTIMIZER_FUELS[idx] if 0 <= idx < len(OPTIMIZER_FUELS) else OPTIMIZER_FUELS[0]


def assignments_of(
    sol: Any,
    vessels: list[dict[str, Any]],
    routes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the vessel→route deployment list for a Solution or persisted dict.

    Persisted solution JSON already carries an explicit ``assignments`` (live
    optimizer runs) or ``vessels`` (BAU artifacts) list; those are returned as-is.
    """
    if isinstance(sol, dict):
        if isinstance(sol.get("assignments"), list):
            return [dict(a) for a in sol["assignments"]]
        if isinstance(sol.get("vessels"), list):
            return [
                {
                    "vessel_id": row.get("vessel_id"),
                    "route_id": row.get("route_id"),
                    "speed_kn": row.get("speed_kn"),
                    "fuel": row.get("fuel"),
                    "shore_power": row.get("shore_power", False),
                }
                for row in sol["vessels"]
                if row.get("route_id") not in (None, "Unassigned", "Reserve")
            ]
        return []

    obs = _observed(sol)
    assignment = obs.get("assignment")
    if assignment is None:
        return []
    fuels = obs.get("fuel", np.zeros(len(vessels), dtype=int))
    shore_power = obs.get("shore_power")
    speeds = getattr(sol, "speeds", np.full((len(vessels), len(routes)), 15.0))

    rows: list[dict[str, Any]] = []
    for v_idx, vessel in enumerate(vessels):
        for r_idx, route in enumerate(routes):
            if not bool(assignment[v_idx, r_idx]):
                continue
            sp = False
            if shore_power is not None and r_idx < shore_power.shape[1]:
                sp = bool(shore_power[v_idx, r_idx])
            rows.append({
                "vessel_id": vessel.get("id", f"V{v_idx:03d}"),
                "route_id": route.get("id", f"R{r_idx}"),
                "speed_kn": round(float(speeds[v_idx, r_idx]), 2),
                "fuel": fuel_name(fuels[v_idx]) if v_idx < len(fuels) else OPTIMIZER_FUELS[0],
                "shore_power": sp,
            })
    return rows


def solution_payload(
    sol: Any,
    vessels: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    solution_id: str | None = None,
) -> dict[str, Any]:
    """Serialize one solution (objectives, feasibility, deployment) for the API."""
    z1, z2, z3 = objectives_of(sol)
    if isinstance(sol, Solution):
        feasible = bool(sol.feasible)
        violations = sol.violations or {}
        sol_id = solution_id or "sol_000"
    else:
        feasible = bool(sol.get("feasible", True))
        violations = sol.get("violations", {}) or {}
        sol_id = solution_id or sol.get("id") or sol.get("solution_id") or "sol_000"

    return to_jsonable({
        "solution_id": sol_id,
        "objectives": dict(zip(OBJECTIVE_KEYS, (z1, z2, z3))),
        "feasible": feasible,
        "violations": violations,
        "assignments": assignments_of(sol, vessels, routes),
    })


def pareto_payload(
    archive: list[Any],
    vessels: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    knee_index: int | None = None,
) -> list[dict[str, Any]]:
    """Serialize a Pareto archive into flat rows suited to scatter plots."""
    rows: list[dict[str, Any]] = []
    for idx, sol in enumerate(archive):
        z1, z2, z3 = objectives_of(sol)
        if isinstance(sol, dict):
            sol_id = sol.get("solution_id") or sol.get("id") or f"sol_{idx:03d}"
            feasible = bool(sol.get("feasible", True))
        else:
            sol_id = f"sol_{idx:03d}"
            feasible = bool(sol.feasible)
        rows.append({
            "solution_id": sol_id,
            "fuel_cost_usd": z1,
            "ghg_wtw_tco2e": z2,
            "opex_usd": z3,
            "feasible": feasible,
            "is_knee": knee_index is not None and idx == knee_index,
            "deployments_count": len(assignments_of(sol, vessels, routes)),
        })
    return to_jsonable(rows)
