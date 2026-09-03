"""Fleet loading, validation, and Business-As-Usual (BAU) baseline generation."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.emissions.factors import OPTIMIZER_FUELS
from src.optimization.constraints import evaluate_violations
from src.optimization.individual import Solution
from src.optimization.objectives import evaluate_objectives


def ensure_session_state() -> None:
    """Ensure all global session state keys are initialized so any subpage works on direct navigation."""
    import streamlit as st
    from src.prediction.predictor import FuelPredictor

    @st.cache_resource
    def _get_predictor() -> FuelPredictor | None:
        try:
            return FuelPredictor()
        except Exception:
            return None

    if "fleet" not in st.session_state or st.session_state.fleet is None:
        default_fleet_path = _PROJECT_ROOT / "data" / "synthetic" / "fleet_20v_5r_seed42.json"
        if default_fleet_path.exists():
            vessels, routes, _ = load_fleet(default_fleet_path)
            st.session_state.fleet = {"vessels": vessels, "routes": routes, "path": str(default_fleet_path)}
        else:
            st.session_state.fleet = None

    if "predictor" not in st.session_state or st.session_state.predictor is None:
        with st.spinner("Loading QGreenFleet..."):
            st.session_state.predictor = _get_predictor()

    # Pre-load case study results at startup for instant scenario switching
    if "preloaded_scenarios" not in st.session_state:
        st.session_state.preloaded_scenarios = {}
        case_study_dir = _PROJECT_ROOT / "outputs" / "case_study"
        if case_study_dir.exists():
            import pandas as pd
            for scen_name in ["baseline", "carbon_100", "cii_tightened", "meoh_subsidized"]:
                s_dir = case_study_dir / scen_name
                if (s_dir / "pareto.csv").exists():
                    df_p = pd.read_csv(s_dir / "pareto.csv")
                    pareto_list = df_p.to_dict(orient="records")
                    knee_s = None
                    if (s_dir / "solution_knee.json").exists():
                        try:
                            knee_s = json.loads((s_dir / "solution_knee.json").read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    bau_b = None
                    if (s_dir / "bau_baseline.json").exists():
                        try:
                            bau_b = json.loads((s_dir / "bau_baseline.json").read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    hist = None
                    if (s_dir / "history.json").exists():
                        try:
                            hist = json.loads((s_dir / "history.json").read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    st.session_state.preloaded_scenarios[scen_name] = {
                        "pareto": pareto_list,
                        "knee": knee_s,
                        "bau": bau_b,
                        "history": hist,
                    }

    if "last_pareto" not in st.session_state or not st.session_state.last_pareto:
        if st.session_state.get("preloaded_scenarios") and "baseline" in st.session_state.preloaded_scenarios:
            b_data = st.session_state.preloaded_scenarios["baseline"]
            st.session_state.last_pareto = b_data["pareto"]
            st.session_state.selected_solution = b_data["knee"]
            if b_data["bau"]:
                st.session_state.bau_baseline = b_data["bau"]
            if b_data["history"]:
                st.session_state.last_history = b_data["history"]
            st.session_state.last_run_time = "Pre-computed (baseline)"
        else:
            pareto_csv = _PROJECT_ROOT / "outputs" / "pareto.csv"
            if pareto_csv.exists():
                import pandas as pd
                df_p = pd.read_csv(pareto_csv)
                st.session_state.last_pareto = df_p.to_dict(orient="records")
            else:
                st.session_state.last_pareto = None

    if "last_history" not in st.session_state:
        st.session_state.last_history = None

    if "scenarios" not in st.session_state:
        st.session_state.scenarios = []

    if "selected_solution" not in st.session_state:
        st.session_state.selected_solution = None

    if "bau_baseline" not in st.session_state or st.session_state.bau_baseline is None:
        if st.session_state.fleet and st.session_state.predictor:
            try:
                st.session_state.bau_baseline = compute_bau_baseline(
                    vessels=st.session_state.fleet["vessels"],
                    routes=st.session_state.fleet["routes"],
                    predictor=st.session_state.predictor,
                )
            except Exception:
                st.session_state.bau_baseline = None
        else:
            st.session_state.bau_baseline = None

    if "last_run_time" not in st.session_state:
        st.session_state.last_run_time = None



def load_fleet(path_or_content: str | Path | dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Load and validate fleet JSON.

    Args:
        path_or_content: File path, JSON string, or parsed dict.

    Returns:
        Tuple of (vessels, routes, error_message).
    """
    try:
        if isinstance(path_or_content, dict):
            data = path_or_content
        elif isinstance(path_or_content, (str, Path)):
            p = Path(path_or_content)
            if p.exists() and p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
            else:
                data = json.loads(str(path_or_content))
        else:
            return [], [], "Invalid input type for fleet data."

        vessels = data.get("vessels", [])
        routes = data.get("routes", [])

        if not vessels:
            return [], [], "Fleet file missing 'vessels' array or array is empty."
        if not routes:
            return [], [], "Fleet file missing 'routes' array or array is empty."

        # Validate basic vessel and route fields
        for idx, v in enumerate(vessels):
            if "id" not in v:
                v["id"] = f"V{idx:03d}"
            if "type" not in v:
                v["type"] = "container"
            if "capacity_teu" not in v and "dwt" in v:
                v["capacity_teu"] = int(v["dwt"] / 12) if v["type"] == "container" else int(v["dwt"])
            if "design_speed" not in v:
                v["design_speed"] = 15.0
            if "fuels_allowed" not in v:
                v["fuels_allowed"] = ["HFO"]

        for idx, r in enumerate(routes):
            if "id" not in r:
                r["id"] = f"R{idx}"
            if "distance_nm" not in r:
                r["distance_nm"] = 1000.0
            if "demand_teu" not in r:
                r["demand_teu"] = 2000
            if "schedule_days" not in r:
                r["schedule_days"] = 7.0

        return vessels, routes, None
    except Exception as exc:
        return [], [], f"Failed to parse fleet data: {exc}"


def compute_bau_baseline(
    vessels: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    predictor: Any,
    fuel_prices: dict[str, float] | None = None,
    carbon_price: float = 0.0,
) -> Solution:
    """Compute Business-As-Usual (BAU) fleet deployment baseline.

    Characteristics:
        - Fuel: All ships burn Heavy Fuel Oil (HFO).
        - Speed: Ships cruise at design speed (or minimum required schedule speed).
        - Routing: First-fit greedily satisfying commercial route demand.
        - Shore Power: Disconnected (0% port electrification).

    Args:
        vessels: Fleet vessel catalog.
        routes: Commercial routes.
        predictor: FuelPredictor instance.
        fuel_prices: Fuel price per metric ton.
        carbon_price: Carbon tax in $/t-CO2e.

    Returns:
        Solution instance representing the BAU baseline.
    """
    if fuel_prices is None:
        fuel_prices = {"HFO": 650.0, "LNG_DIESEL": 800.0, "MEOH_GREEN": 1200.0, "H2_GREEN": 3000.0, "NH3_GREEN": 2500.0}

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
