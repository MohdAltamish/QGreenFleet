"""Comprehensive Plotly chart library for QGreenFleet UI and PDF reporting.

Provides 13 analytical and operational figures:
    1. kpi_bars: BAU vs Optimized comparative bars
    2. pareto_scatter: Multi-objective Pareto frontier with knee identification
    3. ghg_waterfall: Decomposition of emissions abatement levers (simple/technical)
    4. fleet_map: Geographic vessel-route allocation arcs with shore power ports
    5. speed_dumbbell: Per-vessel speed reductions (BAU vs optimized)
    6. fuel_mix_donut: Energy-share fuel distribution
    7. speed_fuel_curve: Calibrated cubic propulsion curves across vessel types
    8. carbon_sweep: Carbon tax threshold sensitivity and alternative fuel crossover
    9. algorithm_diagram: QIEA+QPSO hybrid generation architecture
    10. convergence_chart: Optimization progress dual-axis chart
    11. fuel_mix_bar: Multi-scenario fuel allocation comparison
    12. fig_to_base64_png: High-resolution PNG rasterizer for WeasyPrint PDF embedding
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHARTS_DIR = _PROJECT_ROOT / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

cache_dir = _PROJECT_ROOT / ".cache" / "matplotlib"
cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def _empty(title: str, message: str = "No data") -> go.Figure:
    """Empty-state figure used whenever the real data for a chart is missing."""
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=16))
    fig.update_layout(
        title=f"{title} — {message}",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        template="plotly_white",
    )
    return fig


def sweep_crossover(series: dict[str, Any] | pd.DataFrame | None) -> float | None:
    """Lowest swept price from which green methanol's share stays > 0 and >= HFO's at every higher price.

    A single noisy point where the shares happen to cross is not reported.
    """
    if series is None:
        return None
    try:
        prices = list(series["carbon_price"])
        hfo = list(series["hfo_pct"])
        meoh = list(series["meoh_pct"])
    except (KeyError, TypeError):
        return None
    rows = sorted(zip(prices, hfo, meoh))
    ok = [m is not None and h is not None and m > 0 and m >= h for _, h, m in rows]
    for i in range(len(rows)):
        if all(ok[i:]):
            return float(rows[i][0])
    return None


# ===================================================================== #
#  Image Rasterization Helper                                            #
# ===================================================================== #
def fig_to_base64_png(
    fig: go.Figure | plt.Figure | None,
    save_filename: str | None = None,
    width: int = 800,
    height: int = 450,
) -> str:
    """Convert Plotly or Matplotlib figure to a base64-encoded PNG string.

    Tries Kaleido first; seamlessly falls back to Matplotlib rendering if
    Kaleido headless browser dependencies are unavailable.

    Args:
        fig: Plotly Figure or Matplotlib Figure.
        save_filename: Optional filename to persist under charts/<filename>.png.
        width: Rasterized pixel width.
        height: Rasterized pixel height.

    Returns:
        Base64 ASCII string ready for data-URI embedding in HTML.
    """
    if fig is None:
        return ""

    img_bytes: bytes | None = None

    # 1. Matplotlib Figure
    if isinstance(fig, plt.Figure):
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        img_bytes = buf.read()

    # 2. Plotly Figure
    elif isinstance(fig, go.Figure):
        try:
            img_bytes = fig.to_image(format="png", width=width, height=height, scale=1.5)
        except Exception:
            # Clean Matplotlib fallback for headless environments
            plt_fig, ax = plt.subplots(figsize=(width / 100, height / 100))
            title_text = fig.layout.title.text if fig.layout.title else "Chart"
            ax.set_title(title_text, fontsize=12, fontweight="bold")

            # Extract basic traces
            for tr in fig.data:
                label = tr.name or ""
                if tr.type == "bar":
                    ax.bar(tr.x, tr.y, label=label, alpha=0.85)
                elif tr.type in ("scatter", "scattergeo"):
                    if hasattr(tr, "x") and tr.x is not None:
                        ax.plot(tr.x, tr.y, label=label, marker="o")
                elif tr.type == "pie":
                    ax.pie(tr.values, labels=tr.labels, autopct="%1.1f%%")

            ax.grid(True, linestyle=":", alpha=0.5)
            handles, labels = ax.get_legend_handles_labels()
            if handles and labels:
                ax.legend(handles, labels)
            buf = io.BytesIO()
            plt_fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
            plt.close(plt_fig)
            buf.seek(0)
            img_bytes = buf.read()

    if img_bytes is None:
        return ""

    if save_filename:
        out_p = CHARTS_DIR / save_filename
        out_p.write_bytes(img_bytes)

    return base64.b64encode(img_bytes).decode("utf-8")


# ===================================================================== #
#  1. KPI Bars (BAU vs Optimized)                                        #
# ===================================================================== #
def kpi_bars(data: dict[str, Any]) -> go.Figure:
    """Render side-by-side grouped bar chart comparing BAU vs Optimized KPIs."""
    kpis = data.get("kpi_deltas") or {}
    parts = [kpis.get("fuel_cost") or {}, kpis.get("ghg_wtw") or {}, kpis.get("opex") or {}]
    if any(p.get("bau") is None or p.get("opt") is None for p in parts):
        return _empty("Fleet Performance: BAU vs Recommended Plan")

    categories = ["Fuel Cost ($M)", "WtW GHG (kt-CO₂e)", "Total OPEX ($M)"]
    scale = (1e6, 1e3, 1e6)
    bau_vals = [p["bau"] / k for p, k in zip(parts, scale)]
    opt_vals = [p["opt"] / k for p, k in zip(parts, scale)]

    fig = go.Figure(data=[
        go.Bar(name="BAU Fleet (Today)", x=categories, y=bau_vals, marker_color="#8892b0"),
        go.Bar(name="Optimized (Recommended)", x=categories, y=opt_vals, marker_color="#2ecc71"),
    ])

    fig.update_layout(
        barmode="group",
        title="Fleet Performance: Today (BAU) vs Recommended Plan",
        xaxis_title="Performance Dimension",
        yaxis_title="$M / kt-CO₂e",
        template="plotly_white",
        legend=dict(x=0.7, y=1.1, orientation="h"),
    )
    return fig


# ===================================================================== #
#  2. Pareto Frontier Scatter Plot                                       #
# ===================================================================== #
def pareto_scatter(pareto_df: pd.DataFrame, knee_id: str | None = None) -> go.Figure:
    """Render 3-objective Pareto scatter plot: X=Cost, Y=GHG, Size=OPEX."""
    df = pareto_df.copy() if pareto_df is not None else pd.DataFrame()
    if df.empty or not {"fuel_cost_usd", "ghg_wtw_tco2e", "opex_usd"}.issubset(df.columns):
        return _empty("Fleet Pareto Frontier")
    if "solution_id" not in df.columns:
        df["solution_id"] = [str(row.get("name", f"sol_{i:03d}")) for i, row in df.iterrows()]

    x_cost = df["fuel_cost_usd"] / 1e6
    y_ghg = df["ghg_wtw_tco2e"] / 1000
    size_opex = np.interp(df["opex_usd"], (df["opex_usd"].min(), df["opex_usd"].max()), (12, 28))

    fig = go.Figure()

    # Pareto points
    fig.add_trace(go.Scatter(
        x=x_cost,
        y=y_ghg,
        mode="markers+text",
        text=df["solution_id"],
        textposition="top right",
        marker=dict(size=size_opex, color="#3498db", opacity=0.8, line=dict(width=1, color="black")),
        name="Pareto Frontier",
        hovertemplate="<b>%{text}</b><br>Fuel Cost: $%{x:.2f}M<br>GHG: %{y:.1f} kt<extra></extra>",
    ))

    # Highlight Knee Point
    if knee_id and knee_id in df["solution_id"].values:
        knee_row = df[df["solution_id"] == knee_id].iloc[0]
        fig.add_trace(go.Scatter(
            x=[knee_row["fuel_cost_usd"] / 1e6],
            y=[knee_row["ghg_wtw_tco2e"] / 1000],
            mode="markers+text",
            text=[f"★ {knee_id} (Knee)"],
            textposition="bottom center",
            marker=dict(symbol="star", size=24, color="#f1c40f", line=dict(width=2, color="#d35400")),
            name="Knee Solution",
        ))

    fig.update_layout(
        title="Fleet Pareto Frontier (Cost vs Emissions vs OPEX)",
        xaxis_title="Annual Fuel Cost ($M)",
        yaxis_title="Lifecycle GHG (kt-CO₂e)",
        template="plotly_white",
    )
    return fig


# ===================================================================== #
#  3. GHG Emissions Waterfall                                            #
# ===================================================================== #
def ghg_waterfall(data: dict[str, Any], style: str = "technical") -> go.Figure:
    """Render the exact GHG attribution BAU -> plan (see report_data._decompose_ghg).

    Bars: BAU total, deployment/assignment, slow steaming, fuel switching,
    shore power, plan total. Each lever term is a reduction (positive) or an
    increase (negative) and the terms sum exactly to BAU - plan.
    """
    decomp = data.get("savings_decomposition")
    keys = ("bau_t", "deployment_t", "slow_steaming_t", "fuel_switch_t", "shore_power_t", "plan_t")
    if not decomp or any(decomp.get(k) is None for k in keys):
        return _empty("GHG Change by Lever (t CO₂e)")

    if style == "simple":
        x_labels = ["Fleet Today", "Ship Deployment", "Speed Changes", "Fuel Changes", "Port Electricity", "Recommended Plan"]
    else:
        x_labels = ["BAU Baseline", "Deployment / Assignment", "Slow Steaming", "Fuel Switching", "Shore Power", "Optimized Plan"]

    y_vals = [decomp["bau_t"]] + [-decomp[k] for k in keys[1:5]] + [decomp["plan_t"]]
    measures = ["absolute", "relative", "relative", "relative", "relative", "total"]
    text = [f"{y_vals[0]:,.0f} t"] + [f"{v:+,.0f} t" for v in y_vals[1:5]] + [f"{y_vals[5]:,.0f} t"]

    fig = go.Figure(go.Waterfall(
        name="GHG Abatement",
        orientation="v",
        measure=measures,
        x=x_labels,
        textposition="outside",
        text=text,
        y=y_vals,
        connector={"line": {"color": "rgb(63, 63, 63)"}},
        decreasing={"marker": {"color": "#27ae60"}},
        increasing={"marker": {"color": "#e74c3c"}},
        totals={"marker": {"color": "#2980b9"}},
    ))

    fig.update_layout(
        title="GHG Change by Lever, BAU to Plan (t CO₂e)",
        yaxis_title="Annual GHG Emissions (t-CO₂e)",
        template="plotly_white",
    )
    return fig


# ===================================================================== #
#  4. Fleet Map Geographic Allocation Arcs                               #
# ===================================================================== #
def fleet_map(solution: Solution | dict[str, Any], fleet: dict[str, Any]) -> go.Figure:
    """Render geographic vessel-route allocation arcs colored by assigned fuel."""
    routes = [r for r in fleet.get("routes", []) if r.get("from") and r.get("to")]
    if not routes:
        return _empty("Fleet Deployment Corridors", "No port data for these routes")

    # Port coordinates catalog (geography only)
    port_coords = {
        "Singapore": (1.290270, 103.851959),
        "Shanghai": (31.230416, 121.473701),
        "Rotterdam": (51.924420, 4.477733),
        "Busan": (35.179554, 129.075642),
        "Tokyo": (35.676192, 139.650311),
        "Hamburg": (53.551085, 9.993682),
        "Los_Angeles": (33.743184, -118.267254),
    }

    fig = go.Figure()

    # Draw commercial route corridors
    for r in routes:
        p_from, p_to = r["from"], r["to"]
        if p_from not in port_coords or p_to not in port_coords:
            continue
        c1, c2 = port_coords[p_from], port_coords[p_to]

        fig.add_trace(go.Scattergeo(
            lon=[c1[1], c2[1]],
            lat=[c1[0], c2[0]],
            mode="lines",
            line=dict(width=2.5, color="#f39c12" if r.get("shore_power") else "#27ae60"),
            hoverinfo="text",
            text=f"Route {r.get('id')}: {p_from} → {p_to} ({r.get('distance_nm')} nm)"
            + (" — shore power available" if r.get("shore_power") else ""),
            showlegend=False,
        ))

    # Mark the ports these routes use
    used = {p for r in routes for p in (r["from"], r["to"]) if p in port_coords}
    for port in sorted(used):
        lat, lon = port_coords[port]
        fig.add_trace(go.Scattergeo(
            lon=[lon],
            lat=[lat],
            mode="markers+text",
            text=[port],
            textposition="top center",
            marker=dict(size=10, color="#34495e"),
            name="Ports",
            showlegend=False,
        ))

    fig.update_layout(
        title="Fleet Deployment Corridors (orange = route with shore power)",
        geo=dict(
            projection_type="natural earth",
            showcoastlines=True,
            coastlinecolor="DarkGray",
            showland=True,
            landcolor="#f5f6fa",
            showocean=True,
            oceancolor="#e4f1fe",
        ),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


# ===================================================================== #
#  5. Speed Dumbbell Chart                                               #
# ===================================================================== #
def speed_dumbbell(data: dict[str, Any]) -> go.Figure:
    """Render per-vessel speed changes between BAU and Optimized plan."""
    records = [
        {"vessel": p.get("vessel_id"), "opt": float(p["speed_kn"]), "bau": float(p["bau_speed_kn"]),
         "reduction": abs(float(p["speed_kn"]) - float(p["bau_speed_kn"]))}
        for p in data.get("per_vessel_plan", [])
        if p.get("speed_kn") is not None and p.get("bau_speed_kn") is not None
    ]
    if not records:
        return _empty("Speed per Vessel (BAU vs Optimized)")

    df_sp = pd.DataFrame(records).sort_values("reduction", ascending=True)

    fig = go.Figure()

    # Connecting dumbbell lines
    for _, row in df_sp.iterrows():
        fig.add_trace(go.Scatter(
            x=[row["bau"], row["opt"]],
            y=[row["vessel"], row["vessel"]],
            mode="lines",
            line=dict(color="#bdc3c7", width=3),
            showlegend=False,
        ))

    # BAU speed points
    fig.add_trace(go.Scatter(
        x=df_sp["bau"],
        y=df_sp["vessel"],
        mode="markers",
        name="BAU Speed",
        marker=dict(color="#7f8c8d", size=10),
    ))

    # Optimized speed points
    fig.add_trace(go.Scatter(
        x=df_sp["opt"],
        y=df_sp["vessel"],
        mode="markers",
        name="Optimized Cruising Speed",
        marker=dict(color="#2ecc71", size=10),
    ))

    fig.update_layout(
        title="Speed Optimization per Vessel (Knots: BAU vs Optimized)",
        xaxis_title="Cruising Speed (knots)",
        yaxis_title="Vessel Identifier",
        template="plotly_white",
        legend=dict(x=0.7, y=1.05, orientation="h"),
    )
    return fig


# ===================================================================== #
#  6. Fuel Mix Donut                                                     #
# ===================================================================== #
def fuel_mix_donut(data: dict[str, Any]) -> go.Figure:
    """Render energy-share distribution donut chart."""
    fuel_mix = data.get("fuel_mix_pct") or {}
    if not fuel_mix:
        return _empty("Fuel Mix of Deployed Ships")

    labels = list(fuel_mix.keys())
    values = list(fuel_mix.values())
    colors = ["#7f8c8d", "#3498db", "#2ecc71", "#9b59b6", "#e67e22"]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        marker=dict(colors=colors[:len(labels)]),
        textinfo="label+percent",
        hoverinfo="label+value+percent",
    )])

    fig.update_layout(
        title="Deployed Ships by Fuel Type (%)",
        template="plotly_white",
    )
    return fig


# ===================================================================== #
#  7. Speed-Fuel Admiralty Curve                                         #
# ===================================================================== #
def speed_fuel_curve(
    predictor: Any,
    draft_m: float = 10.0,
    weather_severity: int = 1,
) -> go.Figure:
    """Plot predictor fuel consumption vs speed per ship type.

    ``predictor`` is either an object with ``predict_tpd`` or a precomputed
    ``{ship_type: {"speed": [...], "tpd": [...]}}`` dict. Anything else gives
    an empty-state figure.
    """
    speeds = np.linspace(5.0, 25.0, 40)
    ship_types = ["container", "bulk", "tanker"]
    colors = {"container": "#2ecc71", "bulk": "#3498db", "tanker": "#e67e22"}

    if isinstance(predictor, dict) and predictor:
        curves = {st: (c["speed"], c["tpd"]) for st, c in predictor.items()}
    elif hasattr(predictor, "predict_tpd"):
        curves = {st: (speeds, [predictor.predict_tpd(s, draft_m, weather_severity, st) for s in speeds]) for st in ship_types}
    else:
        return _empty("Fuel Consumption vs Speed", "No predictor available")

    fig = go.Figure()

    for st, (x_sp, fuels) in curves.items():

        fig.add_trace(go.Scatter(
            x=list(x_sp),
            y=list(fuels),
            mode="lines",
            name=st.capitalize(),
            line=dict(color=colors.get(st, "#333333"), width=2.5),
        ))

    fig.update_layout(
        title="Predicted Fuel Consumption vs Speed (t/day)",
        xaxis_title="Vessel Speed (knots)",
        yaxis_title="Fuel Consumption (tons/day)",
        template="plotly_white",
    )
    return fig


# ===================================================================== #
#  8. Carbon Price Sweep Sensitivity                                     #
# ===================================================================== #
def carbon_sweep(sweep_results: pd.DataFrame | dict[str, Any] | None) -> go.Figure:
    """Render fuel adoption vs carbon price from real sweep data (empty state otherwise).

    The crossover line is drawn only when sweep_crossover() finds one in the data.
    """
    cols = ("carbon_price", "hfo_pct", "lng_pct", "meoh_pct")
    try:
        prices, hfo, lng, meoh = (list(sweep_results[c]) for c in cols)  # type: ignore[index]
    except (KeyError, TypeError):
        return _empty("Fuel Mix vs Carbon Price", "No sweep data")
    if not prices:
        return _empty("Fuel Mix vs Carbon Price", "No sweep data")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prices, y=hfo, mode="lines+markers", name="HFO", line=dict(color="#7f8c8d", width=2)))
    fig.add_trace(go.Scatter(x=prices, y=lng, mode="lines+markers", name="LNG", line=dict(color="#3498db", width=2)))
    fig.add_trace(go.Scatter(x=prices, y=meoh, mode="lines+markers", name="Green Methanol", line=dict(color="#2ecc71", width=3)))

    crossover = sweep_crossover({"carbon_price": prices, "hfo_pct": hfo, "meoh_pct": meoh})
    if crossover is not None:
        fig.add_vline(x=crossover, line_width=2, line_dash="dash", line_color="#e74c3c")
        fig.add_annotation(
            x=crossover,
            y=max(meoh),
            text=f"Methanol share ≥ HFO share from ${crossover:,.0f}/t",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#e74c3c",
            bgcolor="white",
        )

    fig.update_layout(
        title=f"Fuel Mix vs Carbon Price (${min(prices):,.0f}–${max(prices):,.0f}/t CO₂e)",
        xaxis_title="Carbon Price ($/t-CO₂e)",
        yaxis_title="Share of Deployed Ships (%)",
        template="plotly_white",
    )
    return fig


# ===================================================================== #
#  9. Optimization Convergence Dual-Axis Chart                          #
# ===================================================================== #
def convergence_chart(history: dict[str, list[Any]]) -> go.Figure:
    """Render dual-axis chart showing Hypervolume and Feasible Solution Count."""
    gens = history.get("generation", list(range(len(history.get("hypervolume", [])))))
    hv = history.get("hypervolume", [])
    feas = history.get("feasible_count", [])

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=gens, y=hv, name="Hypervolume", mode="lines", line=dict(color="#27ae60", width=2.5)))
    fig.add_trace(go.Scatter(
        x=gens,
        y=feas,
        name="Feasible Count",
        mode="lines",
        line=dict(color="#2980b9", width=2, dash="dash"),
        yaxis="y2",
    ))

    fig.update_layout(
        title="QIEA+QPSO Generational Convergence Profile",
        xaxis=dict(title="Generation Index"),
        yaxis=dict(
            title=dict(text="Hypervolume Indicator", font=dict(color="#27ae60")),
            tickfont=dict(color="#27ae60"),
        ),
        yaxis2=dict(
            title=dict(text="Feasible Population Count", font=dict(color="#2980b9")),
            tickfont=dict(color="#2980b9"),
            overlaying="y",
            side="right",
        ),
        template="plotly_white",
        legend=dict(x=0.7, y=1.1, orientation="h"),
    )
    return fig


# ===================================================================== #
#  10. Multi-Scenario Fuel Mix Comparison                                #
# ===================================================================== #
def fuel_mix_bar(scenarios: list[dict[str, Any]]) -> go.Figure:
    """Render horizontal stacked bar chart comparing fuel allocations across scenarios."""
    scen_names = [s.get("name", f"Scenario {i+1}") for i, s in enumerate(scenarios)]
    if not scenarios:
        return _empty("Fuel Mix Across Scenarios")
    # A fuel absent from a scenario's mix has a 0% share; a missing mix is left blank.
    def share(s: dict[str, Any], fuel: str) -> float | None:
        mix = s.get("fuel_mix")
        return None if mix is None else float(mix.get(fuel, 0.0))

    hfo_shares = [share(s, "HFO") for s in scenarios]
    lng_shares = [share(s, "LNG_DIESEL") for s in scenarios]
    meoh_shares = [share(s, "MEOH_GREEN") for s in scenarios]

    fig = go.Figure()
    fig.add_trace(go.Bar(y=scen_names, x=hfo_shares, name="HFO", orientation="h", marker_color="#7f8c8d"))
    fig.add_trace(go.Bar(y=scen_names, x=lng_shares, name="LNG", orientation="h", marker_color="#3498db"))
    fig.add_trace(go.Bar(y=scen_names, x=meoh_shares, name="Green Methanol", orientation="h", marker_color="#2ecc71"))

    fig.update_layout(
        barmode="stack",
        title="Alternative Fuel Adoption Comparison Across Scenarios",
        xaxis_title="Energy Share (%)",
        template="plotly_white",
    )
    return fig


# ===================================================================== #
#  11. Interactive System Flow Diagram (Dark Glassmorphism)             #
# ===================================================================== #
def system_flow_diagram() -> go.Figure:
    """Visually rich end-to-end system flow for the Streamlit home page.

    Pipeline: Data Ingestion -> Two-Stage Surrogate -> Quantum Optimizer
    -> Decision Support.
    """
    # ---- palette (dark glassmorphism) ----
    BG      = "#0E1525"
    STAGES = [  # (x_center, title, lines, accent color)
        (0.11, "📊 DATA INGESTION",
         ["21,622 real, verified", "EU MRV ship records", "Voyage & weather data",
          "IMO emission factors"], "#38BDF8"),
        (0.37, "🧠 TWO-STAGE SURROGATE",
         ["MRV fuel model (real data)", "Draft & weather adjustment",
          "Per-type calibration", "Cubic speed–fuel physics"], "#34D399"),
        (0.63, "⚛️ QUANTUM OPTIMIZER",
         ["QIEA · Q-bit rotation gates", "QPSO · tunneling speed search",
          "NSGA-II Pareto ranking", "Constraint repair engine"], "#A78BFA"),
        (0.89, "🎯 DECISION SUPPORT",
         ["Trade-off menu of plans", "Scenario & carbon sweeps",
          "Dual PDF reports", "Signed deltas vs BAU"], "#FBBF24"),
    ]
    BOX_W, BOX_H, Y_MID = 0.205, 0.56, 0.47

    fig = go.Figure()

    # ---- connector arrows with glow ----
    for i in range(len(STAGES) - 1):
        x0 = STAGES[i][0] + BOX_W / 2
        x1 = STAGES[i + 1][0] - BOX_W / 2
        for width, alpha in [(14, 0.15), (8, 0.3), (3, 0.9)]:  # glow layers
            fig.add_trace(go.Scatter(
                x=[x0 + 0.004, x1 - 0.012], y=[Y_MID, Y_MID], mode="lines",
                line=dict(color=f"rgba(148,163,255,{alpha})", width=width),
                hoverinfo="skip", showlegend=False))
        fig.add_annotation(  # arrowhead
            x=x1 - 0.002, y=Y_MID, ax=x1 - 0.03, ay=Y_MID,
            xref="x", yref="y", axref="x", ayref="y",
            arrowhead=2, arrowsize=1.6, arrowwidth=3,
            arrowcolor="rgba(148,163,255,0.95)", showarrow=True, text="")

    # ---- stage cards ----
    for x, title, lines, accent in STAGES:
        # soft glow
        fig.add_shape(type="rect",
            x0=x - BOX_W/2 - 0.008, x1=x + BOX_W/2 + 0.008,
            y0=Y_MID - BOX_H/2 - 0.015, y1=Y_MID + BOX_H/2 + 0.015,
            fillcolor=accent, opacity=0.10, line_width=0, layer="below")
        # card
        fig.add_shape(type="rect",
            x0=x - BOX_W/2, x1=x + BOX_W/2,
            y0=Y_MID - BOX_H/2, y1=Y_MID + BOX_H/2,
            fillcolor="#1A2332", line=dict(color=accent, width=2), layer="below")
        # accent top bar
        fig.add_shape(type="rect",
            x0=x - BOX_W/2, x1=x + BOX_W/2,
            y0=Y_MID + BOX_H/2 - 0.035, y1=Y_MID + BOX_H/2,
            fillcolor=accent, line_width=0, layer="below")
        # title
        fig.add_annotation(x=x, y=Y_MID + BOX_H/2 - 0.105, text=f"<b>{title}</b>",
            showarrow=False, font=dict(size=15, color="#F1F5F9"))
        # body lines
        body = "<br>".join(f"<span style='color:{accent}'>▸</span> {l}"
                           for l in lines)
        fig.add_annotation(x=x, y=Y_MID - 0.075, text=body, showarrow=False,
            font=dict(size=11.5, color="#CBD5E1"), align="left")

    # ---- header & footer ----
    fig.add_annotation(x=0.5, y=0.97,
        text="<b>QGreenFleet — Quantum-Inspired Fleet Decarbonization Platform</b>",
        showarrow=False, font=dict(size=20, color="#F8FAFC"))
    fig.add_annotation(x=0.5, y=0.895,
        text="QIEA + QPSO coupled optimization · calibrated against real EU MRV data · classical hardware",
        showarrow=False, font=dict(size=12.5, color="#7C8DB0"))
    fig.add_annotation(x=0.5, y=0.06,
        text="Every figure in the reports is computed from the run's own results and committed benchmark data",
        showarrow=False, font=dict(size=12, color="#94A3B8"))

    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG,
        xaxis=dict(visible=False, range=[0, 1], fixedrange=True),
        yaxis=dict(visible=False, range=[0, 1], fixedrange=True),
        height=430, margin=dict(l=10, r=10, t=10, b=10),
        hovermode=False, showlegend=False)
    return fig
