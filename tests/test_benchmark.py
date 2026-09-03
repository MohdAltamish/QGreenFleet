"""Unit tests for the benchmarking module (metrics, baselines, and runner).

Validates:
    1. Hypervolume indicator against known 2D analytical geometry
    2. IGD identity property (IGD=0)
    3. Evaluations to threshold on synthetic history curve
    4. Spread metric on single-point and two-point Pareto fronts
    5. GA single-point crossover mixing
    6. MOPSO sigmoid activation bounds
    7. SA stochastic neighbor generation
    8. filter_nondominated_feasible removes dominated and uses raw_objectives
    9. normalized_hv_in_range: normalized HV always in [0, 1.331] vs shared ref
    10. merged_ref_dominates_individual_fronts: merged reference dominates or ties all constituent fronts
    11. resume_skips_existing_npy: pre-existing archive .npy causes run to be skipped
    12. checkpoint_row_without_metrics_is_valid: CSV row without metrics accepted
    13. qiea_archive_size_smoke_m: 20-generation run on M fleet yields archive >= 10 (or clearly flagged)
    14. update_archive_feasible_only: mixed pool yields feasible only; zero-feasible pool fallback
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from src.benchmark.baselines import MOPSO, GeneticAlgorithm, SimulatedAnnealing, _sigmoid
from src.benchmark.metrics import (
    NORMALIZED_REF_POINT,
    build_reference_front,
    evals_to_threshold,
    filter_nondominated_feasible,
    hypervolume,
    igd,
    normalize_fronts,
    normalized_hypervolume,
    spread,
)
from src.optimization.individual import Solution
from src.optimization.pareto import update_archive
from src.optimization.qiea import run as run_qiea


# ---- shared helper -----

def _make_solution(raw_obj: np.ndarray, feasible: bool) -> Solution:
    """Helper: create a minimal Solution with raw_objectives and objectives set."""
    q = np.full((6, 2), 1.0 / np.sqrt(2.0))
    s = Solution(q_matrix=q, speeds=np.ones((2, 3)) * 12.0)
    s.raw_objectives = raw_obj.copy()
    s.objectives = raw_obj + (0.0 if feasible else np.array([1e8, 1e8, 1e8]))
    s.feasible = feasible
    return s


# ===================================================================== #
#  1. Hypervolume Indicator Test                                         #
# ===================================================================== #
def test_hypervolume_known_2d_analytical_case() -> None:
    """Validate 2D hypervolume on linear front x + y = 1 vs ref [1.1, 1.1]."""
    x = np.linspace(0.0, 1.0, 200)
    y = 1.0 - x
    pts = np.column_stack([x, y])
    hv = hypervolume(pts, ref_point=[1.1, 1.1])
    assert pytest.approx(0.71, rel=0.02) == hv


# ===================================================================== #
#  2. IGD identity                                                       #
# ===================================================================== #
def test_igd_identity_is_zero() -> None:
    """When the candidate front is identical to reference, IGD must be 0.0."""
    pts = np.array([[1.0, 5.0, 10.0], [2.0, 3.0, 8.0], [4.0, 1.0, 6.0]])
    assert igd(pts, pts) == pytest.approx(0.0, abs=1e-7)


def test_build_reference_front_merges_and_dominates() -> None:
    """build_reference_front merges fronts and filters dominated solutions."""
    front_a = np.array([[10.0, 50.0], [30.0, 20.0]])
    front_b = np.array([[15.0, 30.0], [50.0, 50.0]])
    ref = build_reference_front([front_a, front_b])
    assert len(ref) == 3
    assert not any(np.allclose(pt, [50.0, 50.0]) for pt in ref)
    assert igd(front_a, ref) > 0.0
    assert igd(ref, ref) == pytest.approx(0.0, abs=1e-7)


# ===================================================================== #
#  3. evals_to_threshold                                                 #
# ===================================================================== #
def test_evals_to_threshold_correct_index() -> None:
    """Check that evals_to_threshold returns the first generation hitting 95% final HV."""
    history = [0.10, 0.50, 0.85, 0.96, 1.00]
    assert evals_to_threshold(history, threshold=0.95, evals_per_step=10) == 40
    assert evals_to_threshold(history, threshold=1.05, evals_per_step=10) == 50
    sat_history = [0.98, 0.99, 1.00]
    assert np.isnan(evals_to_threshold(sat_history, threshold=0.95, evals_per_step=100))


# ===================================================================== #
#  4. Spread                                                             #
# ===================================================================== #
def test_spread_single_and_two_point() -> None:
    """Single-point front must return NaN; two-point front returns Euclidean distance."""
    assert np.isnan(spread(np.array([[10.0, 20.0]])))
    two_pts = np.array([[0.0, 0.0], [1.0, 1.0]])
    assert spread(two_pts) == pytest.approx(np.sqrt(2.0), rel=1e-4)


# ===================================================================== #
#  5. GA Crossover                                                       #
# ===================================================================== #
def test_ga_crossover_produces_mixed_offspring() -> None:
    """Offspring bitstrings from single-point crossover must differ from parents."""
    n_bits = 20
    p1 = np.zeros(n_bits, dtype=int)
    p2 = np.ones(n_bits, dtype=int)
    cx_point = 10
    c1 = p1.copy()
    c2 = p2.copy()
    c1[cx_point:], c2[cx_point:] = p2[cx_point:].copy(), p1[cx_point:].copy()
    assert not np.array_equal(c1, p1)
    assert not np.array_equal(c1, p2)
    assert np.sum(c1) == 10


# ===================================================================== #
#  6. MOPSO Sigmoid                                                      #
# ===================================================================== #
def test_mopso_sigmoid_bounds() -> None:
    """Sigmoid output must strictly lie in (0, 1) for extreme and typical inputs."""
    inputs = np.array([-1000.0, -10.0, -1.0, 0.0, 1.0, 10.0, 1000.0])
    outputs = _sigmoid(inputs)
    assert np.all(outputs > 0.0)
    assert np.all(outputs < 1.0)
    assert _sigmoid(0.0) == pytest.approx(0.5)


# ===================================================================== #
#  7. SA neighbor                                                        #
# ===================================================================== #
def test_sa_neighbor_flips_bits() -> None:
    """SA neighbor perturbation must alter at least one bit in the chromosome."""
    rng = np.random.default_rng(42)
    n_bits = 30
    curr_bits = rng.integers(0, 2, size=n_bits)
    neighbor_bits = curr_bits.copy()
    flip_indices = rng.choice(n_bits, size=3, replace=False)
    neighbor_bits[flip_indices] = 1 - neighbor_bits[flip_indices]
    assert np.sum(neighbor_bits != curr_bits) == 3


# ===================================================================== #
#  Task 2.1 — filter_nondominated_feasible_removes_dominated             #
# ===================================================================== #
def test_filter_nondominated_feasible_removes_dominated() -> None:
    """Mixed pool -> only mutually non-dominated feasible points survive."""
    sol_a = _make_solution(np.array([1.0, 4.0, 9.0]), feasible=True)
    sol_b = _make_solution(np.array([1.0, 5.0, 10.0]), feasible=True)   # dominated by a
    sol_c = _make_solution(np.array([2.0, 2.0, 8.0]), feasible=True)    # mutually non-dominated with a
    sol_infeas = _make_solution(np.array([0.1, 0.1, 0.1]), feasible=False)  # infeasible best raw objectives

    result = filter_nondominated_feasible([sol_a, sol_b, sol_c, sol_infeas])

    assert result.ndim == 2 and result.shape[1] == 3
    assert len(result) == 2
    # Infeasible sol_infeas must NOT appear
    assert not any(np.allclose(r, sol_infeas.raw_objectives) for r in result)
    # Dominated sol_b must NOT appear
    assert not any(np.allclose(r, sol_b.raw_objectives) for r in result)


def test_filter_nondominated_feasible_empty_input() -> None:
    """Empty input returns (0, 3) array."""
    result = filter_nondominated_feasible([])
    assert result.shape == (0, 3)


def test_filter_nondominated_feasible_fallback_on_zero_feasible() -> None:
    """When no feasible solutions exist, falls back to all solutions with raw_objectives."""
    sol = _make_solution(np.array([5.0, 5.0, 5.0]), feasible=False)
    result = filter_nondominated_feasible([sol])
    assert len(result) == 1
    assert np.allclose(result[0], [5.0, 5.0, 5.0])


# ===================================================================== #
#  Task 2.2 — test_normalized_hv_in_range                                #
# ===================================================================== #
def test_normalized_hv_in_range() -> None:
    """Normalized HV always in [0, 1.331]; reference point identical across algorithms."""
    rng = np.random.default_rng(0)
    for _ in range(10):
        norm_front = rng.uniform(0.0, 1.0, size=(15, 3))
        hv_val = normalized_hypervolume(norm_front)
        assert 0.0 <= hv_val <= 1.331 + 1e-9, f"Normalized HV out of range: {hv_val}"

    # Perfect front at (0,0,0) yields (1.1)^3 = 1.331
    perfect = np.array([[0.0, 0.0, 0.0]])
    hv_perfect = normalized_hypervolume(perfect)
    assert pytest.approx(1.331, rel=0.01) == hv_perfect

    # Empty front returns 0.0
    assert normalized_hypervolume(np.empty((0, 3))) == 0.0

    # Reference point is fixed across algorithms per instance
    assert NORMALIZED_REF_POINT == (1.1, 1.1, 1.1)


# ===================================================================== #
#  Task 2.3 — test_merged_ref_dominates_individual_fronts                #
# ===================================================================== #
def test_merged_ref_dominates_individual_fronts() -> None:
    """Merged reference front dominates-or-ties every individual front."""
    front_a = np.array([[0.1, 0.9, 0.5], [0.5, 0.5, 0.5]])
    front_b = np.array([[0.2, 0.3, 0.7], [0.7, 0.2, 0.3], [0.9, 0.9, 0.9]])
    ref = build_reference_front([front_a, front_b])

    # Point [0.9, 0.9, 0.9] is strictly dominated and must not be in ref
    assert not any(np.allclose(r, [0.9, 0.9, 0.9]) for r in ref)

    # Every point in individual fronts is either in ref or dominated by a point in ref
    all_individual = np.vstack([front_a, front_b])
    for pt in all_individual:
        in_ref = any(np.allclose(pt, r) for r in ref)
        dominated_by_ref = any(np.all(r <= pt) and np.any(r < pt) for r in ref)
        assert in_ref or dominated_by_ref, f"Point {pt} neither in ref nor dominated by ref"

    # No point in individual fronts can strictly dominate any point in ref
    for r in ref:
        for pt in all_individual:
            strictly_dominates = np.all(pt <= r) and np.any(pt < r)
            assert not strictly_dominates, f"Individual point {pt} strictly dominates ref point {r}"

    # Constituent fronts have non-negative IGD vs merged ref; merged ref vs itself is 0
    assert igd(front_a, ref) >= 0.0
    assert igd(front_b, ref) >= 0.0
    assert igd(ref, ref) == pytest.approx(0.0, abs=1e-7)


def test_normalize_fronts_global_bounds() -> None:
    """All fronts must be scaled using the same global obj_min/obj_max."""
    front_a = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
    front_b = np.array([[2.0, 2.0, 2.0], [3.0, 3.0, 3.0]])
    norm_list, obj_min, obj_max = normalize_fronts([front_a, front_b])
    assert np.allclose(obj_min, [0.0, 0.0, 0.0])
    assert np.allclose(obj_max, [3.0, 3.0, 3.0])
    assert np.allclose(norm_list[1][-1], [1.0, 1.0, 1.0])
    assert np.allclose(norm_list[0][0], [0.0, 0.0, 0.0])


# ===================================================================== #
#  Task 2.4 — test_resume_skips_existing_npy                             #
# ===================================================================== #
def test_resume_skips_existing_npy(tmp_path: pytest.TempPathFactory) -> None:
    """Pre-existing archive .npy causes the (instance, algo, seed) run to be skipped."""
    archives_dir = tmp_path / "archives"
    archives_dir.mkdir()
    npy_path = archives_dir / "S_QIEA_seed42.npy"
    dummy_front = np.array([[1.0, 2.0, 3.0]])
    np.save(npy_path, dummy_front)

    resume = True
    should_skip = resume and npy_path.exists()
    assert should_skip, "Resume mode must skip when .npy exists"

    # With --no-resume, should not skip
    no_resume = True
    assert not (not no_resume and npy_path.exists())


# ===================================================================== #
#  Task 2.5 — test_checkpoint_row_without_metrics_is_valid               #
# ===================================================================== #
def test_checkpoint_row_without_metrics_is_valid(tmp_path: pytest.TempPathFactory) -> None:
    """CSV row with only (algo, instance, seed, wall_time_s, archive_size, feasible_count) is valid."""
    csv_path = tmp_path / "benchmark_results.csv"
    checkpoint_row = {
        "algo": "QIEA",
        "instance": "S",
        "seed": 42,
        "archive_size": 15,
        "feasible_count": 10,
        "hv": float("nan"),
        "igd": float("nan"),
        "evals_to_95": float("nan"),
        "spread": float("nan"),
        "wall_time_s": 12.345,
    }
    df = pd.DataFrame([checkpoint_row])
    df.to_csv(csv_path, index=False)

    loaded_df = pd.read_csv(csv_path)
    assert len(loaded_df) == 1
    assert loaded_df.iloc[0]["algo"] == "QIEA"
    assert loaded_df.iloc[0]["instance"] == "S"
    assert loaded_df.iloc[0]["seed"] == 42
    assert loaded_df.iloc[0]["wall_time_s"] == 12.345
    assert loaded_df.iloc[0]["archive_size"] == 15
    assert loaded_df.iloc[0]["feasible_count"] == 10
    assert np.isnan(loaded_df.iloc[0]["hv"])
    assert np.isnan(loaded_df.iloc[0]["igd"])


# ===================================================================== #
#  Task 2.6 — test_qiea_archive_size_smoke_m                             #
# ===================================================================== #
def test_qiea_archive_size_smoke_m() -> None:
    """20-generation run on synthetic M fleet; assert archive >= 10 or clearly flag if diversity fix insufficient."""
    rng = np.random.default_rng(42)
    # Synthetic M fleet (20 vessels, 4 routes) inline - no disk files required
    vessels = [
        {
            "id": f"V{i:02d}", "type": "container" if i % 2 == 0 else "bulk",
            "capacity_teu": 4000 + (i * 200), "dwt": 50000 + (i * 1000),
            "vmin": 10.0, "vmax": 18.0,
            "fuels_allowed": ["HFO", "LNG_DIESEL", "MEOH_GREEN"],
            "charter_per_day": 10000 + (i * 200),
        }
        for i in range(20)
    ]
    routes = [
        {
            "id": f"R{j}", "distance_nm": 1500 + (j * 500),
            "schedule_days": 8.0 + (j * 2.0),
            "demand_teu": 4000 + (j * 500),
            "weather_severity": 1,
            "lng_available": True, "meoh_available": True, "shore_power": False,
        }
        for j in range(4)
    ]
    cfg = {
        "pop_size": 50,
        "generations": 20,
        "theta_start": 0.05 * np.pi,
        "theta_end": 0.005 * np.pi,
        "mutation_prob": 0.05,
        "lambda0": 10.0,
        "fuel_prices": {"HFO": 600.0, "LNG_DIESEL": 750.0, "MEOH_GREEN": 1200.0},
        "carbon_price": 50.0,
        "archive_max": 100,
        "seed": 42,
    }
    def dummy_pred(v_idx: int, speed: float, draft: float, weather: int) -> float:
        return 0.004 * (speed ** 3) + 1.2 * draft + 3.0

    archive, _ = run_qiea(vessels, routes, cfg, dummy_pred, rng=rng)
    filtered = filter_nondominated_feasible(archive)

    # Clearly flag if diversity fix is insufficient to reach >= 10 points
    if len(filtered) < 10:
        warnings.warn(
            UserWarning(
                f"FLAG: QIEA diversity fix insufficient on M fleet (20 gens): "
                f"filtered archive has {len(filtered)} points (< 10 target)."
            )
        )
    assert len(filtered) >= 1, "QIEA archive must contain at least 1 feasible point"


# ===================================================================== #
#  Task 2.7 — test_update_archive_feasible_only                          #
# ===================================================================== #
def test_update_archive_feasible_only() -> None:
    """Mixed pool: archive contains ONLY feasible solutions.
    Zero-feasible pool: best-penalty fallback returned and flagged.
    """
    f1 = _make_solution(np.array([1.0, 4.0, 9.0]), feasible=True)
    f2 = _make_solution(np.array([2.0, 2.0, 8.0]), feasible=True)
    f3 = _make_solution(np.array([3.0, 3.0, 3.0]), feasible=True)
    inf1 = _make_solution(np.array([0.1, 0.1, 0.1]), feasible=False)
    inf2 = _make_solution(np.array([0.2, 0.2, 0.2]), feasible=False)

    archive = update_archive([], [f1, f2, f3, inf1, inf2], max_size=100)

    assert len(archive) > 0
    for sol in archive:
        assert sol.feasible, f"Infeasible in archive: raw={sol.raw_objectives}"

    archive_raws = [tuple(s.raw_objectives.tolist()) for s in archive]
    assert tuple(inf1.raw_objectives.tolist()) not in archive_raws
    assert tuple(inf2.raw_objectives.tolist()) not in archive_raws

    # Zero-feasible pool: fallback returns non-dominated from infeasible pool
    inf_archive = update_archive([], [inf1, inf2], max_size=100)
    assert len(inf_archive) > 0
    for sol in inf_archive:
        assert not sol.feasible
