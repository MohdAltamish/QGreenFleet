"""Dual PDF report generators (Executive Summary & Technical Fleet Optimization Report).

Renders responsive, publication-ready HTML/CSS compiled into PDF documents via WeasyPrint,
embedding charts as high-resolution base64 PNGs.

Guarantees:
    - Shared unified data dictionary from ui/utils/report_data.py
    - Strict Jargon Guard on Executive Summary (zero algorithmic/mathematical jargon)
    - 8-section Technical Report; each figure and sentence appears only when
      the data behind it is present (missing values render as "—")
"""

from __future__ import annotations

import base64
import ctypes.util
import os
from pathlib import Path
import re
from typing import Any

import pandas as pd

# Ensure macOS Homebrew dynamic library resolution for WeasyPrint/Pango
_orig_find_library = ctypes.util.find_library


def _homebrew_find_library(name: str) -> str | None:
    res = _orig_find_library(name)
    if res:
        return res
    for folder in ["/opt/homebrew/lib", "/usr/local/lib"]:
        p1 = f"{folder}/{name}.dylib"
        if os.path.exists(p1):
            return p1
        p2 = f"{folder}/lib{name}.dylib"
        if os.path.exists(p2):
            return p2
        if os.path.exists(folder):
            for fname in os.listdir(folder):
                if fname.startswith("lib" + name.split("-")[0]) and fname.endswith(".dylib"):
                    return f"{folder}/{fname}"
    return None


ctypes.util.find_library = _homebrew_find_library

try:
    import weasyprint
    _WEASYPRINT_AVAILABLE = True
except Exception:
    _WEASYPRINT_AVAILABLE = False

from ui.utils.chart_helpers import (
    carbon_sweep,
    fleet_map,
    fuel_mix_donut,
    ghg_waterfall,
    kpi_bars,
    pareto_scatter,
    speed_dumbbell,
    speed_fuel_curve,
    fig_to_base64_png,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _file_to_base64(path: Path | str) -> str:
    """Read an existing image file from disk and encode to base64 string."""
    p = Path(path)
    if p.exists() and p.is_file():
        return base64.b64encode(p.read_bytes()).decode("utf-8")
    return ""


_SUMMARY_CSS = """
            @page {
                size: A4;
                margin: 20mm 15mm 20mm 15mm;
                @bottom-right {
                    content: counter(page) " / " counter(pages);
                    font-size: 9pt;
                    color: #7f8c8d;
                }
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                font-size: 11pt;
                line-height: 1.5;
                color: #2c3e50;
            }
            h1 {
                font-size: 20pt;
                color: #1e3799;
                margin-bottom: 2px;
            }
            .subtitle {
                font-size: 10pt;
                color: #7f8c8d;
                margin-bottom: 18px;
                border-bottom: 2px solid #ecf0f1;
                padding-bottom: 8px;
            }
            .bottom-line {
                background: linear-gradient(135deg, #e8f8f5 0%, #d4efdf 100%);
                border-left: 5px solid #27ae60;
                padding: 14px 18px;
                border-radius: 4px;
                margin-bottom: 20px;
            }
            .bottom-line p {
                margin: 6px 0;
                font-size: 11.5pt;
            }
            .chart-box {
                text-align: center;
                margin: 16px 0;
            }
            .chart-box img {
                max-width: 85%;
                height: auto;
                border-radius: 4px;
            }
            .caption {
                font-size: 9pt;
                color: #7f8c8d;
                font-style: italic;
                margin-top: 4px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 12px 0 18px 0;
                font-size: 10.5pt;
            }
            th, td {
                border: 1px solid #dcdde1;
                padding: 8px 10px;
                text-align: left;
            }
            th {
                background-color: #f5f6fa;
                font-weight: 600;
            }
            .badge-check {
                color: #27ae60;
                font-weight: bold;
            }
            .page-break {
                page-break-after: always;
            }
"""

_TECH_CSS = """
            @page {
                size: A4;
                margin: 20mm 15mm 20mm 15mm;
                @bottom-right {
                    content: "Page " counter(page) " of " counter(pages);
                    font-size: 8.5pt;
                    color: #7f8c8d;
                }
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                font-size: 10pt;
                line-height: 1.45;
                color: #2c3e50;
            }
            h1 { font-size: 18pt; color: #1e3799; margin-bottom: 2px; }
            h2 { font-size: 13.5pt; color: #1e3799; border-bottom: 1.5px solid #bdc3c7; padding-bottom: 3px; margin-top: 20px; }
            h3 { font-size: 11pt; color: #2c3e50; margin-top: 12px; }
            .metadata {
                font-size: 9pt;
                color: #7f8c8d;
                border-bottom: 1px solid #dcdde1;
                padding-bottom: 6px;
                margin-bottom: 16px;
            }
            .chart-box {
                text-align: center;
                margin: 14px 0;
            }
            .chart-box img {
                max-width: 82%;
                height: auto;
                border: 1px solid #ecf0f1;
                border-radius: 4px;
            }
            .caption {
                font-size: 8.5pt;
                color: #7f8c8d;
                font-style: italic;
                margin-top: 3px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 10px 0 14px 0;
                font-size: 8.8pt;
            }
            th, td {
                border: 1px solid #dcdde1;
                padding: 5px 7px;
                text-align: left;
            }
            th {
                background-color: #f8f9fa;
                font-weight: 600;
            }
            .page-break {
                page-break-after: always;
            }
"""


# ===================================================================== #
#  Formatting helpers: every number shown comes from `data`; missing → — #
# ===================================================================== #
_DASH = "—"


def _num(v: float | None, fmt: str = ",.0f", prefix: str = "", suffix: str = "") -> str:
    return _DASH if v is None else f"{prefix}{v:{fmt}}{suffix}"


def _signed(v: float | None, fmt: str = ",.0f", prefix: str = "", suffix: str = "") -> str:
    """'+$1,234' / '−$1,234' / '$0' — the sign is always the true sign of v."""
    if v is None:
        return _DASH
    sign = "+" if v > 0 else ("−" if v < 0 else "")
    return f"{sign}{prefix}{abs(v):{fmt}}{suffix}"


def _change_word(v: float | None) -> str:
    if v is None:
        return ""
    return "increase" if v > 0 else ("reduction" if v < 0 else "no change")


def _delta_cell(k: dict[str, Any], prefix: str = "", suffix: str = "") -> str:
    d, p = k.get("delta"), k.get("delta_pct")
    if d is None:
        return _DASH
    pct = f", {_signed(p, '.1f', suffix='%')}" if p is not None else ""
    return f"{_signed(d, prefix=prefix, suffix=suffix)} ({_change_word(d)}{pct})"


_VIOLATION_TEXT = {
    "demand_deficit": ("route demand short by {:,.0f} TEU/t", "cargo capacity short by {:,.0f} units"),
    "schedule_delay": ("{:,.1f} h total schedule delay", "{:,.1f} hours of late arrivals"),
    "fuel_unavailable": ("{:,.0f} vessel(s) on a fuel not available to them", "{:,.0f} ship(s) on a fuel they cannot bunker"),
    "cii_excess": ("CII limit exceeded (total excess {:,.3f} gCO₂/dwt·nm)", "carbon-intensity limit exceeded"),
    "vessel_overbooked": ("{:,.0f} vessel(s) booked on more than one route", "{:,.0f} ship(s) double-booked"),
}


def _constraint_sentence(status: dict[str, Any] | None, plain: bool) -> str | None:
    """Demand/schedule/CII statement taken from the solution's violations (None when unknown)."""
    if not status:
        return None
    if status["feasible"]:
        return (
            "The plan meets all route demand, arrival schedules, fuel availability and carbon-intensity limits in the model."
            if plain else
            "Feasible: no demand deficit, schedule delay, fuel-availability, CII or vessel-availability violations."
        )
    parts = []
    for key, val in status["violations"].items():
        if val > 0 and key in _VIOLATION_TEXT:
            tech, simple = _VIOLATION_TEXT[key]
            txt = simple if plain else tech
            parts.append(txt.format(val) if "{" in txt else txt)
    return ("The plan does not meet every requirement: " if plain else "Infeasible: ") + "; ".join(parts) + "."


def _img(b64: str, alt: str, caption: str) -> str:
    if not b64:
        return ""
    return (
        f'<div class="chart-box"><img src="data:image/png;base64,{b64}" alt="{alt}" />'
        f'<div class="caption">{caption}</div></div>'
    )


def _method_rows(mc: dict[str, Any], plain: bool) -> list[tuple[str, str, str, str]]:
    """(label, ours, ga, verdict) per benchmark instance."""
    rows = []
    for inst in mc.get("instances", []):
        q = (inst["algos"].get("QIEA") or {}).get("wall_time_s")
        g = (inst["algos"].get("GA") or {}).get("wall_time_s")
        sp = inst.get("speedup_vs_ga")
        if sp is None:
            verdict = _DASH
        elif sp >= 1:
            verdict = f"{sp:.2f}× faster"
        else:
            verdict = f"{1 / sp:.2f}× slower"
        n = inst.get("n_vessels")
        label = f"{n} ships" if (plain and n) else (f"{inst['instance']} ({n} vessels)" if n else inst["instance"])
        rows.append((label, _num(q, ".1f", suffix=" s"), _num(g, ".1f", suffix=" s"), verdict))
    return rows


_DATA_URI = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+")

_PROHIBITED_JARGON = [
    (r"\bpareto\b", "optimal trade-off"),
    (r"\bknee-point\b", "balanced recommended option"),
    (r"\bknee\b", "recommended choice"),
    (r"\bhypervolume\b", "plan quality score"),
    (r"\bwtw\b", "lifecycle"),
    (r"\bmetaheuristic\b", "optimization engine"),
    (r"\bnon-dominated\b", "best-in-class"),
    (r"\bnsga-ii\b", "standard method"),
    (r"\bmopso\b", "standard method"),
    (r"\bqiea\b", "our optimizer"),
    (r"\bqpso\b", "our optimizer"),
    (r"\bga\b", "standard method"),
]


def _jargon_guard(html: str) -> str:
    """Replace algorithmic jargon in text only: embedded images are left byte-identical,
    and the patterns are whole alphabetic words, so no number is ever altered."""
    def clean(text: str) -> str:
        for pattern, replacement in _PROHIBITED_JARGON:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    out, pos = [], 0
    for m in _DATA_URI.finditer(html):
        out.append(clean(html[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(clean(html[pos:]))
    return "".join(out)


# ===================================================================== #
#  1. Executive Summary (plain language)                                 #
# ===================================================================== #
def generate_summary_html(data: dict[str, Any]) -> str:
    """Executive Summary HTML. All sentences are conditional on the data's signs and presence."""
    kpis = data.get("kpi_deltas") or {}
    fc = kpis.get("fuel_cost") or {}
    ghg = kpis.get("ghg_wtw") or {}
    cars = data.get("cars_equivalent")
    decomp = data.get("savings_decomposition")
    plan_status = (data.get("constraints") or {}).get("plan")

    # --- Bottom line -------------------------------------------------- #
    bl = []
    d, p = fc.get("delta"), fc.get("delta_pct")
    pct = f" ({_signed(p, '.1f', suffix='%')})" if p is not None else ""
    if d is None:
        bl.append(f"<p>💰 Fuel cost vs today: {_DASH}</p>")
    elif d < 0:
        bl.append(f"<p>💰 <strong>Save ${abs(d):,.0f} on fuel</strong> compared with today's plan{pct} — a reduction.</p>")
    elif d > 0:
        bl.append(f"<p>💰 <strong>Fuel cost goes up by ${d:,.0f}</strong> compared with today's plan{pct} — an increase.</p>")
    else:
        bl.append("<p>💰 Fuel cost is unchanged compared with today's plan.</p>")

    d, p = ghg.get("delta"), ghg.get("delta_pct")
    pct = f" ({_signed(p, '.1f', suffix='%')})" if p is not None else ""
    if d is None:
        bl.append(f"<p>🌍 Carbon emissions vs today: {_DASH}</p>")
    elif d < 0:
        car_txt = f" — about the yearly CO₂ of <strong>{cars:,} cars</strong>" if cars else ""
        bl.append(f"<p>🌍 <strong>Cut carbon emissions by {abs(d):,.0f} tonnes</strong>{pct} — a reduction{car_txt}.</p>")
    elif d > 0:
        bl.append(f"<p>🌍 <strong>Carbon emissions go up by {d:,.0f} tonnes</strong>{pct} — an increase.</p>")
    else:
        bl.append("<p>🌍 Carbon emissions are unchanged compared with today's plan.</p>")

    cs = _constraint_sentence(plan_status, plain=True)
    if cs:
        mark = "✅" if plan_status["feasible"] else "⚠️"
        bl.append(f'<p class="badge-check">{mark} {cs}</p>')

    b64_kpi = fig_to_base64_png(kpi_bars(data), save_filename="kpi_bars.png")

    # --- Levers ------------------------------------------------------- #
    if decomp:
        b64_wf = fig_to_base64_png(ghg_waterfall(data, style="simple"), save_filename="waterfall_simple.png")
        lever_html = _img(b64_wf, "Emissions change by lever", "Figure 2: Change in carbon emissions from today's plan, one bar per type of change.")
        lever_html += "<ul>"
        for key, label in (
            ("deployment_t", "🚢 Which ships sail which routes"),
            ("slow_steaming_t", "🐢 Sailing speeds"),
            ("fuel_switch_t", "⛽ Fuel choices"),
            ("shore_power_t", "🔌 Plugging into port electricity"),
        ):
            v = decomp[key]
            word = "saves" if v > 0 else ("adds" if v < 0 else "changes")
            amount = f"{abs(v):,.0f} t CO₂e"
            lever_html += f"<li><strong>{label}</strong> {word} {amount}.</li>"
        lever_html += "</ul>"
    else:
        lever_html = "<p>A breakdown by type of change is not available for this report (the fuel model was not supplied).</p>"

    # --- Options table -------------------------------------------------- #
    options_rows = ""
    for opt in data.get("three_options") or []:
        highlight = "background-color: #e8f8f5; font-weight: bold;" if opt["tier"] == "Recommended" else ""
        options_rows += (
            f'<tr style="{highlight}"><td><strong>{opt["name"]}</strong></td>'
            f'<td>${opt["fuel_cost_usd"] / 1e6:.2f}M</td><td>{opt["ghg_wtw_tco2e"]:,.0f} t</td>'
            f'<td>{opt["extra_cost_vs_cheapest"]}</td><td>{opt["best_for"]}</td></tr>'
        )
    options_html = ""
    if options_rows:
        options_html = f"""
        <h2>Pick Your Priority</h2>
        <table>
            <thead><tr><th>Option</th><th>Fuel Cost</th><th>Carbon</th><th>Extra Cost vs Cheapest</th><th>Recommended When</th></tr></thead>
            <tbody>{options_rows}</tbody>
        </table>"""
        share = data.get("recommended_share")
        if share and share.get("ghg_pct") is not None:
            cost_txt = (
                f" for {share['cost_pct']:.0f}% of the extra fuel cost" if share.get("cost_pct") is not None else ""
            )
            options_html += (
                f"<p><em>The recommended option closes {share['ghg_pct']:.0f}% of the carbon gap between the "
                f"cheapest and the greenest option{cost_txt}.</em></p>"
            )

    # --- Top ships ------------------------------------------------------ #
    ship_rows = "".join(
        f"<tr><td><strong>{s['vessel_id']}</strong></td><td>{s['route_id']}</td><td>{s['change_vs_bau']}</td></tr>"
        for s in data.get("top_5_ships") or []
    )
    ships_html = (
        f"""<h2>Top Ship Changes</h2><table><thead><tr><th>Ship</th><th>Route</th><th>Change vs today</th></tr></thead>
        <tbody>{ship_rows}</tbody></table>""" if ship_rows else ""
    )

    # --- Trust bullets --------------------------------------------------- #
    trust = []
    mrv = data.get("mrv_info") or {}
    tm = mrv.get("test_metrics") or {}
    if mrv.get("records"):
        acc = ""
        if tm.get("r2") is not None and tm.get("mape") is not None:
            acc = (
                f" On ships it had not seen, it explains {100 * tm['r2']:.0f}% of the variation in fuel use, "
                f"with a typical error of {tm['mape']:.0f}%."
            )
        trust.append(f"Fuel model trained on <strong>{mrv['records']:,} real ship reports</strong> from the EU MRV register.{acc}")
    trust.append("Official IMO and EU emission conversion factors are applied throughout.")
    if kpis.get("cii_bands"):
        trust.append(f"Carbon-intensity rating (approximate, A–E): {kpis['cii_bands']}.")

    mc = data.get("method_comparison")
    method_html = ""
    if mc and mc.get("instances"):
        rows = "".join(
            f"<tr><td>{lbl}</td><td>{ours}</td><td>{ga}</td><td>{verdict}</td></tr>"
            for lbl, ours, ga, verdict in _method_rows(mc, plain=True)
        )
        best = mc.get("qiea_hv_best_count")
        n_cmp = mc.get("hv_instances_compared")
        quality = (
            f"<p>Plan quality score: our optimizer scored best on {best} of {n_cmp} fleet sizes tested"
            f"{' (' + str(mc['n_seeds']) + ' random seeds each)' if mc.get('n_seeds') else ''}.</p>"
            if n_cmp else ""
        )
        method_html = f"""
        <h3 style="margin-top: 14px; margin-bottom: 6px; color: #2c3e50; font-size: 11pt;">How our method compares</h3>
        <table>
            <thead><tr><th>Fleet tested</th><th>Our optimizer (run time)</th><th>Standard method (run time)</th><th>Our speed</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        {quality}"""
    trust_html = "".join(f"<li>✔ {t}</li>" for t in trust)

    # --- What to watch --------------------------------------------------- #
    watch = ""
    sens = data.get("sensitivity")
    if sens:
        lo, hi = min(sens["carbon_price"]), max(sens["carbon_price"])
        x = sens.get("crossover_carbon_price")
        if x is not None:
            watch = (
                f"<p>📈 <strong>Carbon price threshold:</strong> in the carbon-price test (${lo:,.0f}–${hi:,.0f} per tonne), "
                f"green methanol is chosen for at least as many ships as heavy fuel oil from ${x:,.0f} per tonne.</p>"
            )
        else:
            watch = (
                f"<p>📈 <strong>Carbon price:</strong> in the carbon-price test (${lo:,.0f}–${hi:,.0f} per tonne), "
                "green methanol never overtook heavy fuel oil — no crossover in the swept range.</p>"
            )
    watch_html = f"<h2>What to Watch</h2>{watch}" if watch else ""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>QGreenFleet — Your Fleet Plan</title>
        <style>{_SUMMARY_CSS}</style>
    </head>
    <body>
        <h1>🚢 QGreenFleet — Your Fleet Plan</h1>
        <div class="subtitle">
            <strong>Date:</strong> {data.get('date') or _DASH} |
            <strong>Fleet:</strong> {_num(data.get('fleet_size'))} ships, {_num(data.get('routes_count'))} routes |
            <strong>Report ID:</strong> {data.get('report_id') or _DASH}
        </div>

        <div class="bottom-line">
            <h3 style="margin-top:0; color:#1e824c;">The Bottom Line</h3>
            {''.join(bl)}
        </div>

        {_img(b64_kpi, "Performance comparison", "Figure 1: Today's plan (grey) vs recommended plan (green).")}

        <div class="page-break"></div>

        <h2>Where the Change Comes From</h2>
        {lever_html}
        {options_html}
        {ships_html}

        <h2>Can You Trust These Numbers?</h2>
        <ul>{trust_html}</ul>
        {method_html}
        {watch_html}
    </body>
    </html>
    """
    return _jargon_guard(html)


def generate_summary_pdf(data: dict[str, Any]) -> bytes:
    """Generate the Executive Summary PDF."""
    html = generate_summary_html(data)

    if _WEASYPRINT_AVAILABLE:
        try:
            return weasyprint.HTML(string=html).write_pdf()
        except Exception:
            pass

    return _render_minimal_pdf("QGreenFleet Executive Summary", html)


# ===================================================================== #
#  2. Technical Fleet Optimization Report                                #
# ===================================================================== #
def generate_technical_html(data: dict[str, Any]) -> str:
    """Technical report HTML. Every number is taken from `data` or committed artefacts."""
    kpis = data.get("kpi_deltas") or {}
    fc = kpis.get("fuel_cost") or {}
    ghg = kpis.get("ghg_wtw") or {}
    opex = kpis.get("opex") or {}
    cons = data.get("constraints") or {}
    plan_st, bau_st = cons.get("plan"), cons.get("bau")
    decomp = data.get("savings_decomposition")
    knee_id = data.get("selected_knee_id")

    b64_fig1 = fig_to_base64_png(kpi_bars(data), save_filename="kpi_bars.png")
    pareto_df = pd.DataFrame(data.get("pareto_points") or [])
    b64_fig2 = (
        fig_to_base64_png(pareto_scatter(pareto_df, knee_id=knee_id), save_filename="pareto_scatter.png")
        if not pareto_df.empty else ""
    )
    routes_geo = [r for r in data.get("routes") or [] if r.get("from") and r.get("to")]
    b64_fig3 = fig_to_base64_png(fleet_map({}, {"routes": routes_geo}), save_filename="fleet_map.png") if routes_geo else ""
    has_speeds = any(p.get("speed_kn") is not None and p.get("bau_speed_kn") is not None for p in data.get("per_vessel_plan") or [])
    b64_fig4 = fig_to_base64_png(speed_dumbbell(data), save_filename="speed_dumbbell.png") if has_speeds else ""
    b64_fig5 = fig_to_base64_png(ghg_waterfall(data, style="technical"), save_filename="ghg_waterfall.png") if decomp else ""
    b64_fig6 = fig_to_base64_png(fuel_mix_donut(data), save_filename="fuel_mix_donut.png") if data.get("fuel_mix_pct") else ""
    b64_fig7 = _file_to_base64(_PROJECT_ROOT / "outputs" / "parity_mrv.png")
    sfp = data.get("speed_fuel_points")
    b64_fig8 = fig_to_base64_png(speed_fuel_curve(sfp), save_filename="speed_fuel_curve.png") if sfp else ""
    b64_fig9 = _file_to_base64(_PROJECT_ROOT / "outputs" / "calibration_check.png")
    b64_fig10 = _file_to_base64(_PROJECT_ROOT / "outputs" / "convergence_S.png")
    b64_fig11 = _file_to_base64(_PROJECT_ROOT / "outputs" / "hv_boxplot.png")
    b64_scal = _file_to_base64(_PROJECT_ROOT / "outputs" / "scalability.png")
    sens = data.get("sensitivity")
    b64_fig12 = fig_to_base64_png(carbon_sweep(sens), save_filename="carbon_sweep.png") if sens else ""
    b64_fig13 = _file_to_base64(_PROJECT_ROOT / "charts" / "architecture_diagram.png") or _file_to_base64(
        _PROJECT_ROOT / "charts" / "algorithm_diagram.png"
    )
    b64_data_trust = _file_to_base64(_PROJECT_ROOT / "charts" / "data_trust_diagram.png")

    # §1 KPI table
    def status_cell(st: dict[str, Any] | None, key: str) -> str:
        if not st:
            return _DASH
        if key == "demand":
            return _num(st.get("demand_met_pct"), ".1f", suffix="%")
        if key == "delay":
            return _num(st["violations"]["schedule_delay"], ",.1f", suffix=" h")
        if key == "cii":
            return f"{st['cii_a_to_c']} / {st['deployed']}" if st["deployed"] else _DASH
        return "yes" if st["feasible"] else "no"

    plan_label = "Recommended plan" + (f" ({knee_id}, knee)" if knee_id and data.get("solution_is_knee") else "")
    constraint_line = _constraint_sentence(plan_st, plain=False)

    # §3 vessel rows
    plan_rows = "".join(
        f"<tr><td>{p['vessel_id']}</td><td>{p.get('type') or _DASH}</td><td>{_num(p.get('dwt'))}</td>"
        f"<td>{p['route_id']}</td><td>{_num(p.get('speed_kn'), '.1f')}</td><td>{p.get('fuel') or _DASH}</td>"
        f"<td>{_num(p.get('fuel_cost'), prefix='$')}</td><td>{_num(p.get('ghg_tco2e'))}</td>"
        f"<td><strong>{p.get('cii_band') or _DASH}</strong></td><td>{p['change_vs_bau']}</td></tr>"
        for p in data.get("per_vessel_plan") or []
    )
    plan_table = (
        f"""<table><thead><tr><th>Vessel</th><th>Type</th><th>DWT</th><th>Route</th><th>Speed (kn)</th><th>Fuel</th>
        <th>Fuel Cost</th><th>CO₂e (t)</th><th>CII*</th><th>Δ vs BAU</th></tr></thead><tbody>{plan_rows}</tbody></table>
        <p style="font-size:8.5pt;color:#555;">*CII band from attained/required CII using the IMO bulk-carrier rating
        boundaries (0.86/0.94/1.06/1.18) as a common approximation for all ship types.</p>"""
        if plan_rows else "<p>No per-vessel decisions were supplied with this solution.</p>"
    )

    # §4 decomposition
    if decomp:
        lever_rows = "".join(
            f"<tr><td>{label}</td><td>{_signed(-decomp[k], suffix=' t')}</td><td>{_change_word(-decomp[k]) or _DASH}</td></tr>"
            for k, label in (
                ("deployment_t", "Deployment / assignment (plan vs BAU vessels, HFO, BAU speeds)"),
                ("slow_steaming_t", "Speed (plan vs BAU speeds, HFO)"),
                ("fuel_switch_t", "Fuel switching"),
                ("shore_power_t", "Shore power"),
            )
        )
        decomp_html = f"""
        <table><thead><tr><th>Lever (sequential attribution)</th><th>GHG change</th><th></th></tr></thead>
        <tbody>
        <tr><td>BAU total</td><td>{decomp['bau_t']:,.0f} t</td><td></td></tr>
        {lever_rows}
        <tr><td><strong>Plan total</strong></td><td><strong>{decomp['plan_t']:,.0f} t</strong></td>
        <td>{_signed(decomp['plan_t'] - decomp['bau_t'], suffix=' t')} overall</td></tr>
        </tbody></table>
        {_img(b64_fig5, "GHG Waterfall", "Figure 5: Exact additive attribution of the GHG change from BAU to the plan.")}"""
    else:
        decomp_html = "<p>Lever decomposition not available: requires the fuel predictor and decision-level BAU and plan solutions.</p>"

    # §5 model table
    model_rows = "".join(
        f"<tr><td><strong>{m['model']}</strong></td><td>{m['cv_rmse']}</td><td>{m['test_rmse']}</td>"
        f"<td>{m['test_mape']}</td><td>{m.get('test_r2', _DASH)}</td><td>{m['selected']}</td></tr>"
        for m in data.get("model_metrics") or []
    )
    mrv = data.get("mrv_info") or {}
    model_html = (
        f"""<table><thead><tr><th>Model</th><th>5-Fold CV RMSE</th><th>Test RMSE</th><th>Test MAPE</th><th>Test R²</th>
        <th>Status</th></tr></thead><tbody>{model_rows}</tbody></table>""" if model_rows
        else "<p>Model metadata (models/*_meta.json) not found.</p>"
    )
    model_intro = f"<p>Stage 1 dataset: {mrv['dataset']}.</p>" if mrv.get("dataset") else ""

    # §6 benchmark
    mc = data.get("method_comparison")
    if mc and mc.get("instances"):
        algos = mc["algos"]
        head = "".join(f"<th>{a}</th>" for a in algos)

        def metric_row(label: str, col: str, fmt: str) -> str:
            out = ""
            for inst in mc["instances"]:
                n = f" ({inst['n_vessels']} vessels)" if inst.get("n_vessels") else ""
                cells = "".join(
                    f"<td>{_num((inst['algos'].get(a) or {}).get(col), fmt)}</td>" for a in algos
                )
                out += f"<tr><td>{label} — {inst['instance']}{n}</td>{cells}</tr>"
            return out

        cols = set()
        for inst in mc["instances"]:
            for a in inst["algos"].values():
                cols |= {k for k, v in a.items() if v is not None}
        body = metric_row("Mean wall time (s)", "wall_time_s", ".1f")
        if "hv" in cols:
            body += metric_row("Mean hypervolume", "hv", ".4f")
        if "archive_size" in cols:
            body += metric_row("Mean archive size", "archive_size", ".1f")
        if "feasible_count" in cols:
            body += metric_row("Mean feasible count", "feasible_count", ".1f")
        speed_rows = "".join(
            f"<tr><td>{lbl}</td><td>{verdict}</td></tr>" for lbl, _, _, verdict in _method_rows(mc, plain=False)
        )
        best, n_cmp = mc.get("qiea_hv_best_count"), mc.get("hv_instances_compared")
        hv_line = (
            f"<p>QIEA had the highest mean hypervolume on {best} of {n_cmp} instances.</p>" if n_cmp else ""
        )
        seeds = f" Means over {mc['n_seeds']} seeds." if mc.get("n_seeds") else ""
        bench_html = f"""
        <p>Source: outputs/benchmark_results.csv; instances and budgets in configs/benchmark.yaml.{seeds}</p>
        <table><thead><tr><th>Metric</th>{head}</tr></thead><tbody>{body}</tbody></table>
        <table><thead><tr><th>Instance</th><th>QIEA wall time vs GA</th></tr></thead><tbody>{speed_rows}</tbody></table>
        {hv_line}"""
    else:
        bench_html = "<p>Benchmark results (outputs/benchmark_results.csv) not found.</p>"

    # §7 sensitivity
    if sens:
        lo, hi = min(sens["carbon_price"]), max(sens["carbon_price"])
        x = sens.get("crossover_carbon_price")
        sens_txt = (
            f"Green methanol share first reaches the HFO share at ${x:,.0f}/t CO₂e."
            if x is not None else "No crossover in the swept range: green methanol never reached the HFO share."
        )
        sens_html = f"""<p>Swept carbon price ${lo:,.0f}–${hi:,.0f}/t CO₂e. {sens_txt}</p>
        {_img(b64_fig12, "Carbon sweep", "Figure 12: Share of deployed ships per fuel vs carbon price.")}"""
    else:
        sens_html = "<p>No carbon-price sweep data was supplied with this report.</p>"

    carbon = data.get("carbon_price")
    gens = data.get("generations")
    meta_line = (
        f"<strong>Carbon price:</strong> ${carbon:,.0f}/t | " if carbon else ""
    ) + f"<strong>Fleet:</strong> {_num(data.get('fleet_size'))} vessels, {_num(data.get('routes_count'))} routes"
    engine_line = "<strong>Engine:</strong> QIEA + QPSO" + (f" ({gens} generations recorded)" if gens else "")

    n_pareto = len(data.get("pareto_points") or [])

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>QGreenFleet — Technical Fleet Optimization Report</title>
        <style>{_TECH_CSS}</style>
    </head>
    <body>
        <h1>QGreenFleet — Technical Fleet Optimization Report</h1>
        <div class="metadata">
            <strong>Generated:</strong> {data.get('date') or _DASH} | <strong>Report ID:</strong> {data.get('report_id') or _DASH}<br>
            {meta_line}<br>
            {engine_line}
        </div>

        <h2>1. Summary</h2>
        <table>
            <thead><tr><th>KPI</th><th>BAU Baseline</th><th>{plan_label}</th><th>Delta (plan − BAU)</th></tr></thead>
            <tbody>
                <tr><td>Fuel cost ($)</td><td>{_num(fc.get('bau'), prefix='$')}</td><td>{_num(fc.get('opt'), prefix='$')}</td><td><strong>{_delta_cell(fc, prefix='$')}</strong></td></tr>
                <tr><td>WtW GHG (t CO₂e)</td><td>{_num(ghg.get('bau'), suffix=' t')}</td><td>{_num(ghg.get('opt'), suffix=' t')}</td><td><strong>{_delta_cell(ghg, suffix=' t')}</strong></td></tr>
                <tr><td>OPEX ($)</td><td>{_num(opex.get('bau'), prefix='$')}</td><td>{_num(opex.get('opt'), prefix='$')}</td><td><strong>{_delta_cell(opex, prefix='$')}</strong></td></tr>
                <tr><td>Demand satisfied</td><td>{status_cell(bau_st, 'demand')}</td><td>{status_cell(plan_st, 'demand')}</td><td></td></tr>
                <tr><td>Total schedule delay</td><td>{status_cell(bau_st, 'delay')}</td><td>{status_cell(plan_st, 'delay')}</td><td></td></tr>
                <tr><td>Deployed vessels in CII A–C*</td><td>{status_cell(bau_st, 'cii')}</td><td>{status_cell(plan_st, 'cii')}</td><td></td></tr>
                <tr><td>All constraints met</td><td>{status_cell(bau_st, 'feasible')}</td><td>{status_cell(plan_st, 'feasible')}</td><td></td></tr>
            </tbody>
        </table>
        {f'<p>{constraint_line}</p>' if constraint_line else ''}
        {_img(b64_fig1, "KPI comparison", "Figure 1: BAU baseline vs recommended plan.")}

        <div class="page-break"></div>

        <h2>2. Pareto Frontier & Trade-Off Surface</h2>
        <p>{n_pareto} non-dominated solutions with objective values were supplied.</p>
        {_img(b64_fig2, "Pareto Scatter", "Figure 2: Pareto front: X = fuel cost ($M), Y = WtW GHG (kt CO₂e), marker size = OPEX. Star marks the knee.")}

        <h2>3. Recommended Deployment Plan</h2>
        {_img(b64_fig3, "Fleet Corridor Map", "Figure 3: Route corridors (orange = shore power available on the route).")}
        {_img(b64_fig4, "Speed dumbbell chart", "Figure 4: Per-vessel speed, BAU (grey) vs plan (green).")}
        {plan_table}

        <div class="page-break"></div>

        <h2>4. Emission Profile & Decomposition</h2>
        {decomp_html}
        {_img(b64_fig6, "Fuel Mix Donut", "Figure 6: Deployed ships by fuel.")}
        <p><em>Emission factors: IMO 4th GHG Study (2020), FuelEU Maritime Regulation (EU) 2023/1805 Annex II, IPCC AR5 GWP₁₀₀.</em></p>

        <h2>5. Fuel Prediction Model</h2>
        {model_intro}
        {model_html}
        {_img(b64_data_trust, "Data Trust Governance", "Figure 7a: Data provenance and validation.")}
        {_img(b64_fig7, "Parity Plot", "Figure 7b: Parity plot of the stage-1 MRV model on held-out ships.")}
        {_img(b64_fig8, "Speed-fuel curve", "Figure 8: Predictor fuel consumption vs speed (draft 10 m, moderate weather).")}
        {_img(b64_fig9, "Calibration Check", "Figure 9: Calibration check against EU MRV fuel-per-nm distributions.")}

        <div class="page-break"></div>

        <h2>6. Optimizer Benchmark</h2>
        {bench_html}
        {_img(b64_fig10, "Convergence curves", "Figure 10: Hypervolume convergence across seeds.")}
        {_img(b64_fig11, "HV Boxplot", "Figure 11a: Hypervolume distribution per algorithm.")}
        {_img(b64_scal, "Scalability", "Figure 11b: Wall time vs fleet size.")}

        <h2>7. Carbon Price Sensitivity</h2>
        {sens_html}

        <h2>8. Algorithmic Methodology</h2>
        <p>QGreenFleet couples Quantum-Inspired Evolutionary Algorithms (QIEA, Han & Kim 2002) for combinatorial assignment, fuel selection, and shore power with Quantum-behaved Particle Swarm Optimization (QPSO, Sun et al. 2004) for continuous speed vectors. Non-dominated sorting and crowding distances maintain diversity in an external elitist archive. All algorithms execute as quantum-inspired surrogates on classical hardware.</p>
        {_img(b64_fig13, "Algorithm Architecture", "Figure 13: Hybrid QIEA+QPSO generational optimization loop.")}
    </body>
    </html>
    """
    return html


def generate_technical_pdf(data: dict[str, Any]) -> bytes:
    """Generate the Technical Fleet Optimization Report PDF."""
    html = generate_technical_html(data)

    if _WEASYPRINT_AVAILABLE:
        try:
            return weasyprint.HTML(string=html).write_pdf()
        except Exception:
            pass

    return _render_minimal_pdf("QGreenFleet Technical Report", html)


def _render_minimal_pdf(title: str, html: str) -> bytes:
    """Robust minimal PDF byte generator fallback for environments without native rendering."""
    # Clean text content from HTML
    text_content = re.sub(r"<[^>]+>", "\n", html)
    lines = [line.strip() for line in text_content.splitlines() if line.strip()]

    header = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    content_stream = f"BT /F1 12 Tf 50 750 Td ({title}) Tj ET\n"
    for i, l in enumerate(lines[:45]):
        clean_l = l.replace("(", "").replace(")", "").replace("\\", "")
        content_stream += f"BT /F1 9 Tf 50 {720 - i*14} Td ({clean_l[:80]}) Tj ET\n"

    b_content = content_stream.encode("latin1", errors="replace")
    obj3 = f"3 0 obj<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>/MediaBox[0 0 595 842]/Contents 5 0 R>>endobj\n4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n5 0 obj<</Length {len(b_content)}>>stream\n".encode("ascii")
    footer = b"\nendstream\nendobj\nxref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000214 00000 n \n0000000281 00000 n \ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n380\n%%EOF"
    return header + obj3 + b_content + footer
