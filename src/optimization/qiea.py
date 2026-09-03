"""Quantum-Inspired Evolutionary Algorithm (QIEA) coupled with QPSO for green fleet deployment.

Orchestrates population observation, greedy repair, multi-objective evaluation,
NSGA-II Pareto ranking, Han & Kim quantum rotation gate updates, quantum mutation,
migration, and QPSO cruising speed updates.

References:
    - Han, K. H., & Kim, J. H. (2002). Quantum-inspired evolutionary algorithm for
      a class of combinatorial optimization problems. IEEE Trans. Evolutionary Computation.
    - docs/algorithms.md §1 QIEA & §3 Hybrid coupling
    - docs/mathematical-model.md §Objectives & §Constraints
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import numpy as np

from src.emissions.factors import OPTIMIZER_FUELS
from src.optimization.constraints import evaluate_violations, penalty, repair
from src.optimization.individual import Solution, init_population, observe
from src.optimization.objectives import evaluate_objectives
from src.optimization.pareto import dominates, fast_nondominated_sort, update_archive
from src.optimization.qpso import update_speeds


def compute_hypervolume(
    archive: list[Solution],
    reference_point: np.ndarray | None = None,
) -> float:
    """Compute hypervolume metric for the non-dominated archive.

    Uses normalized coordinate space relative to the empirical nadir point.

    Args:
        archive: Non-dominated Pareto archive.
        reference_point: Upper reference bounding box point.

    Returns:
        Scalar hypervolume metric.
    """
    valid = [s for s in archive if s.objectives is not None]
    if not valid:
        return 0.0

    objs = np.array([s.objectives for s in valid])
    if reference_point is None:
        ref = 1.1 * np.max(objs, axis=0)
    else:
        ref = reference_point

    # Ensure ref strictly dominates all points
    ref = np.maximum(ref, np.max(objs, axis=0) * 1.01 + 1.0)
    ideal = np.min(objs, axis=0)

    spread = np.maximum(1e-6, ref - ideal)
    norm_objs = (objs - ideal) / spread

    # Approximate 3D hypervolume via Monte Carlo sampling (5000 points)
    # fast and exact in expectation
    rng = np.random.default_rng(123)
    samples = rng.uniform(0.0, 1.0, size=(5000, objs.shape[1]))

    # A sample is dominated if it is >= at least one solution in all dimensions
    is_dominated = np.zeros(len(samples), dtype=bool)
    for p in norm_objs:
        p_dominates_sample = np.all(samples >= p, axis=1)
        is_dominated |= p_dominates_sample

    return float(np.mean(is_dominated))


def _extract_bits(sol: Solution) -> np.ndarray:
    """Extract flat observed bit array corresponding to q_matrix rows."""
    total_q = sol.q_matrix.shape[0]
    if "bits" in sol.observed:
        b = np.asarray(sol.observed["bits"], dtype=int).ravel()
        if len(b) == total_q:
            return b

    if "assignment" in sol.observed:
        a = np.asarray(sol.observed["assignment"], dtype=int).ravel()
        if len(a) == total_q:
            return a

    parts: list[np.ndarray] = []
    if "assignment" in sol.observed:
        parts.append(np.asarray(sol.observed["assignment"], dtype=int).ravel())
    if "fuel" in sol.observed:
        parts.append(np.asarray(sol.observed["fuel"], dtype=int).ravel())
    if "shore_power" in sol.observed:
        parts.append(np.asarray(sol.observed["shore_power"], dtype=int).ravel())

    if parts:
        cat = np.concatenate(parts)
        if len(cat) >= total_q:
            return cat[:total_q]

    return (sol.q_matrix[:, 1] ** 2 > 0.5).astype(int)


def apply_rotation_gates(
    sol: Solution,
    leader: Solution,
    theta_g: float,
) -> None:
    """Apply quantum rotation gate to each qubit toward the archive leader bit.

    Direction lookup table from Han & Kim (2002), Table 1:
        Rotate state vector [alpha, beta] by Delta_theta:
        [alpha', beta']^T = [[cos(dt), -sin(dt)], [sin(dt), cos(dt)]] * [alpha, beta]^T
        followed by normalization to preserve alpha^2 + beta^2 = 1.

    Args:
        sol: Candidate solution whose q_matrix will be updated.
        leader: Reference non-dominated archive leader.
        theta_g: Magnitude of rotation angle for current generation.
    """
    total_q = sol.q_matrix.shape[0]
    x_bits = _extract_bits(sol)
    b_bits = _extract_bits(leader)

    alpha = sol.q_matrix[:, 0]
    beta = sol.q_matrix[:, 1]
    prod = alpha * beta

    delta_theta = np.zeros(total_q, dtype=float)

    # Case 1: x_i = 0, b_i = 1 -> increase |beta|
    mask_01 = (x_bits == 0) & (b_bits == 1)
    d_01 = np.where(prod > 0, 1.0, np.where(prod < 0, -1.0, np.where(beta == 0, 1.0, 0.0)))
    delta_theta[mask_01] = theta_g * d_01[mask_01]

    # Case 2: x_i = 1, b_i = 0 -> decrease |beta|
    mask_10 = (x_bits == 1) & (b_bits == 0)
    d_10 = np.where(prod > 0, -1.0, np.where(prod < 0, 1.0, np.where(alpha == 0, -1.0, 0.0)))
    delta_theta[mask_10] = theta_g * d_10[mask_10]

    # Rotate [alpha, beta]
    cos_t = np.cos(delta_theta)
    sin_t = np.sin(delta_theta)

    new_alpha = cos_t * alpha - sin_t * beta
    new_beta = sin_t * alpha + cos_t * beta

    # Strict quantum normalization: alpha^2 + beta^2 = 1.0
    norm = np.sqrt(new_alpha ** 2 + new_beta ** 2)
    norm = np.where(norm < 1e-12, 1.0, norm)

    sol.q_matrix[:, 0] = new_alpha / norm
    sol.q_matrix[:, 1] = new_beta / norm


def mutate_qbits(
    sol: Solution,
    mutation_prob: float,
    rng: np.random.Generator,
) -> None:
    """Apply quantum mutation by resetting qubits to equal superposition [1/√2, 1/√2]."""
    total_q = sol.q_matrix.shape[0]
    mut_mask = rng.random(total_q) < mutation_prob
    if np.any(mut_mask):
        sol.q_matrix[mut_mask, 0] = 1.0 / np.sqrt(2.0)
        sol.q_matrix[mut_mask, 1] = 1.0 / np.sqrt(2.0)


def run(
    vessels: Sequence[Any],
    routes: Sequence[Any],
    config: dict[str, Any],
    predictor: Any,
    rng: np.random.Generator | None = None,
    progress_callback: Callable[[int, int, int, float, int], None] | None = None,
) -> tuple[list[Solution], dict[str, list[Any]]]:
    """Execute the full hybrid QIEA + QPSO multi-objective fleet optimization.

    Args:
        vessels: Fleet vessel catalog.
        routes: Commercial shipping routes.
        config: Optimization configuration dictionary.
        predictor: FuelPredictor inference instance.
        rng: Seeded numpy Generator.
        progress_callback: Optional progress reporter (gen, max_gen, archive_size, hv, feasible).

    Returns:
        Tuple of (final_pareto_archive, convergence_history_dict).
    """
    seed = int(config.get("seed", 42))
    if rng is None:
        rng = np.random.default_rng(seed)

    pop_size = int(config.get("pop_size", 200))
    generations = int(config.get("generations", 300))
    theta_start = float(config.get("theta_start", 0.05 * np.pi))
    theta_end = float(config.get("theta_end", 0.005 * np.pi))
    mutation_prob = float(config.get("mutation_prob", 0.02))
    lambda0 = float(config.get("lambda0", 10.0))
    fuel_prices = config.get("fuel_prices", {
        "HFO": 650.0,
        "LNG_DIESEL": 800.0,
        "MEOH_GREEN": 1200.0,
        "H2_GREEN": 3000.0,
        "NH3_GREEN": 2500.0,
    })
    carbon_price = float(config.get("carbon_price", 0.0))
    archive_max = int(config.get("archive_max", 100))

    V = len(vessels)
    R = len(routes)
    P = R  # Each route destination represents a port
    F = OPTIMIZER_FUELS

    # Initialize hybrid QIEA + QPSO population
    population = init_population(
        pop_size=pop_size,
        V=V,
        R=R,
        P=P,
        F=len(F),
        rng=rng,
    )

    # Track personal bests for continuous speeds
    pbest_speeds = np.array([sol.speeds.copy() for sol in population])
    pbest_objs = np.full((pop_size, 3), np.inf)

    archive: list[Solution] = []
    history: dict[str, list[Any]] = {
        "generation": [],
        "hypervolume": [],
        "feasible_count": [],
        "best_Z1": [],
        "best_Z2": [],
        "best_Z3": [],
    }

    for g in range(generations):
        # Linear parameter schedules
        theta_g = theta_start - (g / max(1, generations - 1)) * (theta_start - theta_end)
        beta_g = 1.0 - (g / max(1, generations - 1)) * (1.0 - 0.4)
        lambda_g = lambda0 * ((1.0 + (g / generations)) ** 2)

        feasible_count = 0

        # 1. Observe and repair discrete decisions
        for i, sol in enumerate(population):
            observe(sol, rng, n_fuels=len(F), n_ports=P)
            repair(sol, vessels, routes, fuels=F)

            # 2. Evaluate operational constraints
            viols = evaluate_violations(sol, vessels, routes, fuels=F)
            if sol.feasible:
                feasible_count += 1

            pen = penalty(viols, lambda_g=lambda_g)

            # 3. Evaluate objectives with added penalty
            evaluate_objectives(
                sol=sol,
                vessels=vessels,
                routes=routes,
                predictor=predictor,
                fuel_prices=fuel_prices,
                carbon_price=carbon_price,
                penalty_val=pen,
            )

            # Update personal best if newly evaluated dominates previous pbest
            if dominates(sol.objectives, pbest_objs[i]):
                pbest_objs[i] = sol.objectives.copy()
                pbest_speeds[i] = sol.speeds.copy()

        # 4. Update Pareto archive
        archive = update_archive(archive, population, max_size=archive_max)

        # 5. QIEA quantum rotation gate updates toward archive leaders
        # Crowding-weighted selection: prefer leaders with high crowding distance for diversity.
        # Guards against NaN from inf/inf (boundary solutions) or 0/0 (coincident points).
        if archive:
            arch_dists = np.array([s.crowding_dist for s in archive], dtype=float)
            finite = arch_dists[np.isfinite(arch_dists)]
            if finite.size > 0:
                capped = np.where(np.isfinite(arch_dists), arch_dists, finite.max() * 2.0)
            else:
                capped = np.ones_like(arch_dists)
            total = capped.sum()
            if not np.isfinite(total) or total <= 0:
                arch_probs = np.full(len(archive), 1.0 / len(archive))
            else:
                arch_probs = capped / total
            for sol in population:
                leader_idx = rng.choice(len(archive), p=arch_probs)
                leader = archive[leader_idx]
                apply_rotation_gates(sol, leader, theta_g)
                mutate_qbits(sol, mutation_prob, rng)

        # 6. Periodic migration (every 25 generations: reseed worst 10% from archive)
        if g > 0 and g % 25 == 0 and archive:
            n_reseed = max(1, int(pop_size * 0.10))
            # Sort population by total objective magnitude
            pop_scores = [np.sum(s.objectives) if s.objectives is not None else 1e9 for s in population]
            worst_indices = np.argsort(-np.array(pop_scores))[:n_reseed]

            for w_idx in worst_indices:
                donor = rng.choice(archive)
                population[w_idx].q_matrix = donor.q_matrix.copy()
                population[w_idx].speeds = donor.speeds.copy()
                mutate_qbits(population[w_idx], mutation_prob=0.05, rng=rng)

        # 7. QPSO continuous speed update
        curr_speeds = np.array([sol.speeds for sol in population])
        new_speeds = update_speeds(
            speeds=curr_speeds,
            pbest_speeds=pbest_speeds,
            archive=archive,
            vessels=vessels,
            routes=routes,
            beta=beta_g,
            rng=rng,
        )
        for i in range(pop_size):
            population[i].speeds = new_speeds[i]

        # Metric logging
        hv = compute_hypervolume(archive)
        history["generation"].append(g)
        history["hypervolume"].append(hv)
        history["feasible_count"].append(feasible_count)

        if archive:
            arch_objs = np.array([s.objectives for s in archive if s.objectives is not None])
            history["best_Z1"].append(float(np.min(arch_objs[:, 0])))
            history["best_Z2"].append(float(np.min(arch_objs[:, 1])))
            history["best_Z3"].append(float(np.min(arch_objs[:, 2])))
        else:
            history["best_Z1"].append(0.0)
            history["best_Z2"].append(0.0)
            history["best_Z3"].append(0.0)

        if progress_callback is not None:
            progress_callback(g + 1, generations, len(archive), hv, feasible_count)

    # Infeasible scenario fallback
    if not archive:
        print("[WARNING] No feasible solutions found in archive; returning best penalty population solution.")
        best_pop = min(population, key=lambda s: np.sum(s.objectives) if s.objectives is not None else 1e9)
        archive = [best_pop]

    return archive, history

    return archive, history
