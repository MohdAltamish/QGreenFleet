"""Page 3: Hybrid Quantum Optimization Engine (QIEA+QPSO)."""

from __future__ import annotations

import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
import streamlit as st

from src.emissions.factors import OPTIMIZER_FUELS
from src.optimization.qiea import run as run_qiea
from src.optimization.runner import save_pareto_artifacts
from ui.utils.chart_helpers import convergence_chart, pareto_scatter
from ui.utils.fleet_loader import compute_bau_baseline, ensure_session_state
from ui.utils.report_data import _find_knee_solution

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

st.set_page_config(page_title="QGreenFleet | Optimization", page_icon="⚛️", layout="wide")

ensure_session_state()

st.title("⚛️ Fleet Deployment & Speed Optimization")
st.markdown("Coupled Quantum-Inspired Evolutionary Algorithm (QIEA) with Quantum-behaved Particle Swarm Optimization (QPSO).")

# Top banner for Hugging Face / Demo execution
st.info("⚡ Demo mode: pre-computed results load instantly. Live optimization available but takes ~20 min on hosted CPU.")

if not st.session_state.fleet:
    st.warning("⚠️ No active fleet loaded. Please visit **1_Data** to upload or synthesize a fleet first.")
    st.stop()

vessels = st.session_state.fleet["vessels"]
routes = st.session_state.fleet["routes"]

# ===================================================================== #
#  DEFAULT: Offline Demo Loader — Load Pre-Computed Case Study Scenarios#
# ===================================================================== #
case_study_dir = _PROJECT_ROOT / "outputs" / "case_study"
default_scenarios = ["baseline", "carbon_100", "cii_tightened", "meoh_subsidized"]

avail_scenarios = []
if case_study_dir.exists():
    for name in default_scenarios:
        if (case_study_dir / name / "pareto.csv").exists():
            avail_scenarios.append(name)
    # Add any other scenarios present
    for d in sorted(case_study_dir.iterdir()):
        if d.is_dir() and d.name not in avail_scenarios and (d / "pareto.csv").exists():
            avail_scenarios.append(d.name)

if not avail_scenarios and (_PROJECT_ROOT / "outputs" / "pareto.csv").exists():
    avail_scenarios.append("default (outputs/pareto.csv)")

def _load_scenario(chosen: str):
    if chosen == "default (outputs/pareto.csv)":
        df_prev = pd.read_csv(_PROJECT_ROOT / "outputs" / "pareto.csv")
        st.session_state.last_pareto = df_prev.to_dict(orient="records")
        knee_s, _ = _find_knee_solution(st.session_state.last_pareto)
        st.session_state.selected_solution = knee_s
    else:
        s_dir = case_study_dir / chosen
        df_p = pd.read_csv(s_dir / "pareto.csv")
        st.session_state.last_pareto = df_p.to_dict(orient="records")

        if (s_dir / "solution_knee.json").exists():
            st.session_state.selected_solution = json.loads((s_dir / "solution_knee.json").read_text(encoding="utf-8"))
        else:
            knee_s, _ = _find_knee_solution(st.session_state.last_pareto)
            st.session_state.selected_solution = knee_s

        if (s_dir / "bau_baseline.json").exists():
            st.session_state.bau_baseline = json.loads((s_dir / "bau_baseline.json").read_text(encoding="utf-8"))

        if (s_dir / "history.json").exists():
            st.session_state.last_history = json.loads((s_dir / "history.json").read_text(encoding="utf-8"))

    st.session_state.last_run_time = "Pre-computed"

# Auto-load baseline if nothing loaded yet
if st.session_state.last_pareto is None and avail_scenarios:
    _load_scenario(avail_scenarios[0])

if avail_scenarios:
    st.subheader("📂 Load Previous Results (Instant)")
    c_scen_sel, c_scen_btn = st.columns([3, 1])
    with c_scen_sel:
        chosen_scen = st.selectbox(
            "Select Scenario:",
            options=avail_scenarios,
            index=0,
            help="Choose from pre-computed policy scenarios"
        )
    with c_scen_btn:
        st.write("")
        load_scen_btn = st.button("Load Scenario", use_container_width=True, type="primary")

    if load_scen_btn and chosen_scen:
        _load_scenario(chosen_scen)
        st.success(f"Loaded '{chosen_scen}'! Pareto front, baseline, and knee solution are ready.")
        st.rerun()

# ===================================================================== #
#  Live Optimization Configuration (Optional live run)                  #
# ===================================================================== #
with st.expander("🛠️ Live Optimization Parameters & Hyperparameters", expanded=False):
    col_p1, col_p2 = st.columns(2)

    with col_p1:
        st.markdown("#### Fuel Price Benchmarks ($/metric ton)")
        hfo_price = st.slider("HFO Price", min_value=400, max_value=1500, value=650, step=25)
        lng_price = st.slider("LNG (Diesel-cycle) Price", min_value=500, max_value=1800, value=800, step=25)
        meoh_price = st.slider("Green Methanol Price", min_value=800, max_value=2000, value=1200, step=25)
        h2_price = st.slider("Green Hydrogen Price", min_value=2000, max_value=4000, value=3000, step=50)
        nh3_price = st.slider("Green Ammonia Price", min_value=1500, max_value=3500, value=2500, step=50)

    with col_p2:
        st.markdown("#### Environmental Policy & Search Budget")
        carbon_tax = st.slider("Carbon Tax / Price ($/t-CO₂e)", min_value=0, max_value=200, value=0, step=10)
        pop_size = st.select_slider("Population Size (Q-bits)", options=[20, 50, 100, 200], value=50)
        generations = st.select_slider("Generational Search Steps", options=[20, 50, 100, 200, 300], value=50)

    fuel_prices = {
        "HFO": float(hfo_price),
        "LNG_DIESEL": float(lng_price),
        "MEOH_GREEN": float(meoh_price),
        "H2_GREEN": float(h2_price),
        "NH3_GREEN": float(nh3_price),
    }

# Pre-Execution BAU Baseline Evaluation for live runs
if st.session_state.bau_baseline is None or st.button("Recalculate BAU Baseline"):
    with st.spinner("Evaluating Business-As-Usual fleet baseline..."):
        st.session_state.bau_baseline = compute_bau_baseline(
            vessels=vessels,
            routes=routes,
            predictor=st.session_state.predictor,
            fuel_prices=fuel_prices,
            carbon_price=carbon_tax,
        )


# ===================================================================== #
#  Run Optimization Button & Progress Tracking                           #
# ===================================================================== #
st.divider()
c_btn, c_stat = st.columns([1, 3])

with c_btn:
    run_btn = st.button("🚀 Run Quantum Optimization", type="primary", use_container_width=True)

progress_bar = st.empty()
status_text = st.empty()

if run_btn:
    opt_cfg = {
        "pop_size": pop_size,
        "generations": generations,
        "theta_start": 0.05 * np.pi,
        "theta_end": 0.005 * np.pi,
        "mutation_prob": 0.02,
        "lambda0": 10.0,
        "fuel_prices": fuel_prices,
        "carbon_price": float(carbon_tax),
        "archive_max": 100,
        "seed": 42,
    }

    t0 = time.time()

    def update_ui_progress(gen: int, total_gens: int, n_archive: int, hv: float, n_feas: int) -> None:
        pct = gen / total_gens
        progress_bar.progress(pct)
        status_text.text(f"Gen {gen:03d}/{total_gens:03d} | Archive: {n_archive:02d} | HV: {hv:.4f} | Feasible: {n_feas:03d}/{pop_size}")

    with st.spinner("Executing QIEA (discrete) + QPSO (speeds) search..."):
        archive, history = run_qiea(
            vessels=vessels,
            routes=routes,
            config=opt_cfg,
            predictor=st.session_state.predictor,
            progress_callback=update_ui_progress,
        )

    elapsed = time.time() - t0
    st.session_state.last_pareto = archive
    st.session_state.last_history = history
    st.session_state.last_run_time = f"{elapsed:.1f}s"

    # Identify and store knee solution as default selected
    knee_sol, knee_idx = _find_knee_solution(archive)
    st.session_state.selected_solution = knee_sol

    # Persist artifacts to outputs
    save_pareto_artifacts(archive, vessels, routes, _PROJECT_ROOT / "outputs")
    st.success(f"Optimization completed in {elapsed:.2f}s! Found {len(archive)} non-dominated Pareto solutions.")

# ===================================================================== #
#  Results Visualization: Pareto Front & Convergence                    #
# ===================================================================== #
if st.session_state.last_pareto:
    st.subheader("Optimization Results & Pareto Frontier")

    # Format Pareto solutions into DataFrame
    pareto_records = []
    for idx, s in enumerate(st.session_state.last_pareto):
        s_id = f"sol_{idx:03d}" if isinstance(s, dict) is False else s.get("solution_id", f"sol_{idx:03d}")
        if hasattr(s, "objectives") and s.objectives is not None:
            z1, z2, z3 = s.objectives
        elif isinstance(s, dict):
            z1 = s.get("fuel_cost_usd", s.get("objectives", {}).get("fuel_cost_usd", 1e7))
            z2 = s.get("ghg_wtw_tco2e", s.get("objectives", {}).get("ghg_wtw_tco2e", 5e4))
            z3 = s.get("opex_usd", s.get("objectives", {}).get("opex_usd", 2e7))
        else:
            z1, z2, z3 = 1e7, 5e4, 2e7

        pareto_records.append({
            "solution_id": s_id,
            "fuel_cost_usd": float(z1),
            "ghg_wtw_tco2e": float(z2),
            "opex_usd": float(z3),
        })

    df_pareto = pd.DataFrame(pareto_records)
    knee_sol, knee_idx = _find_knee_solution(st.session_state.last_pareto)
    knee_id = df_pareto.iloc[knee_idx]["solution_id"]

    c_plot1, c_plot2 = st.columns(2)
    with c_plot1:
        fig_scatter = pareto_scatter(df_pareto, knee_id=knee_id)
        st.plotly_chart(fig_scatter, use_container_width=True)

    with c_plot2:
        if st.session_state.last_history:
            fig_conv = convergence_chart(st.session_state.last_history)
            st.plotly_chart(fig_conv, use_container_width=True)
        else:
            st.info("Convergence history displayed during active optimization runs.")

    # Solution Selection
    st.markdown("#### Solution Inspection")
    selected_id = st.selectbox("Select Solution to Deploy & Inspect", options=df_pareto["solution_id"].tolist(), index=knee_idx)
    sel_idx = df_pareto[df_pareto["solution_id"] == selected_id].index[0]
    st.session_state.selected_solution = st.session_state.last_pareto[sel_idx]

    # Allocation Table with "Δ vs BAU"
    st.markdown("#### Vessel Allocation & Operational Delta vs BAU")
    sel_sol = st.session_state.selected_solution
    bau_sol = st.session_state.bau_baseline

    bau_speeds = getattr(bau_sol, "speeds", np.full((len(vessels), len(routes)), 15.0))
    opt_speeds = getattr(sel_sol, "speeds", np.full((len(vessels), len(routes)), 15.0))
    opt_assign = getattr(sel_sol, "observed", {}).get("assignment", np.zeros((len(vessels), len(routes)), dtype=bool))
    opt_fuels = getattr(sel_sol, "observed", {}).get("fuel", np.zeros(len(vessels), dtype=int))

    vessel_rows = []
    for v_i, v in enumerate(vessels):
        assigned_r = np.where(opt_assign[v_i])[0] if opt_assign.ndim == 2 else []
        r_lbl = f"R{assigned_r[0]}" if len(assigned_r) > 0 else "Unassigned"

        f_code = opt_fuels[v_i] if v_i < len(opt_fuels) else 0
        f_name = OPTIMIZER_FUELS[f_code] if f_code < len(OPTIMIZER_FUELS) else "HFO"

        opt_spd = float(opt_speeds[v_i, assigned_r[0]]) if len(assigned_r) > 0 else float(v.get("design_speed", 15.0))
        bau_spd = float(bau_speeds[v_i, assigned_r[0]]) if len(assigned_r) > 0 else float(v.get("design_speed", 15.0))
        delta_s = opt_spd - bau_spd

        changes = []
        if f_name != "HFO":
            changes.append(f"switched to {f_name}")
        if abs(delta_s) >= 0.4:
            action = "slowed" if delta_s < 0 else "increased"
            changes.append(f"{action} {abs(delta_s):.1f} kn")

        vessel_rows.append({
            "Vessel ID": v.get("id"),
            "Type": v.get("type"),
            "Route": r_lbl,
            "Optimized Speed": f"{opt_spd:.1f} kn",
            "BAU Speed": f"{bau_spd:.1f} kn",
            "Assigned Fuel": f_name,
            "Δ vs BAU": ", ".join(changes) if changes else "no change",
        })

    st.dataframe(pd.DataFrame(vessel_rows), use_container_width=True, hide_index=True)
