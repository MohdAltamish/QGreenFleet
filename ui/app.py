"""QGreenFleet — Quantum-Inspired Green Fleet Optimization Platform (SIH #26138).

Main Streamlit entry point orchestrating global session state, sidebar badges,
navigation, and executive landing overview.

Usage::

    streamlit run ui/app.py
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.prediction.predictor import FuelPredictor
from ui.utils.chart_helpers import system_flow_diagram
from ui.utils.fleet_loader import compute_bau_baseline, load_fleet, preload_case_study_results

# Page configuration
st.set_page_config(
    page_title="QGreenFleet | Green Fleet Optimization",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Task 5 — Check required files on startup
def check_required_files():
    required = [
        "models/best.pkl",
        "data/synthetic/fleet_20v_5r_seed42.json",
        "outputs/case_study/baseline/pareto.csv",
    ]
    missing = [f for f in required if not (Path(f).exists() or (_PROJECT_ROOT / f).exists())]
    if missing:
        st.error(f"Missing required files: {missing}. "
                 f"Run 'make all' to generate them.")
        st.stop()

check_required_files()

# Task 4 — Preload case study results for instant access & memory optimization
preloaded_results = preload_case_study_results()
if "preloaded_scenarios" not in st.session_state:
    st.session_state.preloaded_scenarios = preloaded_results

# Initialize Session State
if "fleet" not in st.session_state:
    # Auto-load default synthetic fleet if available
    default_fleet_path = _PROJECT_ROOT / "data" / "synthetic" / "fleet_20v_5r_seed42.json"
    if default_fleet_path.exists():
        vessels, routes, _ = load_fleet(default_fleet_path)
        st.session_state.fleet = {"vessels": vessels, "routes": routes, "path": str(default_fleet_path)}
    else:
        st.session_state.fleet = None

if "predictor" not in st.session_state:
    try:
        st.session_state.predictor = FuelPredictor()
    except Exception:
        st.session_state.predictor = None

if "last_pareto" not in st.session_state:
    st.session_state.last_pareto = None

if "last_history" not in st.session_state:
    st.session_state.last_history = None

if "scenarios" not in st.session_state:
    st.session_state.scenarios = []

if "selected_solution" not in st.session_state:
    st.session_state.selected_solution = None

if "bau_baseline" not in st.session_state:
    st.session_state.bau_baseline = None

if "last_run_time" not in st.session_state:
    st.session_state.last_run_time = None

# Auto-populate baseline from preloaded scenarios if not set
if st.session_state.last_pareto is None and "baseline" in preloaded_results:
    b_data = preloaded_results["baseline"]
    p_val = b_data["pareto"]
    st.session_state.last_pareto = p_val.to_dict(orient="records") if hasattr(p_val, "to_dict") else p_val
    st.session_state.selected_solution = b_data.get("knee")
    if b_data.get("bau"):
        st.session_state.bau_baseline = b_data.get("bau")
    if b_data.get("history"):
        st.session_state.last_history = b_data.get("history")
    st.session_state.last_run_time = "Pre-computed (baseline)"

# Auto-compute BAU if fleet and predictor exist and not preloaded
if st.session_state.fleet and st.session_state.predictor and st.session_state.bau_baseline is None:
    try:
        st.session_state.bau_baseline = compute_bau_baseline(
            vessels=st.session_state.fleet["vessels"],
            routes=st.session_state.fleet["routes"],
            predictor=st.session_state.predictor,
        )
    except Exception:
        pass

# Task 3 — Deployment detection and badge
is_streamlit_cloud = bool(os.environ.get('STREAMLIT_SHARING_MODE') or
                          os.environ.get('IS_STREAMLIT_CLOUD'))
is_render = bool(os.environ.get('RENDER'))

if is_streamlit_cloud:
    deploy_badge = "☁️ Live on Streamlit Cloud"
elif is_render:
    deploy_badge = "🌐 Live on Render"
elif os.environ.get("SPACE_ID"):
    deploy_badge = "🌐 Live on Hugging Face"
else:
    deploy_badge = "💻 Running locally"

# Sidebar
with st.sidebar:
    st.title("🚢 QGreenFleet")
    st.caption("Quantum-Inspired Green Fleet Optimization")

    st.markdown(
        f"""
        <div style="background-color: #1e3799; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold; font-size: 11px; margin-bottom: 8px; text-align: center;">
            SIH Problem #26138 · Egreen Quanta
        </div>
        <div style="background-color: {'#064e3b' if ('Live' in deploy_badge or 'Cloud' in deploy_badge) else '#1e293b'}; color: {'#34d399' if ('Live' in deploy_badge or 'Cloud' in deploy_badge) else '#94a3b8'}; padding: 6px 12px; border-radius: 4px; font-weight: bold; font-size: 11px; margin-bottom: 12px; text-align: center; border: 1px solid {'#059669' if ('Live' in deploy_badge or 'Cloud' in deploy_badge) else '#334155'};">
            {deploy_badge}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### System Status")
    # Fleet indicator
    if st.session_state.fleet:
        v_cnt = len(st.session_state.fleet.get("vessels", []))
        r_cnt = len(st.session_state.fleet.get("routes", []))
        st.success(f"Fleet Active: {v_cnt} ships, {r_cnt} routes")
    else:
        st.warning("No Fleet Loaded (Visit Page 1)")

    # Predictor indicator
    if st.session_state.predictor:
        st.success(f"ML Surrogate: {st.session_state.predictor.model_name}")
    else:
        st.error("Predictor Offline")

    # Optimization indicator
    if st.session_state.last_pareto:
        n_p = len(st.session_state.last_pareto)
        t_str = st.session_state.last_run_time or "Recent"
        st.info(f"Pareto Front: {n_p} solutions ({t_str})")
    else:
        st.text("Optimizer: Idle")

    st.divider()
    st.markdown("### Quick Navigation")
    st.markdown("1. **Data** — Ingest or generate fleet\n2. **Predict** — Test fuel surrogate\n3. **Optimize** — QIEA+QPSO run\n4. **Scenarios** — Policy & price sweeps\n5. **Report** — Dual PDF export")

# Main Page Landing
col_head, col_action = st.columns([3, 1])
with col_head:
    st.title("Quantum-Inspired Fleet Decarbonization Platform")
    st.markdown(
        """
        **QGreenFleet** solves complex maritime deployment challenges by coupling **Quantum-Inspired Evolutionary Algorithms (QIEA)**
        with continuous **Quantum-behaved Particle Swarm Optimization (QPSO)**.
        """
    )
with col_action:
    st.write("")
    st.write("")
    if st.button("⚡ Launch Quick Demo", type="primary", use_container_width=True):
        st.switch_page("pages/3_Optimize.py")


# Render interactive system flow diagram hero visual
st.plotly_chart(
    system_flow_diagram(),
    use_container_width=True,
    config={"displayModeBar": False},
)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Active Fleet Size", value=f"{len(st.session_state.fleet['vessels'])} Ships" if st.session_state.fleet else "0")
with col2:
    st.metric(label="Commercial Routes", value=f"{len(st.session_state.fleet['routes'])} Corridors" if st.session_state.fleet else "0")
with col3:
    st.metric(label="Surrogate Accuracy", value="3.26 RMSE", delta="-9.8% QPSO Tuned")
with col4:
    st.metric(label="Algorithm Advantage", value="1.4–2.0×", delta="Faster vs Classical GA")

st.markdown("---")

# Feature Highlights
st.subheader("Platform Workflow")
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("#### 1. Fleet & Fuel Surrogates")
    st.markdown(
        """
        - Ingest real or calibrated synthetic fleets.
        - Vectorized ML predictions calibrated against **21,622 verified EU MRV THETIS vessel-years**.
        - Cubic admiralty resistance curves across container, bulk, and tanker vessels.
        """
    )

with c2:
    st.markdown("#### 2. Hybrid Quantum Optimization")
    st.markdown(
        """
        - Multi-objective Pareto optimization ($Z_1$ Fuel Cost, $Z_2$ WtW GHG, $Z_3$ OPEX).
        - Han & Kim rotation gates for vessel routing and bunkering decisions.
        - Heavy-tailed QPSO continuous speed optimization under strict schedule limits.
        """
    )

with c3:
    st.markdown("#### 3. Dual Decision Reports")
    st.markdown(
        """
        - **Executive Summary PDF**: 2-page jargon-free report with car analogies and top ship levers.
        - **Technical Engineering Report PDF**: 12-page comprehensive report featuring the 13-figure library.
        - Instant WeasyPrint vector compilation and CSV exports.
        """
    )

if not st.session_state.last_pareto:
    st.info("💡 **Getting Started**: Go to **1_Data** to preview the fleet or generate a synthetic scenario, then proceed to **3_Optimize** to run the quantum engine.")
else:
    st.success("✅ **Optimization Results In Memory**: Visit **5_Report** to inspect the Pareto trade-off and export the executive and technical PDF reports.")

st.markdown("---")
st.caption("QGreenFleet v0.3 · SIH #26138 · Egreen Quanta · "
           "Built with ❤️ for Clean & Green Technology")
