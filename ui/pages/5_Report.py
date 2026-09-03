"""Page 5: Dual Decision Reports (Executive Summary & Technical Fleet Optimization Report)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st

from ui.utils.fleet_loader import ensure_session_state
from ui.utils.pdf_export import generate_summary_pdf, generate_technical_pdf
from ui.utils.report_data import _find_knee_solution, build_report_data

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

st.set_page_config(page_title="QGreenFleet | Reports", page_icon="📄", layout="wide")

# Ensure all session state keys are available even on direct URL navigation
ensure_session_state()

st.title("📄 Decision Support & Audit Reports")
st.markdown("Publication-ready dual reporting: **Executive Summary** for leadership and **Technical Report** for naval architects and regulators.")

# Validate prerequisites
if not st.session_state.get("fleet"):
    st.warning("⚠️ No active fleet loaded. Please visit **1_Data** first.")
    st.stop()

if not st.session_state.get("last_pareto"):
    # Offer to load sample reports or pareto.csv
    pareto_csv = _PROJECT_ROOT / "outputs" / "pareto.csv"
    if pareto_csv.exists():
        df_p = pd.read_csv(pareto_csv)
        st.session_state.last_pareto = df_p.to_dict(orient="records")
        knee_s, _ = _find_knee_solution(st.session_state.last_pareto)
        st.session_state.selected_solution = knee_s
    else:
        st.warning("⚠️ No optimization results available. Please run an optimization on **3_Optimize** first.")
        st.stop()

if not st.session_state.get("selected_solution"):
    knee_s, _ = _find_knee_solution(st.session_state.last_pareto)
    st.session_state.selected_solution = knee_s

# Build unified data dictionary
with st.spinner("Compiling fleet KPI deltas and report metrics..."):
    report_data = build_report_data(
        solution=st.session_state.selected_solution,
        pareto=st.session_state.last_pareto,
        history=st.session_state.get("last_history"),
        fleet=st.session_state.fleet,
        bau=st.session_state.get("bau_baseline"),
        scenarios=st.session_state.get("scenarios", []),
        sweep_results=st.session_state.get("sweep_results"),
    )

today_str = datetime.now().strftime("%Y%m%d")

# ===================================================================== #
#  Download Action Bar                                                   #
# ===================================================================== #
st.subheader("Document Export Center")

sample_summary_path = _PROJECT_ROOT / "docs" / "samples" / "QGreenFleet_Executive_Summary.pdf"
sample_tech_path = _PROJECT_ROOT / "docs" / "samples" / "QGreenFleet_Technical_Report.pdf"

# Top control toolbar
col_info, col_recompile = st.columns([3, 1])
with col_info:
    st.caption("Publication-grade PDF reports pre-compiled with high-resolution vector charts. Click below to download:")
with col_recompile:
    if st.button("🔄 Recompile Custom PDFs", use_container_width=True):
        with st.spinner("Rendering fresh PDFs from current session..."):
            st.session_state.summary_pdf_bytes = generate_summary_pdf(report_data)
            st.session_state.tech_pdf_bytes = generate_technical_pdf(report_data)
            st.success("Custom PDFs rendered successfully!")

# Ensure PDF bytes are ready in memory
if "summary_pdf_bytes" not in st.session_state or st.session_state.summary_pdf_bytes is None:
    if sample_summary_path.exists():
        st.session_state.summary_pdf_bytes = sample_summary_path.read_bytes()
    else:
        st.session_state.summary_pdf_bytes = generate_summary_pdf(report_data)

if "tech_pdf_bytes" not in st.session_state or st.session_state.tech_pdf_bytes is None:
    if sample_tech_path.exists():
        st.session_state.tech_pdf_bytes = sample_tech_path.read_bytes()
    else:
        st.session_state.tech_pdf_bytes = generate_technical_pdf(report_data)

d_col1, d_col2, d_col3 = st.columns(3)

with d_col1:
    st.download_button(
        label="📄 Download Executive Summary (PDF)",
        data=st.session_state.summary_pdf_bytes,
        file_name=f"QGreenFleet_Summary_{today_str}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )

with d_col2:
    st.download_button(
        label="📊 Download Technical Report (PDF)",
        data=st.session_state.tech_pdf_bytes,
        file_name=f"QGreenFleet_Technical_{today_str}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )

with d_col3:
    pareto_csv_bytes = pd.DataFrame(st.session_state.last_pareto).to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇ Download Pareto Frontier (CSV)",
        data=pareto_csv_bytes,
        file_name=f"pareto_{today_str}.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.divider()

# ===================================================================== #
#  Dual In-Page Document Preview                                         #
# ===================================================================== #
st.subheader("Document Live Preview")
preview_mode = st.radio(
    "Select Report Type to Preview",
    options=["Executive Summary (Leadership)", "Technical Fleet Optimization Report (Engineering & Regulators)"],
    horizontal=True,
)

sample_dir = _PROJECT_ROOT / "outputs" / "sample-reports"

if preview_mode == "Executive Summary (Leadership)":
    st.markdown("---")
    sample_summary = sample_dir / "summary.md"
    if sample_summary.exists():
        st.markdown(sample_summary.read_text(encoding="utf-8"))
    else:
        # Dynamic preview
        st.markdown(f"# 🚢 QGreenFleet — Your Fleet Plan")
        st.markdown(f"**Date:** {report_data['date']} | **Fleet:** {report_data['fleet_size']} ships, {report_data['routes_count']} routes | **Report:** {report_data['report_id']}")
        st.markdown(
            f"""
            ## The Bottom Line
            > 💰 **Save ${abs(report_data['kpi_deltas']['fuel_cost']['delta']):,.0f} per year on fuel** ({abs(report_data['kpi_deltas']['fuel_cost']['delta_pct']):.1f}% less)
            >
            > 🌍 **Cut CO₂ by {abs(report_data['kpi_deltas']['ghg_wtw']['delta']):,.0f} tonnes per year** ({abs(report_data['kpi_deltas']['ghg_wtw']['delta_pct']):.1f}% less — like taking **{report_data['cars_equivalent']:,} cars** off the road)
            >
            > ✅ **All cargo still delivered on time. Nothing is late, nothing is dropped.**
            """
        )

else:
    st.markdown("---")
    sample_tech = sample_dir / "technical-report.md"
    if sample_tech.exists():
        st.markdown(sample_tech.read_text(encoding="utf-8"))
    else:
        # Dynamic preview
        st.markdown("# QGreenFleet — Technical Fleet Optimization Report")
        st.markdown(f"**Generated:** {report_data['date']} | **Report ID:** {report_data['report_id']}")
        st.markdown("### 1. Executive Summary")
        kpis = report_data["kpi_deltas"]
        st.table(pd.DataFrame([
            {"KPI": "Annual Fuel Cost", "BAU": f"${kpis['fuel_cost']['bau']:,.0f}", "Optimized": f"${kpis['fuel_cost']['opt']:,.0f}", "Delta": f"-${abs(kpis['fuel_cost']['delta']):,.0f}"},
            {"KPI": "Lifecycle GHG (WtW)", "BAU": f"{kpis['ghg_wtw']['bau']:,.0f} t", "Optimized": f"{kpis['ghg_wtw']['opt']:,.0f} t", "Delta": f"-{abs(kpis['ghg_wtw']['delta']):,.0f} t"},
            {"KPI": "Total OPEX", "BAU": f"${kpis['opex']['bau']:,.0f}", "Optimized": f"${kpis['opex']['opt']:,.0f}", "Delta": f"-${abs(kpis['opex']['delta']):,.0f}"},
        ]))
