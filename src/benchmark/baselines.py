"""Classical multi-objective baseline optimizers for fair benchmarking against QGreenFleet.

Implements:
    1. GeneticAlgorithm (NSGA-II based real-binary hybrid GA)
    2. MOPSO (Multi-Objective Particle Swarm Optimization with sigmoid binary mapping)
    3. SimulatedAnnealing (Sequential scalarized SA with identical total evaluation budget)

All baselines strictly share the exact same repair(), evaluate_objectives(),
and update_archive() operators to ensure fair, unbiased comparison.

References:
    - Deb, K. et al. (2002). NSGA-II. IEEE Trans. Evolutionary Computation.
    - Coello Coello, C. A. et al. (2004). Handling multiple objectives with particle swarm optimization.
    - docs/algorithms.md §Benchmarking
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from src.emissions.factors import OPTIMIZER_FUELS
from src.optimization.constraints import evaluate_violations, penalty, repair
from src.optimization.individual import Solution, init_population, observe
from src.optimization.objectives import evaluate_objectives
from src.optimization.pareto import (
    crowding_distance,
    dominates,
    fast_nondominated_sort,
    update_archive,
)
from src.optimization.qiea import compute_hypervolume


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    """Stable sigmoid activation function."""
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20.0, 20.0)))


def _decode_bits_into_solution(
    sol: Solution,
    bits: np.ndarray,
    V: int,
    R: int,
    P: int,
    n_fuels: int = len(OPTIMIZER_FUELS),
) -> None:
    """Decode raw flat bitstring into structured observed decisions."""
    assign_end = V * R
    fuel_end = assign_end + V * n_fuels
    sp_end = fuel_end + V * P

    assignment_bits = bits[:assign_end].reshape(V, R).astype(bool)

    fuel_bits = bits[assign_end:fuel_end].reshape(V, n_fuels)
    fuel_indices = np.zeros(V, dtype=int)
    for v in range(V):
        block = fuel_bits[v]
        if np.any(block > 0):
            fuel_indices[v] = int(np.argmax(block))
        else:
            fuel_indices[v] = 0

    if len(bits) >= sp_end:
        sp_bits = bits[fuel_end:sp_end].reshape(V, P).astype(bool)
    else:
        sp_bits = np.zeros((V, P), dtype=bool)

    sol.observed = {
        "bits": bits.copy(),
        "assignment": assignment_bits,
        "fuel": fuel_indices,
        "shore_power": sp_bits,
    }


def _binary_tournament_selection(
    population: list[Solution],
    rng: np.random.Generator,
) -> Solution:
    """Binary tournament selection preferring dominance and crowding distance."""
    i1, i2 = rng.integers(0, len(population), size=2)
    s1, s2 = population[i1], population[i2]

    if s1.objectives is not None and s2.objectives is not None:
        if dominates(s1.objectives, s2.objectives):
            return s1
        if dominates(s2.objectives, s1.objectives):
            return s2
        if s1.rank < s2.rank:
            return s1
        if s2.rank < s1.rank:
            return s2
        if s1.crowding_dist > s2.crowding_dist:
            return s1
        if s2.crowding_dist > s1.crowding_dist:
            return s2

    return s1 if rng.random() < 0.5 else s2


# ===================================================================== #
#  1. Genetic Algorithm (NSGA-II) Baseline                               #
# ===================================================================== #
class GeneticAlgorithm:
    """Multi-Objective Genetic Algorithm with NSGA-II elitist selection."""

    @staticmethod
    def run(
        vessels: Sequence[Any],
        routes: Sequence[Any],
        config: dict[str, Any],
        predictor: Any,
        rng: np.random.Generator | None = None,
    ) -> tuple[list[Solution], dict[str, list[Any]]]:
        """Execute GA with identical evaluation budget to QIEA."""
        seed = int(config.get("seed", 42))
        if rng is None:
            rng = np.random.default_rng(seed)

        pop_size = int(config.get("pop_size", 200))
        generations = int(config.get("generations", 300))
        lambda0 = float(config.get("lambda0", 10.0))
        fuel_prices = config.get("fuel_prices", {})
        carbon_price = float(config.get("carbon_price", 0.0))
        archive_max = int(config.get("archive_max", 100))

        V = len(vessels)
        R = len(routes)
        P = R
        F = OPTIMIZER_FUELS
        n_fuels = len(F)
        n_bits = (V * R) + (V * n_fuels) + (V * P)

        # Initial random population
        population = init_population(pop_size, V, R, P, n_fuels, rng)
        for sol in population:
            # Random initial bits
            bits = rng.integers(0, 2, size=n_bits)
            _decode_bits_into_solution(sol, bits, V, R, P, n_fuels)
            repair(sol, vessels, routes, fuels=F)
            viols = evaluate_violations(sol, vessels, routes, fuels=F)
            pen = penalty(viols, lambda_g=lambda0)
            evaluate_objectives(sol, vessels, routes, predictor, fuel_prices, carbon_price, pen)

        archive = update_archive([], population, max_size=archive_max)
        history: dict[str, list[Any]] = {
            "generation": [],
            "hypervolume": [],
            "feasible_count": [],
        }

        # Main generation loop
        for g in range(generations):
            lambda_g = lambda0 * ((1.0 + (g / generations)) ** 2)

            # Assign Pareto ranks and crowding distances for tournament selection
            objs = np.array([s.objectives for s in population if s.objectives is not None])
            fronts = fast_nondominated_sort(objs)
            for r_idx, front in enumerate(fronts):
                dists = crowding_distance(front, objs)
                for f_pos, idx in enumerate(front):
                    population[idx].rank = r_idx
                    population[idx].crowding_dist = dists[f_pos]

            # Generate offspring population
            offspring: list[Solution] = []
            for _ in range(pop_size // 2):
                p1 = _binary_tournament_selection(population, rng)
                p2 = _binary_tournament_selection(population, rng)

                b1 = p1.observed["bits"].copy()
                b2 = p2.observed["bits"].copy()
                s1 = p1.speeds.copy()
                s2 = p2.speeds.copy()

                # Crossover (prob 0.9)
                if rng.random() < 0.9 and n_bits > 1:
                    cx_point = rng.integers(1, n_bits)
                    b1[cx_point:], b2[cx_point:] = b2[cx_point:].copy(), b1[cx_point:].copy()

                    gamma = rng.uniform(0.0, 1.0)
                    s1_cx = gamma * s1 + (1.0 - gamma) * s2
                    s2_cx = (1.0 - gamma) * s1 + gamma * s2
                    s1, s2 = s1_cx, s2_cx

                # Mutation (bit flip prob 1/n_bits; Gaussian on speeds)
                mut_mask1 = rng.random(n_bits) < (1.0 / n_bits)
                b1[mut_mask1] = 1 - b1[mut_mask1]
                mut_mask2 = rng.random(n_bits) < (1.0 / n_bits)
                b2[mut_mask2] = 1 - b2[mut_mask2]

                s1 += rng.normal(0.0, 0.5, size=(V, R))
                s2 += rng.normal(0.0, 0.5, size=(V, R))

                for b, s in [(b1, s1), (b2, s2)]:
                    c_sol = Solution(
                        q_matrix=np.full((n_bits, 2), 1.0 / np.sqrt(2.0)),
                        speeds=s,
                    )
                    _decode_bits_into_solution(c_sol, b, V, R, P, n_fuels)
                    repair(c_sol, vessels, routes, fuels=F)
                    viols = evaluate_violations(c_sol, vessels, routes, fuels=F)
                    pen = penalty(viols, lambda_g=lambda_g)
                    evaluate_objectives(c_sol, vessels, routes, predictor, fuel_prices, carbon_price, pen)
                    offspring.append(c_sol)

            # Survivor selection: combine parent + offspring (2N) -> select top N
            combined = population + offspring
            comb_objs = np.array([s.objectives for s in combined if s.objectives is not None])
            comb_fronts = fast_nondominated_sort(comb_objs)

            new_pop: list[Solution] = []
            for front in comb_fronts:
                if len(new_pop) + len(front) <= pop_size:
                    for idx in front:
                        new_pop.append(combined[idx])
                else:
                    # Truncate by crowding distance
                    dists = crowding_distance(front, comb_objs)
                    finite_d = np.where(np.isinf(dists), 1e15, dists)
                    order = np.argsort(-finite_d)
                    needed = pop_size - len(new_pop)
                    for k in order[:needed]:
                        new_pop.append(combined[front[k]])
                    break

            population = new_pop
            archive = update_archive(archive, population, max_size=archive_max)

            hv = compute_hypervolume(archive)
            feas_cnt = sum(1 for s in population if s.feasible)
            history["generation"].append(g)
            history["hypervolume"].append(hv)
            history["feasible_count"].append(feas_cnt)

        return archive, history


# ===================================================================== #
#  2. Multi-Objective Particle Swarm Optimization (MOPSO) Baseline       #
# ===================================================================== #
class MOPSO:
    """Multi-Objective Particle Swarm Optimization with sigmoid binary mapping."""

    @staticmethod
    def run(
        vessels: Sequence[Any],
        routes: Sequence[Any],
        config: dict[str, Any],
        predictor: Any,
        rng: np.random.Generator | None = None,
    ) -> tuple[list[Solution], dict[str, list[Any]]]:
        """Execute MOPSO with identical function evaluation budget."""
        seed = int(config.get("seed", 42))
        if rng is None:
            rng = np.random.default_rng(seed)

        pop_size = int(config.get("pop_size", 200))
        generations = int(config.get("generations", 300))
        lambda0 = float(config.get("lambda0", 10.0))
        fuel_prices = config.get("fuel_prices", {})
        carbon_price = float(config.get("carbon_price", 0.0))
        archive_max = int(config.get("archive_max", 100))

        V = len(vessels)
        R = len(routes)
        P = R
        F = OPTIMIZER_FUELS
        n_fuels = len(F)
        n_bits = (V * R) + (V * n_fuels) + (V * P)

        w = 0.7
        c1 = 1.5
        c2 = 1.5

        # Initialize particles and velocities
        population = init_population(pop_size, V, R, P, n_fuels, rng)
        v_binary = rng.uniform(-1.0, 1.0, size=(pop_size, n_bits))
        v_speeds = rng.uniform(-1.0, 1.0, size=(pop_size, V, R))

        pbest_bits = np.zeros((pop_size, n_bits), dtype=int)
        pbest_speeds = np.array([s.speeds.copy() for s in population])
        pbest_objs = np.full((pop_size, 3), np.inf)

        for i, sol in enumerate(population):
            bits = (rng.random(n_bits) < 0.5).astype(int)
            _decode_bits_into_solution(sol, bits, V, R, P, n_fuels)
            repair(sol, vessels, routes, fuels=F)
            viols = evaluate_violations(sol, vessels, routes, fuels=F)
            pen = penalty(viols, lambda_g=lambda0)
            evaluate_objectives(sol, vessels, routes, predictor, fuel_prices, carbon_price, pen)

            pbest_bits[i] = bits.copy()
            pbest_speeds[i] = sol.speeds.copy()
            pbest_objs[i] = sol.objectives.copy()

        archive = update_archive([], population, max_size=archive_max)
        history: dict[str, list[Any]] = {
            "generation": [],
            "hypervolume": [],
            "feasible_count": [],
        }

        for g in range(generations):
            lambda_g = lambda0 * ((1.0 + (g / generations)) ** 2)

            for i, sol in enumerate(population):
                # Leader selection from archive weighted by crowding distance
                if archive:
                    arch_dists = np.array([s.crowding_dist for s in archive], dtype=float)
                    finite = arch_dists[np.isfinite(arch_dists)]
                    if finite.size > 0:
                        capped = np.where(np.isfinite(arch_dists), arch_dists, finite.max() * 2.0)
                    else:
                        capped = np.ones_like(arch_dists)
                    total = capped.sum()
                    if not np.isfinite(total) or total <= 0:
                        probs = np.full(len(archive), 1.0 / len(archive))
                    else:
                        probs = capped / total
                    leader = rng.choice(archive, p=probs)
                    leader_bits = leader.observed.get("bits", pbest_bits[i])
                    leader_speeds = leader.speeds
                else:
                    leader_bits = pbest_bits[i]
                    leader_speeds = pbest_speeds[i]

                # Update binary velocities & sample bits via sigmoid
                r1 = rng.uniform(0.0, 1.0, size=n_bits)
                r2 = rng.uniform(0.0, 1.0, size=n_bits)
                curr_bits = sol.observed["bits"]

                v_binary[i] = (
                    w * v_binary[i]
                    + c1 * r1 * (pbest_bits[i] - curr_bits)
                    + c2 * r2 * (leader_bits - curr_bits)
                )
                v_binary[i] = np.clip(v_binary[i], -6.0, 6.0)

                sig_probs = _sigmoid(v_binary[i])
                new_bits = (rng.random(n_bits) < sig_probs).astype(int)

                # Update continuous speed velocities
                r1_s = rng.uniform(0.0, 1.0, size=(V, R))
                r2_s = rng.uniform(0.0, 1.0, size=(V, R))

                v_speeds[i] = (
                    w * v_speeds[i]
                    + c1 * r1_s * (pbest_speeds[i] - sol.speeds)
                    + c2 * r2_s * (leader_speeds - sol.speeds)
                )
                v_speeds[i] = np.clip(v_speeds[i], -3.0, 3.0)
                sol.speeds += v_speeds[i]

                # Decode, repair, and evaluate
                _decode_bits_into_solution(sol, new_bits, V, R, P, n_fuels)
                repair(sol, vessels, routes, fuels=F)
                viols = evaluate_violations(sol, vessels, routes, fuels=F)
                pen = penalty(viols, lambda_g=lambda_g)
                evaluate_objectives(sol, vessels, routes, predictor, fuel_prices, carbon_price, pen)

                # Update pbest if new solution dominates
                if dominates(sol.objectives, pbest_objs[i]):
                    pbest_objs[i] = sol.objectives.copy()
                    pbest_bits[i] = new_bits.copy()
                    pbest_speeds[i] = sol.speeds.copy()

            archive = update_archive(archive, population, max_size=archive_max)
            hv = compute_hypervolume(archive)
            feas_cnt = sum(1 for s in population if s.feasible)
            history["generation"].append(g)
            history["hypervolume"].append(hv)
            history["feasible_count"].append(feas_cnt)

        return archive, history


# ===================================================================== #
#  3. Simulated Annealing (SA) Baseline                                  #
# ===================================================================== #
class SimulatedAnnealing:
    """Sequential Simulated Annealing baseline matching total evaluation budget."""

    @staticmethod
    def run(
        vessels: Sequence[Any],
        routes: Sequence[Any],
        config: dict[str, Any],
        predictor: Any,
        rng: np.random.Generator | None = None,
    ) -> tuple[list[Solution], dict[str, list[Any]]]:
        """Execute SA with total_evals = pop_size * generations function calls."""
        seed = int(config.get("seed", 42))
        if rng is None:
            rng = np.random.default_rng(seed)

        pop_size = int(config.get("pop_size", 200))
        generations = int(config.get("generations", 300))
        total_evals = pop_size * generations

        lambda0 = float(config.get("lambda0", 10.0))
        fuel_prices = config.get("fuel_prices", {})
        carbon_price = float(config.get("carbon_price", 0.0))
        archive_max = int(config.get("archive_max", 100))

        V = len(vessels)
        R = len(routes)
        P = R
        F = OPTIMIZER_FUELS
        n_fuels = len(F)
        n_bits = (V * R) + (V * n_fuels) + (V * P)

        T0 = 1000.0
        T_min = 0.1
        cooling_rate = (T_min / T0) ** (1.0 / max(1, total_evals))
        T = T0

        # Initial solution
        curr_sol = init_population(1, V, R, P, n_fuels, rng)[0]
        curr_bits = rng.integers(0, 2, size=n_bits)
        _decode_bits_into_solution(curr_sol, curr_bits, V, R, P, n_fuels)
        repair(curr_sol, vessels, routes, fuels=F)
        viols = evaluate_violations(curr_sol, vessels, routes, fuels=F)
        pen = penalty(viols, lambda_g=lambda0)
        evaluate_objectives(curr_sol, vessels, routes, predictor, fuel_prices, carbon_price, pen)

        def scalarize(objs: np.ndarray) -> float:
            # Weighted-sum scalarization Z1 + 0.01*Z2 + Z3 (normalized scale)
            return float((objs[0] / 1e7) + (0.01 * objs[1] / 5e4) + (objs[2] / 2e7))

        curr_cost = scalarize(curr_sol.objectives)
        best_sol = curr_sol
        archive = [curr_sol]

        history: dict[str, list[Any]] = {
            "generation": [],
            "hypervolume": [],
            "feasible_count": [],
        }

        # Sequential evaluation loop matching identical budget
        eval_count = 0
        gen_idx = 0

        for step in range(total_evals):
            lambda_g = lambda0 * ((1.0 + (step / total_evals)) ** 2)

            # Neighbor operator: flip 3 random bits + perturb 2 speeds
            neighbor_bits = curr_sol.observed["bits"].copy()
            flip_indices = rng.choice(n_bits, size=min(3, n_bits), replace=False)
            neighbor_bits[flip_indices] = 1 - neighbor_bits[flip_indices]

            neighbor_speeds = curr_sol.speeds.copy()
            v_pick = rng.integers(0, V, size=2)
            r_pick = rng.integers(0, R, size=2)
            for v, r in zip(v_pick, r_pick):
                neighbor_speeds[v, r] += rng.normal(0.0, 1.0)

            cand_sol = Solution(
                q_matrix=curr_sol.q_matrix.copy(),
                speeds=neighbor_speeds,
            )
            _decode_bits_into_solution(cand_sol, neighbor_bits, V, R, P, n_fuels)
            repair(cand_sol, vessels, routes, fuels=F)
            cand_viols = evaluate_violations(cand_sol, vessels, routes, fuels=F)
            cand_pen = penalty(cand_viols, lambda_g=lambda_g)
            evaluate_objectives(cand_sol, vessels, routes, predictor, fuel_prices, carbon_price, cand_pen)

            cand_cost = scalarize(cand_sol.objectives)
            delta = cand_cost - curr_cost

            # Metropolis acceptance
            if delta <= 0 or rng.random() < np.exp(-delta / max(1e-4, T)):
                curr_sol = cand_sol
                curr_cost = cand_cost
                archive = update_archive(archive, [cand_sol], max_size=archive_max)

            T = max(T_min, T * cooling_rate)
            eval_count += 1

            # Log generational snapshot every pop_size evaluations
            if eval_count % pop_size == 0 or step == total_evals - 1:
                hv = compute_hypervolume(archive)
                history["generation"].append(gen_idx)
                history["hypervolume"].append(hv)
                history["feasible_count"].append(1 if curr_sol.feasible else 0)
                gen_idx += 1

        return archive, history
