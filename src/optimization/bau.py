"""Business-As-Usual (BAU) fleet deployment baseline.

Framework-free counterfactual used by both the Streamlit UI and the HTTP API as
the reference point for every KPI delta reported by QGreenFleet.

BAU characteristics:
    - Fuel: every ship burns Heavy Fuel Oil (HFO).
    - Speed: design speed, raised to the schedule minimum where necessary.
    - Routing: first-fit greedy assignment satisfying commercial route demand.
    - Shore power: disconnected (0% port electrification).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from src.emissions.factors import OPTIMIZER_FUELS
from src.optimization.constraints import evaluate_violations
from src.optimization.individual import Solution
from src.optimization.objectives import evaluate_objectives

DEFAULT_FUEL_PRICES: dict[str, float] = {
    "HFO": 650.0,
    "LNG_DIESEL": 800.0,
    "MEOH_GREEN": 1200.0,
    "H2_GREEN": 3000.0,
    "NH3_GREEN": 2500.0,
}


def compute_bau_baseline(
    vessels: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    predictor: Any,
    fuel_prices: dict[str, float] | None = None,
    carbon_price: float = 0.0,
) -> Solution:
    """Compute the Business-As-Usual fleet deployment baseline.

    Args:
        vessels: Fleet vessel catalog.
        routes: Commercial routes.
        predictor: FuelPredictor instance.
        fuel_prices: Fuel price per metric ton.
        carbon_price: Carbon tax in $/t-CO2e.

    Returns:
        Evaluated Solution instance representing the BAU baseline.
    """
    if fuel_prices is None:
        fuel_prices = dict(DEFAULT_FUEL_PRICES)

    V = len(vessels)
    R = len(routes)
    P = R

    # Cruising speeds set to design speed or schedule minimum
    speeds = np.zeros((V, R), dtype=float)
    for v_idx in range(V):
        ds = float(vessels[v_idx].get("design_speed", 15.0))
        for r_idx in range(R):
            dist = float(routes[r_idx].get("distance_nm", 1000.0))
            days = float(routes[r_idx].get("schedule_days", 7.0))
            sched_spd = dist / max(1.0, days * 24.0)
            speeds[v_idx, r_idx] = max(ds, sched_spd)

    # First-fit assignment meeting route demand
    assignment = np.zeros((V, R), dtype=bool)
    vessel_used = np.zeros(V, dtype=bool)

    for r_idx in range(R):
        req_demand = float(routes[r_idx].get("demand_teu", 2000.0))
        curr_cap = 0.0

        for v_idx in range(V):
            if not vessel_used[v_idx]:
                cap = float(vessels[v_idx].get("capacity_teu", 1000.0))
                assignment[v_idx, r_idx] = True
                curr_cap += cap
                vessel_used[v_idx] = True
                if curr_cap >= req_demand:
                    break

    # If any routes still need capacity, assign remaining vessels
    for r_idx in range(R):
        req_demand = float(routes[r_idx].get("demand_teu", 2000.0))
        curr_cap = sum(float(vessels[v]["capacity_teu"]) for v in range(V) if assignment[v, r_idx])
        if curr_cap < req_demand:
            for v_idx in range(V):
                if not assignment[v_idx, r_idx]:
                    assignment[v_idx, r_idx] = True
                    curr_cap += float(vessels[v_idx].get("capacity_teu", 1000.0))
                    if curr_cap >= req_demand:
                        break

    # All vessels use HFO (index 0)
    fuel_indices = np.zeros(V, dtype=int)
    # No shore power
    shore_power = np.zeros((V, P), dtype=bool)

    n_bits = V * R + V * len(OPTIMIZER_FUELS) + V * P
    bau_sol = Solution(
        q_matrix=np.full((n_bits, 2), 1.0 / np.sqrt(2.0)),
        speeds=speeds,
    )
    bau_sol.observed = {
        "assignment": assignment,
        "fuel": fuel_indices,
        "shore_power": shore_power,
    }

    viols = evaluate_violations(bau_sol, vessels, routes, fuels=OPTIMIZER_FUELS)
    bau_sol.violations = viols
    bau_sol.feasible = bool(sum(viols.values()) <= 1e-6)

    evaluate_objectives(
        sol=bau_sol,
        vessels=vessels,
        routes=routes,
        predictor=predictor,
        fuel_prices=fuel_prices,
        carbon_price=carbon_price,
        penalty_val=0.0,
    )

    return bau_sol
