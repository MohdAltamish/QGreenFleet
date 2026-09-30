"""Unit tests for report data compilation, jargon guard, and dual PDF generation.

All tests operate strictly with inline synthetic data (no disk dependencies).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from src.optimization.bau import DEFAULT_FUEL_PRICES, compute_bau_baseline
from src.optimization.constraints import evaluate_violations
from src.optimization.individual import Solution
from src.optimization.objectives import evaluate_objectives
from ui.utils import chart_helpers
from ui.utils.chart_helpers import carbon_sweep, fleet_map, ghg_waterfall, pareto_scatter
from ui.utils.pdf_export import (
    generate_summary_html,
    generate_summary_pdf,
    generate_technical_html,
    generate_technical_pdf,
)
from ui.utils.report_data import _find_knee_solution, build_report_data


@pytest.fixture(autouse=True)
def _charts_to_tmp(tmp_path, monkeypatch):
    """Keep chart PNG side effects out of the repo's charts/ directory."""
    monkeypatch.setattr(chart_helpers, "CHARTS_DIR", tmp_path)


# ===================================================================== #
#  1. KPI Deltas Math & Cars Analogy Test                                #
# ===================================================================== #
def test_kpi_deltas_math_and_cars_equivalent() -> None:
    """Verify KPI delta subtractions and car emissions equivalent calculation."""
    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([10_000_000.0, 50_000.0, 15_000_000.0])

    opt = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    opt.objectives = np.array([8_500_000.0, 40_800.0, 13_500_000.0])

    fleet = {
        "vessels": [{"id": "V01", "type": "container", "dwt": 50000, "design_speed": 15.0}],
        "routes": [{"id": "R01", "distance_nm": 1000}],
    }

    data = build_report_data(
        solution=opt,
        pareto=[opt],
        history=None,
        fleet=fleet,
        bau=bau,
    )

    kpis = data["kpi_deltas"]
    assert kpis["fuel_cost"]["delta"] == pytest.approx(-1_500_000.0)
    assert kpis["fuel_cost"]["delta_pct"] == pytest.approx(-15.0)

    assert kpis["ghg_wtw"]["delta"] == pytest.approx(-9_200.0)
    assert kpis["ghg_wtw"]["delta_pct"] == pytest.approx(-18.4)

    # Cars equivalent: 9,200 t / 4.6 t/car = 2,000 cars
    assert data["cars_equivalent"] == 2000


# ===================================================================== #
#  2. Knee Point & Three Options Selection Test                          #
# ===================================================================== #
def test_knee_and_three_options_selection() -> None:
    """Validate utopia distance minimization and extraction of Cheapest, Recommended, and Greenest."""
    # 3 solutions in 3D (Z1, Z2, Z3):
    # s1: min cost (8M, 50k, 12M)
    # s2: balanced trade-off (9M, 42k, 13M)
    # s3: min carbon (11M, 38k, 16M)
    s1 = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    s1.objectives = np.array([8_000_000.0, 50_000.0, 12_000_000.0])

    s2 = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    s2.objectives = np.array([9_000_000.0, 42_000.0, 13_000_000.0])

    s3 = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    s3.objectives = np.array([11_000_000.0, 38_000.0, 16_000_000.0])

    pareto = [s1, s2, s3]
    knee, idx = _find_knee_solution(pareto)
    assert idx == 1  # s2 is closest to utopia point

    fleet = {
        "vessels": [{"id": "V01", "type": "container", "dwt": 50000, "design_speed": 15.0}],
        "routes": [{"id": "R01", "distance_nm": 1000}],
    }
    data = build_report_data(solution=s2, pareto=pareto, history=None, fleet=fleet, bau=s1)

    options = data["three_options"]
    assert len(options) == 3
    assert options[0]["tier"] == "Cheapest"
    assert options[0]["fuel_cost_usd"] == pytest.approx(8_000_000.0)

    assert options[1]["tier"] == "Recommended"
    assert options[1]["fuel_cost_usd"] == pytest.approx(9_000_000.0)

    assert options[2]["tier"] == "Greenest"
    assert options[2]["ghg_wtw_tco2e"] == pytest.approx(38_000.0)


# ===================================================================== #
#  3. No predictor -> no decomposition, no per-vessel estimates          #
# ===================================================================== #
def test_no_predictor_means_no_fabricated_breakdown() -> None:
    """Without a predictor the decomposition is None, never a fixed split."""
    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([10_000_000.0, 58_140.0, 18_000_000.0])
    opt = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    opt.objectives = np.array([9_000_000.0, 44_610.0, 16_000_000.0])
    fleet = {
        "vessels": [{"id": "V01", "type": "container", "dwt": 50000, "design_speed": 15.0}],
        "routes": [{"id": "R01", "distance_nm": 1000}],
    }
    data = build_report_data(solution=opt, pareto=[opt], history=None, fleet=fleet, bau=bau)
    assert data["savings_decomposition"] is None
    assert data["kpi_deltas"]["demand_satisfied"] is None
    assert data["sensitivity"] is None
    html = generate_summary_html(data)
    assert "not available" in html
    tech = generate_technical_html(data)
    for fake in ("6,840", "5,420", "1,270", "sol_007", "QGF-2026-0902-001", "84%", "$85", "11%"):
        assert fake not in html and fake not in tech, fake


# ===================================================================== #
#  4. Jargon Guard on Executive Summary Test                             #
# ===================================================================== #
def test_jargon_guard_on_executive_summary() -> None:
    """Executive summary HTML must contain zero forbidden algorithmic terms."""
    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([10_000_000.0, 50_000.0, 15_000_000.0])
    opt = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    opt.objectives = np.array([8_500_000.0, 40_000.0, 13_000_000.0])

    fleet = {
        "vessels": [{"id": "V01", "type": "container", "dwt": 50000, "design_speed": 15.0}],
        "routes": [{"id": "R01", "distance_nm": 1000}],
    }
    data = build_report_data(solution=opt, pareto=[opt], history=None, fleet=fleet, bau=bau)

    from ui.utils.pdf_export import generate_summary_html
    import re

    raw_html = generate_summary_html(data).lower()
    # Strip base64 image data-URI strings so random ASCII base64 bytes don't trigger false positives
    text_only = re.sub(r'data:image/[^;]+;base64,[^"\']+', '', raw_html)

    prohibited = [
        "pareto", "knee-point", "hypervolume", "wtw", "metaheuristic",
        "non-dominated", "nsga-ii", "mopso", "qiea", "qpso", "ga"
    ]
    for word in prohibited:
        assert not re.search(r'\b' + re.escape(word) + r'\b', text_only), (
            f"Forbidden jargon '{word}' found in Executive Summary HTML text!"
        )


# ===================================================================== #
#  5. Per-Vessel 'No Change' when Identical to BAU                       #
# ===================================================================== #
def test_per_vessel_plan_no_change_when_identical() -> None:
    """When a vessel's speed and fuel match BAU, change_vs_bau must equal 'no change'."""
    speeds = np.array([[15.0]])
    assign = np.array([[True]])
    fuels = np.array([0])  # HFO

    sol = Solution(q_matrix=np.zeros((1, 2)), speeds=speeds)
    sol.observed = {"assignment": assign, "fuel": fuels}
    sol.objectives = np.array([10_000_000.0, 50_000.0, 15_000_000.0])

    fleet = {
        "vessels": [{"id": "V01", "type": "container", "dwt": 50000, "design_speed": 15.0}],
        "routes": [{"id": "R01", "distance_nm": 1000}],
    }
    data = build_report_data(solution=sol, pareto=[sol], history=None, fleet=fleet, bau=sol)

    plan = data["per_vessel_plan"]
    assert len(plan) == 1
    assert plan[0]["change_vs_bau"] == "no change"


# ===================================================================== #
#  6. Dual PDF Generation Returns Non-Empty Bytes                        #
# ===================================================================== #
def test_dual_pdf_generation_returns_non_empty_bytes() -> None:
    """Both generate_summary_pdf and generate_technical_pdf must return non-empty bytes."""
    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([11_000_000.0, 55_000.0, 18_000_000.0])

    opt = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    opt.objectives = np.array([9_500_000.0, 42_000.0, 16_000_000.0])

    fleet = {
        "vessels": [{"id": "V01", "type": "container", "dwt": 50000, "design_speed": 15.0}],
        "routes": [{"id": "R01", "distance_nm": 1000}],
    }
    data = build_report_data(solution=opt, pareto=[opt], history=None, fleet=fleet, bau=bau)

    summary_bytes = generate_summary_pdf(data)
    assert isinstance(summary_bytes, bytes)
    assert len(summary_bytes) > 500

    tech_bytes = generate_technical_pdf(data)
    assert isinstance(tech_bytes, bytes)
    assert len(tech_bytes) > 500


# ===================================================================== #
#  7. Chart Library Robustness on Minimal Input                          #
# ===================================================================== #
def test_charts_return_figures_without_error() -> None:
    """fleet_map, pareto_scatter, and ghg_waterfall must return go.Figure objects."""
    # 1. fleet_map
    fleet = {"routes": [{"id": "R0", "from": "Singapore", "to": "Shanghai", "distance_nm": 1500}]}
    fig_m = fleet_map({}, fleet)
    assert isinstance(fig_m, go.Figure)

    # 2. pareto_scatter
    df_p = pd.DataFrame([{"solution_id": "s1", "fuel_cost_usd": 1e7, "ghg_wtw_tco2e": 5e4, "opex_usd": 2e7}])
    fig_s = pareto_scatter(df_p)
    assert isinstance(fig_s, go.Figure)

    # 3. ghg_waterfall
    data = {
        "savings_decomposition": {
            "bau_t": 50000, "plan_t": 40000, "deployment_t": -500, "slow_steaming_t": 5500,
            "fuel_switch_t": 4000, "shore_power_t": 1000, "total_reduction_t": 10000,
        },
    }
    fig_w_simple = ghg_waterfall(data, style="simple")
    fig_w_tech = ghg_waterfall(data, style="technical")
    assert isinstance(fig_w_simple, go.Figure)
    assert isinstance(fig_w_tech, go.Figure)
    assert list(fig_w_tech.data[0].y) == [50000, 500, -5500, -4000, -1000, 40000]
    # Missing data -> empty-state figure, no invented bars
    assert len(ghg_waterfall({}, style="technical").data) == 0
    assert len(carbon_sweep(None).data) == 0


# ===================================================================== #
#  8. Method Comparison Computation from Synthetic Benchmark CSV        #
# ===================================================================== #
def test_method_comparison_speedup_from_synthetic_csv(tmp_path) -> None:
    """Verify speedup_factor, n_seeds, and hv_wins correctly computed from CSV."""
    csv_file = tmp_path / "synthetic_benchmarks.csv"
    csv_content = (
        "algo,instance,seed,hv,igd,evals_to_95,spread,wall_time_s\n"
        "QIEA,L,42,100.0,0.0,50,0.0,10.0\n"
        "GA,L,42,80.0,1.0,50,0.0,18.0\n"
        "QIEA,L,7,105.0,0.0,50,0.0,10.0\n"
        "GA,L,7,85.0,1.0,50,0.0,18.0\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([10_000_000.0, 50_000.0, 15_000_000.0])
    opt = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    opt.objectives = np.array([8_500_000.0, 40_000.0, 13_000_000.0])
    fleet = {
        "vessels": [{"id": "V01", "type": "container", "dwt": 50000, "design_speed": 15.0}],
        "routes": [{"id": "R01", "distance_nm": 1000}],
    }

    data = build_report_data(
        solution=opt,
        pareto=[opt],
        history=None,
        fleet=fleet,
        bau=bau,
        benchmark_csv_path=csv_file,
    )

    comp = data["method_comparison"]
    assert comp is not None
    assert comp["instances"][0]["speedup_vs_ga"] == pytest.approx(1.8)
    assert comp["n_seeds"] == 2
    assert comp["qiea_hv_best_count"] == 1
    assert comp["hv_instances_compared"] == 1


# ===================================================================== #
#  9. Method Comparison Table Omitted when CSV Absent                   #
# ===================================================================== #
def test_method_comparison_table_omitted_when_csv_absent(tmp_path) -> None:
    """When benchmark CSV is missing, method_comparison is None and table is omitted from summary."""
    non_existent = tmp_path / "non_existent_benchmarks.csv"

    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([10_000_000.0, 50_000.0, 15_000_000.0])
    opt = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    opt.objectives = np.array([8_500_000.0, 40_000.0, 13_000_000.0])
    fleet = {
        "vessels": [{"id": "V01", "type": "container", "dwt": 50000, "design_speed": 15.0}],
        "routes": [{"id": "R01", "distance_nm": 1000}],
    }

    data = build_report_data(
        solution=opt,
        pareto=[opt],
        history=None,
        fleet=fleet,
        bau=bau,
        benchmark_csv_path=non_existent,
    )

    assert data["method_comparison"] is None

    from ui.utils.pdf_export import generate_summary_html
    html = generate_summary_html(data)
    assert "How our method compares" not in html

    summary_bytes = generate_summary_pdf(data)
    assert isinstance(summary_bytes, bytes)
    assert len(summary_bytes) > 500


# ===================================================================== #
#  10. Benchmark wording follows the CSV (slower is said plainly)        #
# ===================================================================== #
def test_method_comparison_reports_slower_and_losses(tmp_path) -> None:
    csv_file = tmp_path / "bench.csv"
    csv_file.write_text(
        "algo,instance,seed,hv,wall_time_s\n"
        "QIEA,M,42,0.1,20.0\nGA,M,42,1.0,10.0\n",
        encoding="utf-8",
    )
    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([10_000_000.0, 50_000.0, 15_000_000.0])
    fleet = {"vessels": [], "routes": []}
    data = build_report_data(solution=bau, pareto=[bau], history=None, fleet=fleet, bau=bau, benchmark_csv_path=csv_file)
    html = generate_summary_html(data)
    assert "2.00× slower" in html
    assert "best on 0 of 1" in html
    assert "faster" not in html
    tech = generate_technical_html(data)
    assert "2.00× slower" in tech
    assert "highest mean hypervolume on 0 of 1" in tech


# ===================================================================== #
#  11. Plan worse than BAU: signed increase, never "Save"                #
# ===================================================================== #
def test_worse_plan_renders_increase_not_savings() -> None:
    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([10_000_000.0, 50_000.0, 15_000_000.0])
    opt = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    opt.objectives = np.array([11_500_000.0, 55_000.0, 16_000_000.0])
    fleet = {"vessels": [{"id": "V01", "type": "container", "dwt": 50000}], "routes": [{"id": "R01"}]}
    data = build_report_data(solution=opt, pareto=[opt], history=None, fleet=fleet, bau=bau)

    assert data["kpi_deltas"]["ghg_wtw"]["delta"] == pytest.approx(5_000.0)
    assert data["cars_equivalent"] is None

    html = generate_summary_html(data)
    assert "increase" in html
    assert "Save" not in html and "Cut carbon" not in html and "cars" not in html
    assert "+15.0%" in html and "+10.0%" in html

    tech = generate_technical_html(data)
    assert "+$1,500,000" in tech and "+5,000 t" in tech
    assert "−$1,500,000" not in tech


# ===================================================================== #
#  12. Decomposition is exact on a synthetic fleet with a stub predictor #
# ===================================================================== #
class _StubPredictor:
    def predict_tpd(self, speed_kn, draft_m, weather_severity, ship_type):
        return 0.002 * np.asarray(speed_kn, dtype=float) ** 3 + 5.0


def _tiny_fleet() -> tuple[list[dict], list[dict]]:
    vessels = [
        {"id": f"V{i}", "type": t, "dwt": 60000 + 10000 * i, "capacity_teu": 3000, "design_speed": 15.0,
         "vmin": 8.0, "vmax": 20.0, "fuel_per_nm_kg": 150.0, "fuels_allowed": ["HFO", "LNG_DIESEL", "MEOH_GREEN"],
         "charter_per_day": 20000}
        for i, t in enumerate(["container", "bulk", "tanker", "container"])
    ]
    routes = [
        {"id": "R0", "distance_nm": 3000, "schedule_days": 20, "demand_teu": 3000, "shore_power": True,
         "meoh_available": True},
        {"id": "R1", "distance_nm": 5000, "schedule_days": 30, "demand_teu": 3000, "shore_power": False,
         "meoh_available": True},
    ]
    return vessels, routes


def test_decomposition_terms_sum_to_total_change() -> None:
    vessels, routes = _tiny_fleet()
    pred = _StubPredictor()
    bau = compute_bau_baseline(vessels, routes, pred, DEFAULT_FUEL_PRICES)

    plan = Solution(q_matrix=bau.q_matrix, speeds=np.full((4, 2), 12.0))
    plan.observed = {
        "assignment": np.array([[False, False], [True, False], [False, True], [False, False]]),
        "fuel": np.array([0, 2, 1, 0]),
        "shore_power": np.array([[False, False], [True, False], [False, False], [False, False]]),
    }
    evaluate_violations(plan, vessels, routes)
    evaluate_objectives(plan, vessels, routes, pred, DEFAULT_FUEL_PRICES)

    data = build_report_data(
        plan, [plan], None, {"vessels": vessels, "routes": routes}, bau,
        predictor=pred, fuel_prices=DEFAULT_FUEL_PRICES,
    )
    d = data["savings_decomposition"]
    total = d["deployment_t"] + d["slow_steaming_t"] + d["fuel_switch_t"] + d["shore_power_t"]
    assert total == pytest.approx(d["bau_t"] - d["plan_t"], abs=1e-6)
    assert d["bau_t"] == pytest.approx(bau.raw_objectives[1], abs=1e-6)
    assert d["plan_t"] == pytest.approx(plan.raw_objectives[1], abs=1e-6)
    assert d["shore_power_t"] == pytest.approx(3.0)

    # Per-vessel figures come from the model and add up to the plan totals
    deployed = [p for p in data["per_vessel_plan"] if p["route_id"] != "Reserve"]
    assert sum(p["ghg_tco2e"] for p in deployed) == pytest.approx(plan.raw_objectives[1], abs=len(deployed))
    assert sum(p["fuel_cost"] for p in deployed) == pytest.approx(plan.raw_objectives[0], abs=len(deployed))
    assert all(p["cii_band"] in "ABCDE" for p in deployed)
    assert data["constraints"]["plan"]["feasible"] == plan.feasible

    tech = generate_technical_html(data)
    assert "Deployment / assignment" in tech


# ===================================================================== #
#  13. Carbon sweep crossover only from data                              #
# ===================================================================== #
def test_no_crossover_never_prints_85() -> None:
    sweep = pd.DataFrame({
        "carbon_price": [0, 50, 85, 100, 200],
        "hfo_pct": [100, 100, 90, 80, 70],
        "lng_pct": [0, 0, 10, 20, 30],
        "meoh_pct": [0, 0, 0, 0, 0],
    })
    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([10_000_000.0, 50_000.0, 15_000_000.0])
    fleet = {"vessels": [], "routes": []}
    data = build_report_data(bau, [bau], None, fleet, bau, sweep_results=sweep)
    assert data["sensitivity"]["crossover_carbon_price"] is None
    for html in (generate_summary_html(data), generate_technical_html(data)):
        assert "$85" not in html
        assert "no crossover in the swept range" in html.lower()
    assert len(carbon_sweep(sweep).layout.shapes) == 0

    sweep2 = sweep.assign(hfo_pct=[100, 80, 40, 20, 0], meoh_pct=[0, 20, 40, 60, 90])
    data2 = build_report_data(bau, [bau], None, fleet, bau, sweep_results=sweep2)
    assert data2["sensitivity"]["crossover_carbon_price"] == 85.0
    assert "$85" in generate_summary_html(data2)


# ===================================================================== #
#  14. Jargon guard leaves numbers and images untouched                   #
# ===================================================================== #
def test_jargon_guard_keeps_numbers_and_images() -> None:
    from ui.utils.pdf_export import _jargon_guard
    html = '<p>GA 12.5 qiea 3,000</p><img src="data:image/png;base64,ab/ga+wtw=">'
    out = _jargon_guard(html)
    assert "12.5" in out and "3,000" in out
    assert "data:image/png;base64,ab/ga+wtw=" in out
    assert "standard method 12.5 our optimizer 3,000" in out
