"""Quantum-behaved Particle Swarm Optimization (QPSO) for continuous voyage speeds.

Updates the cruising speed matrix s[v, r] for each particle in the hybrid population
guided by mean personal best attractor dynamics and external Pareto archive leaders.

References:
    - Sun, J. et al. (2004). Particle swarm optimization with particles having
      quantum behavior. IEEE CEC.
    - docs/algorithms.md §2 QPSO (continuous speeds s[v,r])
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from src.optimization.individual import Solution


def _get(obj: Any, key: str, default: Any = 0.0) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def update_speeds(
    speeds: np.ndarray,
    pbest_speeds: np.ndarray,
    archive: list[Solution],
    vessels: Sequence[Any],
    routes: Sequence[Any],
    beta: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Update continuous vessel speed matrices across the entire population.

    Update rule per particle i, vessel v, route r:
        mbest = mean(pbest_speeds, axis=0)
        p = phi * pbest[i] + (1 - phi) * leader_speeds
        s[i, v, r] = p ± beta * |mbest[v, r] - speeds[i, v, r]| * ln(1 / u)
        where phi ~ U(0, 1), u ~ U(0, 1), sign in {-1, +1} with prob 0.5.

    The speed is subsequently clipped to [vmin_v, vmax_v] and schedule bounds.

    Args:
        speeds: (pop_size, V, R) current speed matrix.
        pbest_speeds: (pop_size, V, R) personal best speed matrix.
        archive: Non-dominated Pareto archive.
        vessels: List of vessel specifications.
        routes: List of route parameters.
        beta: Current contraction-expansion coefficient (linearly decaying 1.0 -> 0.4).
        rng: Seeded numpy Generator.

    Returns:
        Updated (pop_size, V, R) speed matrix.
    """
    pop_size, V, R = speeds.shape
    new_speeds = np.zeros_like(speeds)

    # Compute mean personal best attractor across population
    # Shape: (V, R)
    mbest = np.mean(pbest_speeds, axis=0)

    # Precalculate vessel and route speed bounds
    # Shape: (V, R)
    vmin_grid = np.zeros((V, R), dtype=float)
    vmax_grid = np.zeros((V, R), dtype=float)

    for v in range(V):
        vm = float(_get(vessels[v], "vmin", 8.0))
        vx = float(_get(vessels[v], "vmax", 22.0))
        for r in range(R):
            dist = float(_get(routes[r], "distance_nm", 1000.0))
            sched_hours = float(_get(routes[r], "schedule_days", 10.0)) * 24.0
            min_sched_spd = dist / max(1.0, sched_hours)

            # Feasible cruising speed lower bound
            lo = min_sched_spd if min_sched_spd <= vx else vm
            lo = max(vm, lo)
            vmin_grid[v, r] = lo
            vmax_grid[v, r] = max(lo, vx)

    # Compute selection probabilities for archive solutions if available
    archive_speeds: list[np.ndarray] = []
    selection_probs: np.ndarray | None = None

    if len(archive) > 0:
        archive_speeds = [sol.speeds for sol in archive]
        # Crowding-weighted selection probabilities (same guard as QIEA)
        arch_dists = np.array([sol.crowding_dist for sol in archive], dtype=float)
        finite = arch_dists[np.isfinite(arch_dists)]
        if finite.size > 0:
            capped = np.where(np.isfinite(arch_dists), arch_dists, finite.max() * 2.0)
        else:
            capped = np.ones_like(arch_dists)
        total = capped.sum()
        if not np.isfinite(total) or total <= 0:
            selection_probs = np.full(len(archive), 1.0 / len(archive))
        else:
            selection_probs = capped / total

    # Update each particle's speed matrix
    for i in range(pop_size):
        # Select leader speeds from archive or population
        if len(archive_speeds) > 0:
            leader_idx = rng.choice(len(archive_speeds), p=selection_probs)
            leader = archive_speeds[leader_idx]
        else:
            # Fallback to random personal best
            leader = pbest_speeds[rng.integers(0, pop_size)]

        # Stochastic attractor p = phi * pbest[i] + (1 - phi) * leader
        phi = rng.uniform(0.0, 1.0, size=(V, R))
        p = phi * pbest_speeds[i] + (1.0 - phi) * leader

        # Quantum position jump
        u = rng.uniform(1e-12, 1.0, size=(V, R))
        signs = rng.choice([-1.0, 1.0], size=(V, R))
        diff = np.abs(mbest - speeds[i])
        jump = signs * beta * diff * np.log(1.0 / u)

        updated = p + jump

        # Clip strictly to vessel & schedule limits
        new_speeds[i] = np.clip(updated, vmin_grid, vmax_grid)

    return new_speeds
