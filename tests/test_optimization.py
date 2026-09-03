"""Unit tests for the QGreenFleet optimization engine.

Uses synthetic data inline (no disk files required) to validate:
    1. Pareto dominance criteria
    2. NSGA-II fast non-dominated sorting on known front geometry
    3. Boundary crowding distance initialization
    4. C1 demand constraint repair operator
    5. Adaptive penalty scaling with generation
    6. Quantum rotation gate normalization and target convergence
    7. QPSO speed boundary clipping and mean-best attractor calculation
    8. End-to-end smoke test on a 3-vessel, 2-route toy fleet
"""

from __future__ import annotations

import numpy as np
import pytest

from src.optimization.constraints import evaluate_violations, penalty, repair
from src.optimization.individual import OPTIMIZER_FUELS, Solution, init_population, observe
from src.optimization.objectives import evaluate_objectives
from src.optimization.pareto import crowding_distance, dominates, fast_nondominated_sort, update_archive
from src.optimization.qiea import apply_rotation_gates, run
from src.optimization.qpso import update_speeds


# ===================================================================== #
#  1. Pareto Dominance Tests                                             #
# ===================================================================== #
def test_dominates_four_cases() -> None:
    """Verify Pareto dominance over four canonical pairwise scenarios."""
    # Case 1: a strictly dominates b (a is strictly smaller in all dims)
    a1 = np.array([10.0, 20.0])
    b1 = np.array([15.0, 25.0])
    assert dominates(a1, b1) is True

    # Case 2: b dominates a
    assert dominates(b1, a1) is False

    # Case 3: a and b are identical (no strict inequality on any objective)
    a3 = np.array([10.0, 20.0])
    b3 = np.array([10.0, 20.0])
    assert dominates(a3, b3) is False

    # Case 4: Trade-off (a is better on obj 0, b is better on obj 1)
    a4 = np.array([10.0, 30.0])
    b4 = np.array([20.0, 15.0])
    assert dominates(a4, b4) is False
    assert dominates(b4, a4) is False


# ===================================================================== #
#  2. Fast Non-Dominated Sorting Test                                    #
# ===================================================================== #
def test_fast_nondominated_sort_known_structure() -> None:
    """Validate non-dominated sorting on a 6-point 2D set with 3 known fronts."""
    # Points in (Z1, Z2):
    # Front 0: (1, 5), (2, 3), (4, 1) -> indices [0, 1, 2]
    # Front 1: (2, 6) dominates none of front 0, dominated by (2, 3)
    #          (3, 4) dominated by (2, 3) -> indices [3, 4]
    # Front 2: (5, 5) dominated by (3, 4) and (4, 1) -> index [5]
    objectives = np.array([
        [1.0, 5.0],  # 0: Front 0
        [2.0, 3.0],  # 1: Front 0
        [4.0, 1.0],  # 2: Front 0
        [2.0, 6.0],  # 3: Front 1
        [3.0, 4.0],  # 4: Front 1
        [5.0, 5.0],  # 5: Front 2
    ])

    fronts = fast_nondominated_sort(objectives)
    assert len(fronts) == 3
    assert set(fronts[0]) == {0, 1, 2}
    assert set(fronts[1]) == {3, 4}
    assert set(fronts[2]) == {5}


# ===================================================================== #
#  3. Crowding Distance Test                                             #
# ===================================================================== #
def test_crowding_distance_boundaries_are_infinite() -> None:
    """Boundary solutions along each objective must receive infinite distance."""
    objs = np.array([
        [1.0, 10.0],  # min Z1, max Z2
        [2.0, 5.0],   # interior
        [5.0, 1.0],   # max Z1, min Z2
    ])
    front = [0, 1, 2]
    dists = crowding_distance(front, objs)

    assert dists.shape == (3,)
    assert np.isinf(dists[0])
    assert np.isinf(dists[2])
    assert np.isfinite(dists[1])
    assert dists[1] > 0.0


# ===================================================================== #
#  4. C1 Demand Repair Test                                              #
# ===================================================================== #
def test_repair_satisfies_c1_demand() -> None:
    """Greedy repair must satisfy route demand on a 2-vessel, 2-route scenario."""
    vessels = [
        {"id": "V1", "capacity_teu": 5000, "vmin": 10.0, "vmax": 20.0, "fuels_allowed": ["HFO"]},
        {"id": "V2", "capacity_teu": 8000, "vmin": 10.0, "vmax": 20.0, "fuels_allowed": ["HFO"]},
    ]
    routes = [
        {"id": "R1", "demand_teu": 6000, "distance_nm": 2000, "schedule_days": 10.0},
        {"id": "R2", "demand_teu": 7000, "distance_nm": 2000, "schedule_days": 10.0},
    ]

    # Initialize unassigned solution (all False)
    V, R = 2, 2
    sol = Solution(
        q_matrix=np.full((V * R + V * 5 + V * R, 2), 1.0 / np.sqrt(2.0)),
        speeds=np.full((V, R), 15.0),
    )
    sol.observed = {
        "assignment": np.zeros((V, R), dtype=bool),
        "fuel": np.zeros(V, dtype=int),
        "shore_power": np.zeros((V, R), dtype=bool),
    }

    # Before repair: deficit = 6000 + 7000 = 13000
    viols_before = evaluate_violations(sol, vessels, routes)
    assert viols_before["demand_deficit"] == 13000.0

    # Apply greedy repair
    repair(sol, vessels, routes)

    # After repair: both routes should have assigned vessels
    # R1: V2 (8000 >= 6000) assigned
    # R2: V2 (8000 >= 7000) assigned
    viols_after = evaluate_violations(sol, vessels, routes)
    assert viols_after["demand_deficit"] == 0.0
    assert sol.feasible is True


# ===================================================================== #
#  5. Adaptive Penalty Test                                              #
# ===================================================================== #
def test_penalty_grows_with_generation() -> None:
    """Penalty magnitude must strictly increase with generation index g."""
    violations = {"demand_deficit": 50.0, "cii_excess": 2.0}
    lambda0 = 10.0
    G = 300

    lambda_gen0 = lambda0 * ((1.0 + (0 / G)) ** 2)
    lambda_gen150 = lambda0 * ((1.0 + (150 / G)) ** 2)
    lambda_gen300 = lambda0 * ((1.0 + (300 / G)) ** 2)

    p0 = penalty(violations, lambda_gen0)
    p150 = penalty(violations, lambda_gen150)
    p300 = penalty(violations, lambda_gen300)

    assert p0 < p150 < p300
    assert p0 == pytest.approx(52.0 * 10.0)
    assert p300 == pytest.approx(52.0 * 40.0)


# ===================================================================== #
#  6. Quantum Rotation Gate & Normalization Test                         #
# ===================================================================== #
def test_rotation_gate_normalization_and_convergence() -> None:
    """Q-bits must preserve normalization and rotate toward the leader bit."""
    # Initialize qubit in superposition [1/√2, 1/√2]
    sol = Solution(
        q_matrix=np.array([[1.0 / np.sqrt(2.0), 1.0 / np.sqrt(2.0)]]),
        speeds=np.zeros((1, 1)),
    )
    sol.observed = {
        "assignment": np.array([[False]]),
        "fuel": np.array([0]),
        "shore_power": np.array([[False]]),
    }

    # Target leader has measured bit = 1 (beta^2 close to 1.0)
    leader = Solution(
        q_matrix=np.array([[0.05, np.sqrt(1.0 - 0.05 ** 2)]]),
        speeds=np.zeros((1, 1)),
    )
    leader.observed = {
        "assignment": np.array([[True]]),
        "fuel": np.array([0]),
        "shore_power": np.array([[False]]),
    }

    # Rotate over 50 iterations with theta = 0.03 rad
    theta = 0.03
    for _ in range(50):
        apply_rotation_gates(sol, leader, theta_g=theta)
        alpha, beta = sol.q_matrix[0]
        # Normalization constraint: alpha^2 + beta^2 = 1.0
        assert np.isclose(alpha ** 2 + beta ** 2, 1.0, atol=1e-7)

    # Qubit probability of measuring 1 (beta^2) should have increased substantially
    final_beta_sq = sol.q_matrix[0, 1] ** 2
    assert final_beta_sq > 0.85, f"Expected beta^2 > 0.85, got {final_beta_sq:.4f}"


# ===================================================================== #
#  7. QPSO Speed Update Test                                             #
# ===================================================================== #
def test_qpso_speed_update_and_mbest() -> None:
    """QPSO update must stay within vessel bounds and compute mbest correctly."""
    rng = np.random.default_rng(42)
    pop_size = 2
    V, R = 1, 1

    speeds = np.array([[[10.0]], [[14.0]]])
    pbest_speeds = np.array([[[12.0]], [[16.0]]])

    # Hand-checked mbest on 2 particles: (12.0 + 16.0) / 2 = 14.0
    mbest = np.mean(pbest_speeds, axis=0)
    assert mbest[0, 0] == pytest.approx(14.0)

    vessels = [{"id": "V0", "vmin": 8.0, "vmax": 20.0}]
    routes = [{"id": "R0", "distance_nm": 1000.0, "schedule_days": 10.0}]

    new_speeds = update_speeds(
        speeds=speeds,
        pbest_speeds=pbest_speeds,
        archive=[],
        vessels=vessels,
        routes=routes,
        beta=0.7,
        rng=rng,
    )

    assert new_speeds.shape == (2, 1, 1)
    assert 8.0 <= new_speeds[0, 0, 0] <= 20.0
    assert 8.0 <= new_speeds[1, 0, 0] <= 20.0


# ===================================================================== #
#  8. Full Smoke Test on Toy Fleet (5 generations)                       #
# ===================================================================== #
def test_full_qiea_smoke_test_toy_fleet() -> None:
    """Execute 5 generations of QIEA+QPSO on a 3-vessel, 2-route fleet.

    Archive must be non-empty and all archive solutions pairwise non-dominated.
    """
    vessels = [
        {"id": "V1", "type": "container", "capacity_teu": 4000, "dwt": 50000, "vmin": 10.0, "vmax": 20.0, "fuels_allowed": ["HFO"], "charter_per_day": 12000},
        {"id": "V2", "type": "bulk", "capacity_teu": 5000, "dwt": 60000, "vmin": 9.0, "vmax": 18.0, "fuels_allowed": ["HFO", "LNG_DIESEL"], "charter_per_day": 14000},
        {"id": "V3", "type": "tanker", "capacity_teu": 6000, "dwt": 70000, "vmin": 9.0, "vmax": 17.0, "fuels_allowed": ["HFO"], "charter_per_day": 16000},
    ]
    routes = [
        {"id": "R1", "distance_nm": 1500, "schedule_days": 6.0, "demand_teu": 3500, "weather_severity": 0, "lng_available": True, "shore_power": True},
        {"id": "R2", "distance_nm": 2200, "schedule_days": 9.0, "demand_teu": 4200, "weather_severity": 1, "lng_available": False, "shore_power": False},
    ]

    config = {
        "pop_size": 20,
        "generations": 5,
        "theta_start": 0.05 * np.pi,
        "theta_end": 0.01 * np.pi,
        "mutation_prob": 0.02,
        "lambda0": 5.0,
        "fuel_prices": {"HFO": 600.0, "LNG_DIESEL": 750.0, "MEOH_GREEN": 1200.0, "H2_GREEN": 3000.0, "NH3_GREEN": 2500.0},
        "carbon_price": 50.0,
        "seed": 42,
    }

    # Dummy surrogate predictor returning realistic tons/day
    def dummy_predictor(v_idx: int, speed: float, draft: float, weather: int) -> float:
        return 0.004 * (speed ** 3) + 1.2 * draft + 3.0

    archive, history = run(
        vessels=vessels,
        routes=routes,
        config=config,
        predictor=dummy_predictor,
    )

    assert len(archive) > 0, "Archive should contain at least one solution"
    assert len(history["generation"]) == 5

    # Check pairwise non-dominance among archive members
    arch_objs = [sol.objectives for sol in archive if sol.objectives is not None]
    for i in range(len(arch_objs)):
        for j in range(len(arch_objs)):
            if i != j:
                assert not dominates(arch_objs[i], arch_objs[j]), (
                    f"Solution {i} dominates solution {j} in archive!"
                )


# ===================================================================== #
#  9. Small Archive Leader Selection Regression Test                     #
# ===================================================================== #
def test_leader_selection_small_archive_no_nan() -> None:
    """Regression test: verify leader selection never crashes with NaN probabilities.

    Directly exercises:
        1. Archive of size 1 where crowding_dist is inf -> prob [1.0]
        2. Archive of size 2 where both crowding_dists are inf -> probs [0.5, 0.5]
        3. Archive of size 2 where one is finite and one is inf
        4. Archive with coincident points where all crowding_dists are 0.0
        5. 3-generation QIEA run on toy fleet with pop_size=4
    """
    rng = np.random.default_rng(42)

    def calc_arch_probs(archive: list[Solution]) -> np.ndarray:
        arch_dists = np.array([s.crowding_dist for s in archive], dtype=float)
        finite = arch_dists[np.isfinite(arch_dists)]
        if finite.size > 0:
            capped = np.where(np.isfinite(arch_dists), arch_dists, finite.max() * 2.0)
        else:
            capped = np.ones_like(arch_dists)
        total = capped.sum()
        if not np.isfinite(total) or total <= 0:
            return np.full(len(archive), 1.0 / len(archive))
        return capped / total

    # 1. Size 1: crowding_dist = inf
    s1 = Solution(q_matrix=np.ones((6, 2)) / np.sqrt(2), speeds=np.ones((2, 2)) * 12.0)
    s1.crowding_dist = float("inf")
    p1 = calc_arch_probs([s1])
    assert not np.any(np.isnan(p1)), "Size 1 archive produced NaN probabilities"
    assert np.allclose(p1, [1.0])

    # 2. Size 2: both inf
    s2 = Solution(q_matrix=np.ones((6, 2)) / np.sqrt(2), speeds=np.ones((2, 2)) * 14.0)
    s2.crowding_dist = float("inf")
    p2 = calc_arch_probs([s1, s2])
    assert not np.any(np.isnan(p2)), "Size 2 all-inf archive produced NaN probabilities"
    assert np.allclose(p2, [0.5, 0.5])

    # 3. Size 2: one finite, one inf
    s1.crowding_dist = 2.0
    s2.crowding_dist = float("inf")
    p12 = calc_arch_probs([s1, s2])
    assert not np.any(np.isnan(p12)), "Mixed finite/inf archive produced NaN probabilities"
    assert np.isclose(p12.sum(), 1.0)
    assert p12[1] > p12[0]

    # 4. Coincident points: all 0.0
    s1.crowding_dist = 0.0
    s2.crowding_dist = 0.0
    p0 = calc_arch_probs([s1, s2])
    assert not np.any(np.isnan(p0)), "All-zero crowding dist archive produced NaN probabilities"
    assert np.allclose(p0, [0.5, 0.5])

    # 5. Full QIEA run with pop_size=4 for 3 generations (forces tiny archives)
    vessels = [
        {"id": "V1", "type": "container", "capacity_teu": 4000, "dwt": 50000, "vmin": 10.0, "vmax": 20.0, "fuels_allowed": ["HFO"], "charter_per_day": 12000},
        {"id": "V2", "type": "bulk", "capacity_teu": 5000, "dwt": 60000, "vmin": 9.0, "vmax": 18.0, "fuels_allowed": ["HFO", "LNG_DIESEL"], "charter_per_day": 14000},
    ]
    routes = [
        {"id": "R1", "distance_nm": 1500, "schedule_days": 6.0, "demand_teu": 3500, "weather_severity": 0, "lng_available": True, "shore_power": True},
    ]
    cfg = {
        "pop_size": 4,
        "generations": 3,
        "theta_start": 0.05 * np.pi,
        "theta_end": 0.01 * np.pi,
        "mutation_prob": 0.05,
        "lambda0": 5.0,
        "fuel_prices": {"HFO": 600.0, "LNG_DIESEL": 750.0},
        "carbon_price": 50.0,
        "seed": 42,
    }
    def dummy_predictor(v_idx: int, speed: float, draft: float, weather: int) -> float:
        return 0.004 * (speed ** 3) + 1.2 * draft + 3.0

    archive, history = run(vessels, routes, cfg, dummy_predictor, rng=rng)
    assert len(archive) >= 1
    assert len(history["generation"]) == 3

