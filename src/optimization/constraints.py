"""Operational constraints evaluation and repair operators for QGreenFleet.

Implements demand satisfaction (C1), schedule limits (C2/C6), vessel availability
(C3), fuel availability (C5), and Carbon Intensity Indicator (C4) constraint
evaluation and greedy repair.

References:
    - docs/mathematical-model.md §Constraints C1–C6
    - docs/algorithms.md §1 Loop (Repair & Penalties)
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from src.emissions.factors import lhv_mj_per_kg, ttw_co2_tons
from src.optimization.individual import OPTIMIZER_FUELS, Solution


def _get_val(obj: Any, key: str, default: Any = 0.0) -> Any:
    """Safely get attribute or dict value."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# HFO reference price used only to rank vessels inside repair ($/kg).
_REPAIR_HFO_USD_PER_KG = 0.65


def _leg_cost_proxy(vessel: Any, route: Any) -> float:
    """Rough cost of vessel v sailing route r at design speed (charter + HFO fuel), in $.

    Used only to order candidates during repair; the real objective is computed
    by evaluate_objectives().
    """
    dist = float(_get_val(route, "distance_nm", 1000.0))
    speed = max(1.0, float(_get_val(vessel, "design_speed", 15.0)))
    days = dist / (24.0 * speed)
    charter = float(_get_val(vessel, "charter_per_day", 15000.0)) * days
    fuel = float(_get_val(vessel, "fuel_per_nm_kg", 150.0)) * dist * _REPAIR_HFO_USD_PER_KG
    return charter + fuel


def _can_meet_schedule(vessel: Any, route: Any) -> bool:
    """True if the vessel's vmax reaches the route's schedule-feasible speed (C2/C6)."""
    dist = float(_get_val(route, "distance_nm", 1000.0))
    sched_hours = max(1.0, float(_get_val(route, "schedule_days", 10.0)) * 24.0)
    return float(_get_val(vessel, "vmax", 22.0)) >= dist / sched_hours


def repair(
    sol: Solution,
    vessels: Sequence[Any],
    routes: Sequence[Any],
    fuels: Sequence[str] = OPTIMIZER_FUELS,
) -> Solution:
    """Greedily repair constraint violations on an observed Solution.

    Repairs applied, in order:
        1. C3 Availability: a vessel serves at most one route per planning
           period (available_days_v equals one route schedule window). Extra
           routes are dropped, keeping the one where the vessel is most needed.
        2. C1 Demand (add): while a route is short of capacity, add the cheapest
           idle, schedule-capable vessel that closes the gap on its own, or the
           largest one if none can.
        3. C1 Demand (prune): drop the most expensive assigned vessels while
           the route's demand stays met — without this, random initial
           assignments leave capacity at many times demand.
        4. C2/C6 Speed clipping to [max(vmin, D_r / (T_r*24)), vmax].
        5. C5 Fuel availability: fall back to HFO when the chosen fuel is not
           allowed on the vessel or not bunkerable on its route.

    The repaired decisions are written back into observed["bits"] (Lamarckian
    repair), so the rotation gates learn the repaired assignment rather than
    the raw measurement.

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

    vessel_caps = np.array([float(_get_val(v, "capacity_teu", _get_val(v, "dwt", 0.0))) for v in vessels])
    demands = np.array([float(_get_val(r, "demand_teu", 0.0)) for r in routes])
    cost = np.array([[_leg_cost_proxy(vessels[v], routes[r]) for r in range(R)] for v in range(V)])
    capable = np.array([[_can_meet_schedule(vessels[v], routes[r]) for r in range(R)] for v in range(V)])

    # 1. C3: at most one route per vessel. Keep the route with the largest
    #    shortfall once the vessel is removed from it.
    for v in range(V):
        assigned = np.where(x[v])[0]
        if len(assigned) <= 1:
            continue
        shortfall = [demands[r] - (np.sum(vessel_caps[x[:, r]]) - vessel_caps[v]) for r in assigned]
        keep = assigned[int(np.argmax(shortfall))]
        x[v, :] = False
        x[v, keep] = True

    # 2. C1 add: cover each route's deficit with idle capable vessels.
    for r in range(R):
        assigned_cap = float(np.sum(vessel_caps[x[:, r]]))
        while assigned_cap < demands[r]:
            idle = np.where(~x.any(axis=1) & capable[:, r])[0]
            if len(idle) == 0:
                break  # demand deficit stays and is penalised
            gap = demands[r] - assigned_cap
            closers = idle[vessel_caps[idle] >= gap]
            pick = closers[np.argmin(cost[closers, r])] if len(closers) else idle[np.argmax(vessel_caps[idle])]
            x[pick, r] = True
            assigned_cap += vessel_caps[pick]

    # 3. C1 prune: drop surplus vessels, most expensive first.
    for r in range(R):
        assigned = np.where(x[:, r])[0]
        assigned_cap = float(np.sum(vessel_caps[assigned]))
        for v in assigned[np.argsort(-cost[assigned, r])]:
            if assigned_cap - vessel_caps[v] >= demands[r]:
                x[v, r] = False
                assigned_cap -= vessel_caps[v]

    # 4. C2 & C6: speed within [max(vmin, schedule speed), vmax]. A vessel that
    #    cannot reach the schedule speed sails at vmax and C2 penalises it.
    for v in range(V):
        vmin = float(_get_val(vessels[v], "vmin", 8.0))
        vmax = float(_get_val(vessels[v], "vmax", 22.0))
        for r in range(R):
            dist = float(_get_val(routes[r], "distance_nm", 1000.0))
            sched_hours = max(1.0, float(_get_val(routes[r], "schedule_days", 10.0)) * 24.0)
            lo = min(max(vmin, dist / sched_hours), vmax)
            speeds[v, r] = np.clip(speeds[v, r], lo, vmax)

    # 5. C5: fuel availability on the vessel and its route's ports.
    for v in range(V):
        assigned_routes = np.where(x[v, :])[0]
        if len(assigned_routes) == 0:
            continue

        selected_fuel = fuels[f_idx[v]] if f_idx[v] < len(fuels) else fuels[0]
        allowed_fuels = _get_val(vessels[v], "fuels_allowed", [fuels[0]])
        if not (selected_fuel in allowed_fuels and _fuel_bunkerable(selected_fuel, [routes[r] for r in assigned_routes])):
            f_idx[v] = 0  # Fallback to universally available HFO

    sol.observed["assignment"] = x
    sol.observed["fuel"] = f_idx
    sol.speeds = speeds

    # Lamarckian write-back: the rotation gates read these bits.
    bits = sol.observed.get("bits")
    n_fuels = len(fuels)
    if bits is not None and len(bits) >= V * R + V * n_fuels:
        bits = np.asarray(bits, dtype=int).copy()
        bits[: V * R] = x.ravel().astype(int)
        fuel_block = np.zeros((V, n_fuels), dtype=int)
        fuel_block[np.arange(V), np.clip(f_idx, 0, n_fuels - 1)] = 1
        bits[V * R : V * R + V * n_fuels] = fuel_block.ravel()
        sol.observed["bits"] = bits
    return sol


def _fuel_bunkerable(fuel: str, assigned_routes: Sequence[Any]) -> bool:
    """C5 port infrastructure: can *fuel* be bunkered on every assigned route?

    Hydrogen and ammonia need an explicit route flag (h2_available /
    nh3_available); no route in the committed fleets sets one, so they are
    modelled but not yet selectable there.
    """
    flag = {
        "LNG_DIESEL": ("lng_available", True),
        "MEOH_GREEN": ("meoh_available", False),
        "H2_GREEN": ("h2_available", False),
        "NH3_GREEN": ("nh3_available", False),
    }.get(fuel)
    if flag is None:
        return True
    key, default = flag
    return all(bool(_get_val(r, key, default)) for r in assigned_routes)


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
        "vessel_overbooked": 0.0,
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
        if selected_fuel not in allowed_fuels or not _fuel_bunkerable(
            selected_fuel, [routes[r] for r in assigned_routes]
        ):
            violations["fuel_unavailable"] += 1.0

    # 3b. Vessel availability (Eq. C3): one route per vessel per planning period.
    violations["vessel_overbooked"] = float(np.sum(np.maximum(0, x.sum(axis=1) - 1)))

    # 4. CII emissions limit check (Eq. C4)
    # attained_CII_v = annual_CO2_g / (DWT_v * annual_distance_nm), with
    # annual CO2 from the vessel's own speed and fuel: fuel per nm scales with
    # speed^2 (admiralty law) and is converted to the chosen fuel by energy
    # content before applying that fuel's TtW carbon factor.
    for v in range(V):
        assigned_routes = np.where(x[v, :])[0]
        if len(assigned_routes) == 0:
            continue

        dwt = float(_get_val(vessels[v], "dwt", 50000.0))
        dists = np.array([float(_get_val(routes[r], "distance_nm", 1000.0)) for r in assigned_routes])
        tot_dist = float(dists.sum())
        if tot_dist <= 0 or dwt <= 0:
            continue

        cii_limit = float(_get_val(vessels[v], "cii_limit", 1984.0 * (dwt ** -0.489)))
        fuel_rate_kg = float(_get_val(vessels[v], "fuel_per_nm_kg", 150.0))
        design = max(1.0, float(_get_val(vessels[v], "design_speed", 15.0)))
        fuel_name = fuels[f_idx[v]] if f_idx[v] < len(fuels) else fuels[0]
        ratio = (speeds[v, assigned_routes] / design) ** 2
        fuel_kg_hfo_eq = float(np.sum(dists * fuel_rate_kg * ratio))
        fuel_kg = fuel_kg_hfo_eq * lhv_mj_per_kg("HFO") / lhv_mj_per_kg(fuel_name)
        annual_co2_g = ttw_co2_tons(fuel_name, fuel_kg) * 1000.0  # kg-fuel in -> kg CO2 -> g
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
