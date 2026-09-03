"""Multi-objective performance indicators for benchmark evaluation.

Provides:
    - hypervolume: Volume of objective space dominated by Pareto front.
    - normalized_hypervolume: HV on normalized fronts vs fixed (1.1,1.1,1.1) ref in [0, 1.331].
    - igd: IGD vs reference front (expects pre-normalized inputs from normalize_fronts).
    - spread: Extent/diversity via mean nearest-neighbor distance.
    - evals_to_threshold: Evals to reach 95% of final normalized HV.
    - filter_nondominated_feasible: Feasible non-dominated raw objectives from Solutions.
    - normalize_fronts: Normalize fronts to [0,1]^M using global per-objective bounds.
    - build_reference_front: Merged non-dominated reference front across all algos/seeds.

References:
    - Zitzler, E. et al. (2003). Performance assessment of multiobjective optimizers.
      IEEE Trans. Evolutionary Computation.
    - docs/algorithms.md §Benchmarking
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

if TYPE_CHECKING:
    from src.optimization.individual import Solution


# ---------------------------------------------------------------------------
# 1. Raw hypervolume (unnormalized; used internally and for convergence plots)
# ---------------------------------------------------------------------------

def hypervolume(
    pareto_objectives: np.ndarray | Sequence[Sequence[float]],
    ref_point: np.ndarray | Sequence[float] | None = None,
    n_samples: int = 100_000,
    seed: int = 42,
) -> float:
    """Calculate Hypervolume indicator for 2D or 3D Pareto fronts.

    For 2D, computes the exact geometric Lebesgue measure.
    For 3D, uses high-precision Monte Carlo integration (reproducible via seed).

    Args:
        pareto_objectives: (N, M) matrix of minimization objective vectors.
        ref_point: Optional upper bound reference point. Defaults to 1.1 * nadir.
        n_samples: Number of Monte Carlo samples for 3D evaluation.
        seed: Random seed for Monte Carlo sampling.

    Returns:
        Scalar hypervolume metric value.
    """
    pts = np.asarray(pareto_objectives, dtype=float)
    if pts.size == 0 or pts.ndim != 2:
        return 0.0

    N, M = pts.shape
    if N == 0:
        return 0.0

    if ref_point is None:
        ref = 1.1 * np.max(pts, axis=0)
    else:
        ref = np.asarray(ref_point, dtype=float)

    valid_mask = np.all(pts <= ref, axis=1)
    valid_pts = pts[valid_mask]
    if len(valid_pts) == 0:
        return 0.0

    ideal = np.min(valid_pts, axis=0)
    box_volume = float(np.prod(ref - ideal))
    if box_volume <= 1e-12:
        return 0.0

    if M == 2:
        sorted_idx = np.argsort(valid_pts[:, 0])
        sorted_pts = valid_pts[sorted_idx]
        hv = 0.0
        filtered: list[np.ndarray] = []
        for p in sorted_pts:
            if not filtered:
                filtered.append(p)
            elif p[1] < filtered[-1][1]:
                filtered.append(p)
        n_f = len(filtered)
        for i in range(n_f):
            x_curr = filtered[i][0]
            x_next = filtered[i + 1][0] if i + 1 < n_f else ref[0]
            height = ref[1] - filtered[i][1]
            width = x_next - x_curr
            if width > 0 and height > 0:
                hv += width * height
        return float(hv)

    rng = np.random.default_rng(seed)
    spread_range = ref - ideal
    norm_pts = (valid_pts - ideal) / spread_range
    samples = rng.uniform(0.0, 1.0, size=(n_samples, M))
    is_dominated = np.zeros(n_samples, dtype=bool)
    for p in norm_pts:
        is_dominated |= np.all(samples >= p, axis=1)
    fraction = float(np.mean(is_dominated))
    return fraction * box_volume


# ---------------------------------------------------------------------------
# 2. Fair archive extraction
# ---------------------------------------------------------------------------

def filter_nondominated_feasible(solutions: list[Solution]) -> np.ndarray:
    """Extract the non-dominated front from feasible solutions using raw_objectives.

    Uses raw_objectives (unpenalized) for dominance comparison so penalty terms
    do not inflate any solution's apparent quality. Falls back to infeasible
    solutions only if no feasible solutions exist in the pool.

    Args:
        solutions: List of Solution objects from an algorithm run.

    Returns:
        (N_nd, 3) array of non-dominated raw objective vectors.
        Returns empty (0, 3) array if no solutions have raw_objectives.
    """
    from src.optimization.pareto import fast_nondominated_sort

    feasible = [s for s in solutions if s.feasible and s.raw_objectives is not None]
    if not feasible:
        has_raw = [s for s in solutions if s.raw_objectives is not None]
        if not has_raw:
            return np.empty((0, 3), dtype=float)
        feasible = has_raw

    objs = np.array([s.raw_objectives for s in feasible], dtype=float)
    if len(objs) == 1:
        return objs

    fronts = fast_nondominated_sort(objs)
    if not fronts or not fronts[0]:
        return objs
    return objs[fronts[0]]


# ---------------------------------------------------------------------------
# 3. Normalization — global bounds across all algos/seeds for an instance
# ---------------------------------------------------------------------------

def normalize_fronts(
    fronts: list[np.ndarray],
    obj_min: np.ndarray | None = None,
    obj_max: np.ndarray | None = None,
) -> tuple[list[np.ndarray], np.ndarray, np.ndarray]:
    """Normalize a list of objective fronts to [0, 1]^M using global bounds.

    Global bounds are computed across ALL fronts so every algorithm is scaled
    identically — a prerequisite for fair HV and IGD comparison.

    Args:
        fronts: List of (N_i, M) raw objective arrays.
        obj_min: Pre-computed per-objective minimum (optional, computed if None).
        obj_max: Pre-computed per-objective maximum (optional, computed if None).

    Returns:
        Tuple of (normalized_fronts, obj_min, obj_max).
    """
    non_empty = [f for f in fronts if len(f) > 0]
    if not non_empty:
        zeros = np.zeros(3, dtype=float)
        return [np.empty((0, 3), dtype=float)] * len(fronts), zeros, zeros

    if obj_min is None or obj_max is None:
        stacked = np.vstack(non_empty)
        obj_min = np.min(stacked, axis=0)
        obj_max = np.max(stacked, axis=0)

    denom = np.where(obj_max - obj_min > 1e-12, obj_max - obj_min, 1.0)
    normalized = [
        (f - obj_min) / denom if len(f) > 0 else np.empty((0, denom.shape[0]), dtype=float)
        for f in fronts
    ]
    return normalized, obj_min, obj_max


# ---------------------------------------------------------------------------
# 4. Normalized hypervolume — always in [0, 1.331]
# ---------------------------------------------------------------------------

NORMALIZED_REF_POINT: tuple[float, float, float] = (1.1, 1.1, 1.1)


def normalized_hypervolume(
    norm_front: np.ndarray,
    ref_point: tuple[float, ...] = NORMALIZED_REF_POINT,
    n_samples: int = 100_000,
    seed: int = 42,
) -> float:
    """Compute hypervolume on a pre-normalized front vs the shared reference point.

    Since norm_front is in [0, 1]^3 and ref = (1.1, 1.1, 1.1), the maximum
    possible HV is 1.1^3 = 1.331.

    Args:
        norm_front: (N, M) array of objectives already normalized to [0, 1]^M.
        ref_point: Shared reference point across all algorithms per instance.
        n_samples: Monte Carlo samples for 3D integration.
        seed: Reproducibility seed.

    Returns:
        HV value in [0, 1.331].
    """
    return hypervolume(norm_front, ref_point=list(ref_point), n_samples=n_samples, seed=seed)


# ---------------------------------------------------------------------------
# 5. Merged reference front
# ---------------------------------------------------------------------------

def build_reference_front(
    fronts: Sequence[np.ndarray | Sequence[Sequence[float]]],
) -> np.ndarray:
    """Construct a unified non-dominated Pareto reference front from multiple fronts.

    Merges all solution objective vectors from archives across algorithms and seeds,
    filters duplicates, and extracts the non-dominated Pareto frontier (Front 0).
    No algorithm may be its own sole reference — all fronts are merged together.

    Args:
        fronts: Sequence of (N_i, M) objective arrays (should be pre-normalized).

    Returns:
        (N_ref, M) array representing the merged non-dominated reference front.
    """
    from src.optimization.pareto import fast_nondominated_sort

    valid_arrays = [
        np.asarray(f, dtype=float)
        for f in fronts
        if len(f) > 0 and np.asarray(f).ndim == 2
    ]
    if not valid_arrays:
        return np.empty((0, 3), dtype=float)

    combined = np.vstack(valid_arrays)
    unique_pts = np.unique(combined, axis=0)
    if len(unique_pts) <= 1:
        return unique_pts

    sorted_fronts = fast_nondominated_sort(unique_pts)
    if not sorted_fronts or not sorted_fronts[0]:
        return unique_pts
    return unique_pts[sorted_fronts[0]]


# ---------------------------------------------------------------------------
# 6. IGD — expects pre-normalized fronts (same global bounds as HV)
# ---------------------------------------------------------------------------

def igd(
    approx_front: np.ndarray | Sequence[Sequence[float]],
    reference_front: np.ndarray | Sequence[Sequence[float]],
) -> float:
    """Compute Inverted Generational Distance (IGD) against a reference front.

    Expects both fronts to be pre-normalized to [0, 1]^M using the same
    global bounds (via normalize_fronts). Do NOT pass raw objective values.

    Args:
        approx_front: Candidate Pareto front (N_A, M), normalized.
        reference_front: Merged Pareto reference front (N_R, M), normalized.

    Returns:
        Mean Euclidean distance from reference points to nearest approx points.
        Returns inf if either front is empty.
    """
    A = np.asarray(approx_front, dtype=float)
    R = np.asarray(reference_front, dtype=float)

    if A.size == 0 or R.size == 0:
        return float("inf")

    if A.shape == R.shape and np.allclose(A, R):
        return 0.0

    min_dists = np.zeros(len(R), dtype=float)
    for i, r_pt in enumerate(R):
        dists = np.linalg.norm(A - r_pt, axis=1)
        min_dists[i] = np.min(dists)

    return float(np.mean(min_dists))


# ---------------------------------------------------------------------------
# 7. evals_to_threshold — must be called on normalized HV history
# ---------------------------------------------------------------------------

def evals_to_threshold(
    history: Sequence[float] | dict[str, Any],
    threshold: float = 0.95,
    evals_per_step: int = 1,
) -> int | float:
    """Determine number of function evaluations needed to attain threshold * final_HV.

    Must be called with a NORMALIZED HV history so the metric is comparable
    across instances of different scales. Returns nan if saturated at step 0.

    Args:
        history: Sequence of normalized HV values, or dict with "hypervolume" key.
        threshold: Proportional target of final hypervolume (default 0.95).
        evals_per_step: Evaluation multiplier per generation/step (pop_size).

    Returns:
        Number of evaluations, or float("nan") if saturated at step 0 or unreached.
    """
    if isinstance(history, dict):
        if "hypervolume" in history:
            hv_series = np.asarray(history["hypervolume"], dtype=float)
        else:
            return float("nan")
    else:
        hv_series = np.asarray(history, dtype=float)

    if len(hv_series) == 0:
        return float("nan")

    final_hv = hv_series[-1]
    total_evals = len(hv_series) * evals_per_step

    if final_hv <= 1e-9:
        return float("nan")

    target = threshold * final_hv
    indices = np.where(hv_series >= target)[0]

    if len(indices) == 0:
        return total_evals

    if indices[0] == 0:
        return float("nan")

    return int((indices[0] + 1) * evals_per_step)


# ---------------------------------------------------------------------------
# 8. Spread
# ---------------------------------------------------------------------------

def spread(pareto_objectives: np.ndarray | Sequence[Sequence[float]]) -> float:
    """Compute Pareto front spread/extent as mean nearest-neighbor distance.

    Objectives are normalized to [0, 1] before calculating Euclidean distances.

    Args:
        pareto_objectives: (N, M) matrix of non-dominated solutions.

    Returns:
        Mean nearest-neighbor distance. Returns np.nan if |front| < 2.
    """
    pts = np.asarray(pareto_objectives, dtype=float)
    if pts.size == 0 or pts.ndim != 2:
        return float("nan")

    N, M = pts.shape
    if N < 2:
        return float("nan")

    pt_min = np.min(pts, axis=0)
    pt_max = np.max(pts, axis=0)
    denom = np.where(pt_max - pt_min > 1e-9, pt_max - pt_min, 1.0)
    norm_pts = (pts - pt_min) / denom

    if N == 2:
        return float(np.linalg.norm(norm_pts[0] - norm_pts[1]))

    nn_dists = np.zeros(N, dtype=float)
    for i in range(N):
        diffs = norm_pts - norm_pts[i]
        dists = np.linalg.norm(diffs, axis=1)
        dists[i] = np.inf
        nn_dists[i] = np.min(dists)

    return float(np.mean(nn_dists))
