"""Unit tests for report data compilation, jargon guard, and dual PDF generation.

All tests operate strictly with inline synthetic data (no disk dependencies).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from src.optimization.individual import Solution
from ui.utils.chart_helpers import fleet_map, ghg_waterfall, pareto_scatter
from ui.utils.pdf_export import generate_summary_pdf, generate_technical_pdf
from ui.utils.report_data import _find_knee_solution, build_report_data


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
#  3. Savings Decomposition Exact Summation Test                         #
# ===================================================================== #
def test_savings_decomposition_sums_exactly() -> None:
    """Decomposed savings levers must sum exactly to total GHG saved."""
    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([10_000_000.0, 58_140.0, 18_000_000.0])

    opt = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    opt.objectives = np.array([9_000_000.0, 44_610.0, 16_000_000.0])

    fleet = {
        "vessels": [{"id": "V01", "type": "container", "dwt": 50000, "design_speed": 15.0}],
        "routes": [{"id": "R01", "distance_nm": 1000}],
    }
    data = build_report_data(solution=opt, pareto=[opt], history=None, fleet=fleet, bau=bau)

    decomp = data["savings_decomposition"]
    tot_decomp = decomp["slow_steaming_t"] + decomp["fuel_switch_t"] + decomp["shore_power_t"]
    total_saved = 58_140.0 - 44_610.0

    assert pytest.approx(total_saved, abs=1e-5) == tot_decomp


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
        "kpi_deltas": {"ghg_wtw": {"bau": 50000, "opt": 40000}},
        "savings_decomposition": {"slow_steaming_t": 5000, "fuel_switch_t": 4000, "shore_power_t": 1000},
    }
    fig_w_simple = ghg_waterfall(data, style="simple")
    fig_w_tech = ghg_waterfall(data, style="technical")
    assert isinstance(fig_w_simple, go.Figure)
    assert isinstance(fig_w_tech, go.Figure)


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
    assert comp["speedup_factor"] == "1.8x"
    assert comp["n_seeds"] == 2
    assert comp["hv_wins"] is True


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
#  10. HV Wins Wording Switch ('Best in all' vs 'Best in most')          #
# ===================================================================== #
def test_method_comparison_hv_wins_wording_switch() -> None:
    """Wording switches between 'Best in all test runs' and 'Best in most test runs'."""
    bau = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    bau.objectives = np.array([10_000_000.0, 50_000.0, 15_000_000.0])
    opt = Solution(q_matrix=np.zeros((1, 2)), speeds=np.zeros((1, 1)))
    opt.objectives = np.array([8_500_000.0, 40_000.0, 13_000_000.0])
    fleet = {
        "vessels": [{"id": "V01", "type": "container", "dwt": 50000, "design_speed": 15.0}],
        "routes": [{"id": "R01", "distance_nm": 1000}],
    }

    from ui.utils.pdf_export import generate_summary_html

    data_all = build_report_data(solution=opt, pareto=[opt], history=None, fleet=fleet, bau=bau)
    data_all["method_comparison"] = {
        "speedup_factor": "1.8x",
        "n_seeds": 5,
        "hv_wins": True,
    }
    html_all = generate_summary_html(data_all)
    assert "Best in all test runs" in html_all
    assert "Best in most test runs" not in html_all

    data_most = build_report_data(solution=opt, pareto=[opt], history=None, fleet=fleet, bau=bau)
    data_most["method_comparison"] = {
        "speedup_factor": "1.8x",
        "n_seeds": 5,
        "hv_wins": False,
    }
    html_most = generate_summary_html(data_most)
    assert "Best in most test runs" in html_most
    assert "Best in all test runs" not in html_most
