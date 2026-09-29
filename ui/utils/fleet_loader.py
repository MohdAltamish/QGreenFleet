"""Fleet loading, validation, and Business-As-Usual (BAU) baseline generation."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.optimization.bau import compute_bau_baseline  # re-exported for the UI pages

__all__ = [
    "compute_bau_baseline",
    "ensure_session_state",
    "load_fleet",
    "preload_case_study_results",
]


@st.cache_resource
def preload_case_study_results() -> dict[str, dict[str, Any]]:
    """Load all 4 scenario results at startup for instant access."""
    import json
    from pathlib import Path
    import pandas as pd

    results: dict[str, dict[str, Any]] = {}
    base = Path("outputs/case_study")
    if not base.exists():
        base = _PROJECT_ROOT / "outputs" / "case_study"

    for scenario in ["baseline", "carbon_100", "cii_tightened", "meoh_subsidized"]:
        p = base / scenario
        if p.exists():
            try:
                data: dict[str, Any] = {
                    "pareto": pd.read_csv(p / "pareto.csv"),
                    "knee": json.loads((p / "solution_knee.json").read_text(encoding="utf-8")),
                    "bau": json.loads((p / "bau_baseline.json").read_text(encoding="utf-8")),
                }
                if (p / "history.json").exists():
                    try:
                        data["history"] = json.loads((p / "history.json").read_text(encoding="utf-8"))
                    except Exception:
                        pass
                results[scenario] = data
            except Exception:
                pass
    return results


def ensure_session_state() -> None:
    """Ensure all global session state keys are initialized so any subpage works on direct navigation."""
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
        st.session_state.preloaded_scenarios = preload_case_study_results()

    if "last_pareto" not in st.session_state or not st.session_state.last_pareto:
        if st.session_state.get("preloaded_scenarios") and "baseline" in st.session_state.preloaded_scenarios:
            b_data = st.session_state.preloaded_scenarios["baseline"]
            p_val = b_data["pareto"]
            st.session_state.last_pareto = p_val.to_dict(orient="records") if isinstance(p_val, pd.DataFrame) else p_val
            st.session_state.selected_solution = b_data["knee"]
            if b_data.get("bau"):
                st.session_state.bau_baseline = b_data["bau"]
            if b_data.get("history"):
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
