"""Operational constraints evaluation and repair operators for QGreenFleet.

Implements demand satisfaction (C1), schedule limits (C2/C6), fuel availability (C5),
and Carbon Intensity Indicator (C4) constraint evaluation and greedy repair.

References:
    - docs/mathematical-model.md §Constraints C1–C6
    - docs/algorithms.md §1 Loop (Repair & Penalties)
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from src.optimization.individual import OPTIMIZER_FUELS, Solution


def _get_val(obj: Any, key: str, default: Any = 0.0) -> Any:
    """Safely get attribute or dict value."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def repair(
    sol: Solution,
    vessels: Sequence[Any],
    routes: Sequence[Any],
    fuels: Sequence[str] = OPTIMIZER_FUELS,
) -> Solution:
    """Greedily repair constraint violations on an observed Solution.

    Repairs applied:
        1. C1 Demand repair: If total vessel capacity on route r < demand,
           greedily assign unassigned vessels with highest capacity until met.
        2. C2/C6 Speed clipping: Clip speeds to vessel [vmin, vmax] and to
           minimum schedule-feasible speed D_r / (T_r * 24).
        3. Fuel availability repair: If assigned fuel is not bunkerable on all
           assigned routes, fallback to HFO (fuel index 0).

    Args:
        sol: Observed Solution instance.
        vessels: List of vessel dictionaries or domain models.
        routes: List of route dictionaries or domain models.
        fuels: Tuple of supported fuel names.

    Returns:
        The repaired Solution instance.
    """
    V = len(vessels)
    R = len(routes)

    if "assignment" not in sol.observed or "fuel" not in sol.observed:
        return sol

    x = sol.observed["assignment"].copy()
    f_idx = sol.observed["fuel"].copy()
    speeds = sol.speeds.copy()

    # 1. C1 Demand repair (Greedy capacity addition)
    vessel_caps = np.array([float(_get_val(v, "capacity_teu", _get_val(v, "dwt", 0.0))) for v in vessels])

    for r in range(R):
        demand = float(_get_val(routes[r], "demand_teu", 0.0))
        assigned_cap = np.sum(vessel_caps[x[:, r]])

        if assigned_cap < demand:
            # Unassigned candidate vessels for route r
            unassigned_indices = np.where(~x[:, r])[0]
            if len(unassigned_indices) > 0:
                # Sort unassigned by capacity descending
                order = np.argsort(-vessel_caps[unassigned_indices])
                for idx in unassigned_indices[order]:
                    x[idx, r] = True
                    assigned_cap += vessel_caps[idx]
                    if assigned_cap >= demand:
                        break

    # 2. C2 & C6 Speed clip to [vmin, vmax] and schedule-feasible speed D_r / (T_r * 24)
    for v in range(V):
        vmin = float(_get_val(vessels[v], "vmin", 8.0))
        vmax = float(_get_val(vessels[v], "vmax", 22.0))

        for r in range(R):
            dist = float(_get_val(routes[r], "distance_nm", 1000.0))
            sched_days = float(_get_val(routes[r], "schedule_days", 10.0))
            sched_hours = max(1.0, sched_days * 24.0)
            min_sched_speed = dist / sched_hours

            # Lower bound is max(vmin, schedule-feasible speed)
            lo = max(vmin, min_sched_speed)
            hi = max(lo, vmax)
            speeds[v, r] = np.clip(speeds[v, r], lo, hi)

    # 3. Fuel availability repair: verify bunkerability on assigned routes
    for v in range(V):
        assigned_routes = np.where(x[v, :])[0]
        if len(assigned_routes) == 0:
            continue

        selected_fuel = fuels[f_idx[v]] if f_idx[v] < len(fuels) else fuels[0]
        allowed_fuels = _get_val(vessels[v], "fuels_allowed", [fuels[0]])

        # Check vessel engine capability
        is_allowed = selected_fuel in allowed_fuels

        # Check route port infrastructure
        is_bunkerable = True
        if selected_fuel == "LNG_DIESEL":
            is_bunkerable = all(bool(_get_val(routes[r], "lng_available", True)) for r in assigned_routes)
        elif selected_fuel == "MEOH_GREEN":
            is_bunkerable = all(bool(_get_val(routes[r], "meoh_available", False)) for r in assigned_routes)
        elif selected_fuel in ("H2_GREEN", "NH3_GREEN"):
            is_bunkerable = False  # Not yet commercial on route ports

        if not (is_allowed and is_bunkerable):
            f_idx[v] = 0  # Fallback to universally available HFO

    sol.observed["assignment"] = x
    sol.observed["fuel"] = f_idx
    sol.speeds = speeds
    return sol


def evaluate_violations(
    sol: Solution,
    vessels: Sequence[Any],
    routes: Sequence[Any],
    fuels: Sequence[str] = OPTIMIZER_FUELS,
) -> dict[str, float]:
    """Quantify constraint violation magnitudes on an observed solution.

    Computes:
        - demand_deficit: Missing cargo capacity across commercial routes.
        - cii_excess: Excess operational carbon intensity over regulatory limit.
        - fuel_unavailable: Non-zero if vessel runs an un-bunkerable fuel.
        - schedule_delay: Excess hours if speed is below schedule window.

    Args:
        sol: Candidate Solution.
        vessels: List of vessel specifications.
        routes: List of route parameters.
        fuels: Tuple of fuel names.

    Returns:
        Dictionary of non-negative violation values.
    """
    V = len(vessels)
    R = len(routes)

    violations: dict[str, float] = {
        "demand_deficit": 0.0,
        "cii_excess": 0.0,
        "fuel_unavailable": 0.0,
        "schedule_delay": 0.0,
    }

    if "assignment" not in sol.observed or "fuel" not in sol.observed:
        violations["demand_deficit"] = 1000.0
        sol.feasible = False
        sol.violations = violations
        return violations

    x = sol.observed["assignment"]
    f_idx = sol.observed["fuel"]
    speeds = sol.speeds

    vessel_caps = np.array([float(_get_val(v, "capacity_teu", _get_val(v, "dwt", 0.0))) for v in vessels])

    # 1. Demand deficit (Eq. C1)
    for r in range(R):
        demand = float(_get_val(routes[r], "demand_teu", 0.0))
        assigned_cap = np.sum(vessel_caps[x[:, r]])
        if assigned_cap < demand:
            violations["demand_deficit"] += float(demand - assigned_cap)

    # 2. Schedule delay (Eq. C2)
    for v in range(V):
        for r in range(R):
            if x[v, r]:
                dist = float(_get_val(routes[r], "distance_nm", 1000.0))
                sched_hours = float(_get_val(routes[r], "schedule_days", 10.0)) * 24.0
                actual_hours = dist / max(1.0, speeds[v, r])
                if actual_hours > sched_hours:
                    violations["schedule_delay"] += float(actual_hours - sched_hours)

    # 3. Fuel availability (Eq. C5)
    for v in range(V):
        assigned_routes = np.where(x[v, :])[0]
        if len(assigned_routes) == 0:
            continue

        selected_fuel = fuels[f_idx[v]] if f_idx[v] < len(fuels) else fuels[0]
        allowed_fuels = _get_val(vessels[v], "fuels_allowed", [fuels[0]])

        if selected_fuel not in allowed_fuels:
            violations["fuel_unavailable"] += 1.0
            continue

        if selected_fuel == "LNG_DIESEL":
            if not all(bool(_get_val(routes[r], "lng_available", True)) for r in assigned_routes):
                violations["fuel_unavailable"] += 1.0
        elif selected_fuel == "MEOH_GREEN":
            if not all(bool(_get_val(routes[r], "meoh_available", False)) for r in assigned_routes):
                violations["fuel_unavailable"] += 1.0
        elif selected_fuel in ("H2_GREEN", "NH3_GREEN"):
            violations["fuel_unavailable"] += 1.0

    # 4. CII emissions limit check (Eq. C4)
    # attained_CII_v = (annual_CO2_g) / (DWT_v * annual_distance_nm)
    # Default CII limit benchmark line: 1984 * DWT^(-0.489)
    for v in range(V):
        assigned_routes = np.where(x[v, :])[0]
        if len(assigned_routes) == 0:
            continue

        dwt = float(_get_val(vessels[v], "dwt", 50000.0))
        tot_dist = sum(float(_get_val(routes[r], "distance_nm", 1000.0)) for r in assigned_routes)
        if tot_dist <= 0 or dwt <= 0:
            continue

        # Benchmark reference line limit
        cii_limit = float(_get_val(vessels[v], "cii_limit", 1984.0 * (dwt ** -0.489)))
        fuel_rate_kg = float(_get_val(vessels[v], "fuel_per_nm_kg", 150.0))
        # 3.114 g-CO2 per g-fuel (HFO standard carbon factor)
        annual_co2_g = tot_dist * fuel_rate_kg * 1000.0 * 3.114
        attained_cii = annual_co2_g / (dwt * tot_dist)

        if attained_cii > cii_limit:
            violations["cii_excess"] += float(attained_cii - cii_limit)

    total_violation = sum(violations.values())
    sol.feasible = bool(total_violation == 0.0)
    sol.violations = violations
    return violations


def penalty(violations: dict[str, float], lambda_g: float) -> float:
    """Compute adaptive scalar penalty from constraint violations.

    Penalty formula:
        penalty = lambda_g * sum(violations)
        where lambda_g = lambda0 * (1 + g / G)^2

    Args:
        violations: Dictionary of violation magnitudes.
        lambda_g: Current adaptive penalty scaling factor.

    Returns:
        Scalar penalty value to be added to objective functions.
    """
    total_violation = float(sum(violations.values()))
    return lambda_g * total_violation
