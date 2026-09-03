"""Quantum individual representation and population initialization for QGreenFleet.

Implements the probabilistic Q-bit matrix encoding for discrete decisions
(vessel assignment, fuel selection, shore power) and continuous speed matrices.

Binary variable layout:
    1. Assignment variables: x[v, r] in {0, 1}
       Size: V * R binary variables.
       x[v, r] = 1 indicates vessel v is deployed on route r.

    2. Fuel selection one-hot block: f[v] in {0, ..., |F|-1}
       Size: V * |F| binary variables.
       |F| = 5 fuels: (HFO, LNG_DIESEL, MEOH_GREEN, H2_GREEN, NH3_GREEN).
       Decoded as argmax over the |F| block; repaired to 0 (HFO) if all zero.

    3. Shore power connection: sp[v, p] in {0, 1}
       Size: V * P binary variables.
       sp[v, p] = 1 indicates vessel v connects to cold ironing at port p.

Total binary variables:
    N_bin = (V * R) + (V * |F|) + (V * P)

References:
    - docs/mathematical-model.md §Decision variables
    - docs/algorithms.md §1 Q-bit encoding
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

# Canonical optimizer fuels list (size |F| = 5)
OPTIMIZER_FUELS: tuple[str, ...] = (
    "HFO",
    "LNG_DIESEL",
    "MEOH_GREEN",
    "H2_GREEN",
    "NH3_GREEN",
)


@dataclass
class Solution:
    """Represents a joint quantum-probabilistic and continuous fleet deployment solution.

    Attributes:
        q_matrix: (N_bin, 2) array of Q-bits [alpha, beta] where alpha^2 + beta^2 = 1.
        speeds: (V, R) float array of vessel cruising speeds in knots.
        observed: Collapsed binary decisions with keys 'assignment', 'fuel', 'shore_power'.
        objectives: Array of [fuel_cost, ghg_tco2e, opex] after evaluation.
        feasible: True if all hard operational constraints are satisfied after repair.
        violations: Dictionary of constraint violation magnitudes.
    """

    q_matrix: np.ndarray
    speeds: np.ndarray
    observed: dict[str, np.ndarray] = field(default_factory=dict)
    objectives: np.ndarray | None = None
    raw_objectives: np.ndarray | None = None  # unpenalized [Z1, Z2, Z3] for fair metric comparison
    feasible: bool = False
    violations: dict[str, float] = field(default_factory=dict)
    crowding_dist: float = 0.0
    rank: int = 0

    @property
    def V(self) -> int:
        """Number of vessels."""
        return self.speeds.shape[0]

    @property
    def R(self) -> int:
        """Number of routes."""
        return self.speeds.shape[1]


def observe(
    sol: Solution,
    rng: np.random.Generator,
    n_fuels: int = len(OPTIMIZER_FUELS),
    n_ports: int | None = None,
) -> Solution:
    """Collapse quantum state into classical binary decisions via Born measurement.

    Each qubit i is observed as bit = 1 with probability beta_i^2.
    Decodes the flat bitstring into structured decision arrays:
        - assignment: (V, R) boolean array
        - fuel: (V,) integer array with values in {0, ..., |F|-1}
        - shore_power: (V, P) boolean array

    Args:
        sol: Quantum solution containing q_matrix and speeds.
        rng: Seeded numpy Generator for stochastic sampling.
        n_fuels: Number of alternative fuels (|F|, default 5).
        n_ports: Number of ports (P). Inferred from q_matrix if None.

    Returns:
        The Solution instance with updated `observed` dictionary.
    """
    V, R = sol.speeds.shape

    # Calculate P if not explicitly provided
    # Total = V*R + V*n_fuels + V*P => V*P = Total - V*R - V*n_fuels
    total_qbits = sol.q_matrix.shape[0]
    if n_ports is None:
        rem = total_qbits - (V * R + V * n_fuels)
        P = max(1, rem // V) if V > 0 else 1
    else:
        P = n_ports

    # Born measurement: P(bit=1) = beta^2
    beta_sq = sol.q_matrix[:, 1] ** 2
    random_draws = rng.random(total_qbits)
    bits = (random_draws < beta_sq).astype(int)

    # 1. Assignment block: first V * R bits
    assign_end = V * R
    assignment_bits = bits[:assign_end].reshape(V, R).astype(bool)

    # 2. Fuel block: next V * n_fuels bits
    fuel_end = assign_end + V * n_fuels
    fuel_bits = bits[assign_end:fuel_end].reshape(V, n_fuels)

    # Decode each vessel's one-hot block: argmax, repair all-zero to 0 (HFO)
    fuel_indices = np.zeros(V, dtype=int)
    for v in range(V):
        v_block = fuel_bits[v]
        if np.any(v_block > 0):
            fuel_indices[v] = int(np.argmax(v_block))
        else:
            fuel_indices[v] = 0  # HFO fallback

    # 3. Shore power block: next V * P bits
    sp_end = fuel_end + V * P
    if total_qbits >= sp_end:
        sp_bits = bits[fuel_end:sp_end].reshape(V, P).astype(bool)
    else:
        sp_bits = np.zeros((V, P), dtype=bool)

    sol.observed = {
        "bits": bits,
        "assignment": assignment_bits,
        "fuel": fuel_indices,
        "shore_power": sp_bits,
    }
    return sol


def init_population(
    pop_size: int,
    V: int,
    R: int,
    P: int,
    F: int | Sequence[str] = len(OPTIMIZER_FUELS),
    rng: np.random.Generator | None = None,
    vmins: np.ndarray | None = None,
    vmaxs: np.ndarray | None = None,
) -> list[Solution]:
    """Initialize a population of Q-individuals and continuous cruising speeds.

    All Q-bits are initialized to the equal superposition state:
        [alpha, beta] = [1 / sqrt(2), 1 / sqrt(2)]

    Cruising speeds s[v, r] are uniformly sampled from [vmin_v, vmax_v].

    Args:
        pop_size: Number of candidate solutions in the population.
        V: Number of candidate fleet vessels.
        R: Number of commercial shipping routes.
        P: Number of unique destination ports.
        F: Number of fuel options or sequence of fuel names.
        rng: Seeded numpy Generator.
        vmins: Optional 1D array of minimum speeds per vessel (default 8.0 kn).
        vmaxs: Optional 1D array of maximum speeds per vessel (default 22.0 kn).

    Returns:
        List of initialized Solution instances.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    n_fuels = len(F) if isinstance(F, (list, tuple)) else int(F)
    n_binary_vars = (V * R) + (V * n_fuels) + (V * P)

    # Base Q-bit state: [1/√2, 1/√2] ensuring alpha^2 + beta^2 = 1.0
    q_init_state = np.array([1.0 / np.sqrt(2.0), 1.0 / np.sqrt(2.0)], dtype=float)

    # Vessel speed bounds
    v_lo = vmins if vmins is not None else np.full(V, 8.0)
    v_hi = vmaxs if vmaxs is not None else np.full(V, 22.0)

    population: list[Solution] = []
    for _ in range(pop_size):
        q_matrix = np.tile(q_init_state, (n_binary_vars, 1))

        # Uniformly sample speeds for each vessel across routes
        # Shape: (V, R)
        speeds = np.zeros((V, R), dtype=float)
        for v in range(V):
            speeds[v, :] = rng.uniform(v_lo[v], v_hi[v], size=R)

        sol = Solution(
            q_matrix=q_matrix,
            speeds=speeds,
        )
        population.append(sol)

    return population
