"""Multi-objective evaluation functions for QGreenFleet.

Evaluates:
    Z1: Fuel cost ($)
    Z2: Well-to-Wake Greenhouse Gas emissions (t-CO2e)
    Z3: Total operating expenditure ($) including chartering and carbon pricing.

References:
    - docs/mathematical-model.md §Objectives (Z1, Z2, Z3)
    - docs/design.md §src/optimization/objectives.py
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import numpy as np

from src.emissions.factors import OPTIMIZER_FUELS, voyage_ghg_tco2e
from src.optimization.individual import Solution


def _get(obj: Any, key: str, default: Any = 0.0) -> Any:
    """Safely get attribute or dictionary value."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


_FLEET_ARRAYS_CACHE: dict[tuple[int, int, int, int], dict[str, np.ndarray]] = {}


def _get_fleet_cached_arrays(vessels: Sequence[Any], routes: Sequence[Any]) -> dict[str, np.ndarray]:
    key = (id(vessels), id(routes), len(vessels), len(routes))
    cached = _FLEET_ARRAYS_CACHE.get(key)
    if cached is not None:
        return cached

    types = np.array([_get(v, "type", "container") for v in vessels])
    dwts = np.array([float(_get(v, "dwt", 50000.0)) for v in vessels])
    drafts = np.array([float(_get(v, "draft_m", 8.0 + 6.0 * (d / 150000.0))) for d, v in zip(dwts, vessels)])
    charters = np.array([float(_get(v, "charter_per_day", 15000.0)) for v in vessels])

    distances = np.array([float(_get(r, "distance_nm", 1000.0)) for r in routes])
    weathers = np.array([int(_get(r, "weather_severity", 1)) for r in routes])
    shore_avail = np.array([bool(_get(r, "shore_power", False)) for r in routes])

    data = {
        "types": types,
        "dwts": dwts,
        "drafts": drafts,
        "charters": charters,
        "distances": distances,
        "weathers": weathers,
        "shore_avail": shore_avail,
    }
    _FLEET_ARRAYS_CACHE[key] = data
    return data


def compute_voyage_metrics(
    sol: Solution,
    vessels: Sequence[Any],
    routes: Sequence[Any],
    predictor: Any,
    fuel_prices: dict[str, float],
    fuels: Sequence[str] = OPTIMIZER_FUELS,
) -> tuple[float, float, float]:
    """Vectorized calculation of voyage fuel consumption, fuel cost, and charter cost.

    Args:
        sol: Observed Solution instance.
        vessels: List of vessel specifications.
        routes: List of route parameters.
        predictor: FuelPredictor instance or compatible callable.
        fuel_prices: Price per metric ton for each fuel type.
        fuels: Tuple of fuel names.

    Returns:
        Tuple of (total_fuel_cost, total_ghg_wtw, total_charter_cost).
    """
    if "assignment" not in sol.observed or "fuel" not in sol.observed:
        return 0.0, 0.0, 0.0

    x = sol.observed["assignment"]
    f_idx = sol.observed["fuel"]
    speeds = sol.speeds
    sp = sol.observed.get("shore_power")

    V = len(vessels)
    R = len(routes)

    total_fuel_cost = 0.0
    total_ghg_wtw = 0.0
    total_charter_cost = 0.0

    # Vectorized extraction of all active assignments in the solution
    v_indices, r_indices = np.where(x)
    if len(v_indices) == 0:
        return 0.0, 0.0, 0.0

    # Extract vessel and route attributes from cached arrays
    arrs = _get_fleet_cached_arrays(vessels, routes)
    types = arrs["types"]
    dwts = arrs["dwts"]
    drafts = arrs["drafts"]
    charters = arrs["charters"]
    distances = arrs["distances"]
    weathers = arrs["weathers"]
    shore_avail = arrs["shore_avail"]

    act_speeds = speeds[v_indices, r_indices]
    act_dists = distances[r_indices]
    act_drafts = drafts[v_indices]
    act_weathers = weathers[r_indices]
    act_types = types[v_indices]
    act_fuels = np.array([fuels[f_idx[v]] if f_idx[v] < len(fuels) else fuels[0] for v in v_indices])
    act_prices = np.array([float(fuel_prices.get(fn, 650.0)) for fn in act_fuels])

    n_act = len(v_indices)
    fuel_tpd_arr = np.zeros(n_act, dtype=float)

    # Predict grouped by ship type (at most 3 calls: container, bulk, tanker)
    unique_types = np.unique(act_types)
    for st in unique_types:
        mask = (act_types == st)
        sub_speeds = act_speeds[mask]
        sub_drafts = act_drafts[mask]
        sub_weathers = act_weathers[mask]

        if hasattr(predictor, "predict_tpd"):
            fuel_tpd_arr[mask] = predictor.predict_tpd(
                speed_kn=sub_speeds,
                draft_m=sub_drafts,
                weather_severity=sub_weathers,
                ship_type=st,
            )
        else:
            k = 0.005 if st == "container" else (0.003 if st == "bulk" else 0.004)
            fuel_tpd_arr[mask] = k * (sub_speeds ** 3) + 1.2 * sub_drafts

    # Voyage duration (days) = distance / (24 * speed)
    voyage_days = act_dists / (24.0 * np.maximum(act_speeds, 1.0))
    fc_voyages = fuel_tpd_arr * voyage_days

    # Fuel cost ($)
    total_fuel_cost = float(np.sum(fc_voyages * act_prices))

    # GHG emissions (t-CO2e)
    total_ghg_wtw = float(sum(
        voyage_ghg_tco2e(f_name, float(fc))
        for f_name, fc in zip(act_fuels, fc_voyages)
    ))

    # Charter cost ($)
    total_charter_cost = float(np.sum(voyage_days * charters[v_indices]))

    # Shore power savings
    if sp is not None:
        for v, r in zip(v_indices, r_indices):
            p_idx = min(r, sp.shape[1] - 1)
            if v < sp.shape[0] and sp[v, p_idx] and shore_avail[r]:
                total_ghg_wtw = max(0.0, total_ghg_wtw - 3.0)

    return total_fuel_cost, total_ghg_wtw, total_charter_cost


def fuel_cost(
    sol: Solution,
    vessels: Sequence[Any],
    routes: Sequence[Any],
    predictor: Any,
    fuel_prices: dict[str, float],
) -> float:
    """Calculate objective Z1: Total fleet fuel expenditure ($)."""
    cost, _, _ = compute_voyage_metrics(sol, vessels, routes, predictor, fuel_prices)
    return cost


def ghg_wtw(
    sol: Solution,
    vessels: Sequence[Any],
    routes: Sequence[Any],
    predictor: Any,
    fuel_prices: dict[str, float],
) -> float:
    """Calculate objective Z2: Total Well-to-Wake greenhouse gas emissions (t-CO2e)."""
    _, ghg, _ = compute_voyage_metrics(sol, vessels, routes, predictor, fuel_prices)
    return ghg


def opex(
    sol: Solution,
    vessels: Sequence[Any],
    routes: Sequence[Any],
    predictor: Any,
    fuel_prices: dict[str, float],
    carbon_price: float = 0.0,
) -> float:
    """Calculate objective Z3: Total Operating Expenditure ($).

    OPEX = Fuel Cost + Charter Costs + Carbon Price * GHG emissions.
    """
    cost, ghg, charter = compute_voyage_metrics(sol, vessels, routes, predictor, fuel_prices)
    return cost + charter + (carbon_price * ghg)


def evaluate_objectives(
    sol: Solution,
    vessels: Sequence[Any],
    routes: Sequence[Any],
    predictor: Any,
    fuel_prices: dict[str, float],
    carbon_price: float = 0.0,
    penalty_val: float = 0.0,
) -> np.ndarray:
    """Evaluate all three objectives [Z1, Z2, Z3] incorporating adaptive penalty.

    Args:
        sol: Candidate Solution.
        vessels: Fleet vessel catalog.
        routes: Route catalog.
        predictor: FuelPredictor inference instance.
        fuel_prices: Dictionary of fuel price per ton.
        carbon_price: Carbon tax in $/t-CO2e.
        penalty_val: Infeasibility penalty magnitude to add to each objective.

    Returns:
        Array of [Z1, Z2, Z3] with added penalties.
    """
    cost, ghg, charter = compute_voyage_metrics(sol, vessels, routes, predictor, fuel_prices)
    total_opex = cost + charter + (carbon_price * ghg)

    sol.raw_objectives = np.array([cost, ghg, total_opex], dtype=float)

    objs = np.array([
        cost + penalty_val,
        ghg + penalty_val,
        total_opex + penalty_val,
    ], dtype=float)

    sol.objectives = objs
    return objs

