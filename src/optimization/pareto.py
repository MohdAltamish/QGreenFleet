"""Non-dominated Pareto ranking, crowding distance, and archive management.

Implements standard NSGA-II Pareto sorting and diversity-preserving archiving.

References:
    - Deb, K. et al. (2002). A fast and elitist multiobjective genetic algorithm: NSGA-II.
      IEEE Transactions on Evolutionary Computation, 6(2), 182-197.
    - docs/algorithms.md §1 Loop (Nondominated sort + crowding)
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from src.optimization.individual import Solution


def dominates(a: np.ndarray, b: np.ndarray) -> bool:
    """Check Pareto dominance: True if vector a dominates vector b.

    a dominates b if:
        for all objectives k: a[k] <= b[k]
        and for at least one j: a[j] < b[j] (strict inequality)

    Args:
        a: First objective vector.
        b: Second objective vector.

    Returns:
        True if a dominates b, False otherwise.
    """
    a_arr = np.asarray(a)
    b_arr = np.asarray(b)
    return bool(np.all(a_arr <= b_arr) and np.any(a_arr < b_arr))


def fast_nondominated_sort(objectives: np.ndarray) -> list[list[int]]:
    """Execute Deb's O(M*N^2) fast non-dominated sorting.

    Args:
        objectives: (N, M) array of minimization objective values.

    Returns:
        List of fronts where each front is a list of solution row indices.
        Front 0 is the non-dominated Pareto front.
    """
    n_solutions = objectives.shape[0]
    if n_solutions == 0:
        return []

    # S[p]: set of solutions dominated by p
    # n[p]: domination count (number of solutions that dominate p)
    S: list[list[int]] = [[] for _ in range(n_solutions)]
    n: list[int] = [0] * n_solutions
    fronts: list[list[int]] = [[]]

    for p in range(n_solutions):
        obj_p = objectives[p]
        for q in range(n_solutions):
            if p == q:
                continue
            obj_q = objectives[q]
            if dominates(obj_p, obj_q):
                S[p].append(q)
            elif dominates(obj_q, obj_p):
                n[p] += 1

        if n[p] == 0:
            fronts[0].append(p)

    # Successive front identification
    curr_front = 0
    while len(fronts[curr_front]) > 0:
        next_front: list[int] = []
        for p in fronts[curr_front]:
            for q in S[p]:
                n[q] -= 1
                if n[q] == 0:
                    next_front.append(q)
        curr_front += 1
        if len(next_front) > 0:
            fronts.append(next_front)
        else:
            break

    return fronts


def crowding_distance(front_indices: list[int], objectives: np.ndarray) -> np.ndarray:
    """Compute NSGA-II crowding distance for solutions in a given front.

    Boundary solutions with minimum and maximum values along each objective
    dimension are assigned infinite distance to preserve extent.

    Args:
        front_indices: List of solution indices belonging to the front.
        objectives: Complete (N, M) matrix of objective values.

    Returns:
        1D array of crowding distances corresponding to front_indices.
    """
    L = len(front_indices)
    if L == 0:
        return np.array([], dtype=float)
    if L <= 2:
        return np.full(L, np.inf, dtype=float)

    distances = np.zeros(L, dtype=float)
    front_objs = objectives[front_indices]
    n_objectives = objectives.shape[1]

    for m in range(n_objectives):
        sorted_pos = np.argsort(front_objs[:, m])

        # Boundary points get infinity
        distances[sorted_pos[0]] = np.inf
        distances[sorted_pos[-1]] = np.inf

        val_min = front_objs[sorted_pos[0], m]
        val_max = front_objs[sorted_pos[-1], m]
        spread = val_max - val_min

        if spread > 1e-12:
            for i in range(1, L - 1):
                distances[sorted_pos[i]] += (
                    front_objs[sorted_pos[i + 1], m] - front_objs[sorted_pos[i - 1], m]
                ) / spread

    return distances


def update_archive(
    archive: list[Solution],
    new_solutions: list[Solution],
    max_size: int = 100,
) -> list[Solution]:
    """Merge solutions, perform non-dominated sort, and retain front 0 up to max_size.

    If front 0 exceeds max_size, solutions with highest crowding distance are kept.

    Args:
        archive: Existing archive solutions.
        new_solutions: Newly evaluated candidate solutions.
        max_size: Maximum allowed solutions in the archive.

    Returns:
        Updated non-dominated archive.
    """
    # Combine and discard un-evaluated solutions
    all_evaluated = [s for s in (archive + new_solutions) if s.objectives is not None]
    if not all_evaluated:
        return []

    # Feasibility-first filtering: only feasible solutions enter archive if any exist
    feasible_pool = [s for s in all_evaluated if s.feasible]
    pool = feasible_pool if feasible_pool else all_evaluated

    objs = np.array([
        s.raw_objectives if s.raw_objectives is not None else s.objectives
        for s in pool
    ])
    fronts = fast_nondominated_sort(objs)
    if not fronts or not fronts[0]:
        return []

    front_0 = fronts[0]
    distances = crowding_distance(front_0, objs)

    # Assign crowding distances and ranks
    for i, idx in enumerate(front_0):
        pool[idx].crowding_dist = float(distances[i])
        pool[idx].rank = 0

    if len(front_0) <= max_size:
        return [pool[idx] for idx in front_0]

    # Truncate front 0 by crowding distance descending
    # Replace np.inf with a very large number for sorting stability
    finite_dist = np.where(np.isinf(distances), 1e15, distances)
    order = np.argsort(-finite_dist)
    selected_indices = [front_0[k] for k in order[:max_size]]
    return [pool[idx] for idx in selected_indices]
