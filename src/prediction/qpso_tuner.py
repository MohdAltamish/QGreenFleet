"""Quantum-behaved Particle Swarm Optimization (QPSO) for XGBoost tuning.

Implements QPSO (Sun et al., 2004) from scratch using NumPy.
Tunes continuous and discrete hyperparameters of XGBoost over 3-fold CV.

Reference:
    Sun, J., Feng, B., & Xu, W. (2004). Particle swarm optimization with
    particles having quantum behavior. In Proceedings of the 2004 Congress
    on Evolutionary Computation (Vol. 1, pp. 325-331). IEEE.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.metrics import root_mean_squared_error
from sklearn.model_selection import KFold
import xgboost as xgb


class QPSOSearchSpace:
    """Represents the hyperparameter search space normalized to [0, 1]^D."""

    DIMENSION: int = 6

    def __init__(self, n_estimators_max: int = 800) -> None:
        """Initialize search space bounds.

        Args:
            n_estimators_max: Upper bound for n_estimators (default 800).
        """
        self.lr_min = 0.01
        self.lr_max = 0.3
        self.depth_min = 3
        self.depth_max = 10
        self.subsample_min = 0.5
        self.subsample_max = 1.0
        self.colsample_min = 0.5
        self.colsample_max = 1.0
        self.n_est_min = 100
        self.n_est_max = n_estimators_max
        self.min_child_min = 1
        self.min_child_max = 10

    def decode(self, position: np.ndarray) -> dict[str, Any]:
        """Decode a normalized position vector in [0, 1]^6 to XGBoost kwargs.

        Args:
            position: 1D array of shape (6,) with elements in [0, 1].

        Returns:
            Dictionary with decoded hyperparameters.
        """
        p = np.clip(position, 0.0, 1.0)

        # learning_rate on logarithmic scale in [0.01, 0.3]
        log_lr_min = np.log(self.lr_min)
        log_lr_max = np.log(self.lr_max)
        lr = float(np.exp(log_lr_min + p[0] * (log_lr_max - log_lr_min)))

        # max_depth in [3, 10]
        max_depth = int(np.round(self.depth_min + p[1] * (self.depth_max - self.depth_min)))

        # subsample in [0.5, 1.0]
        subsample = float(self.subsample_min + p[2] * (self.subsample_max - self.subsample_min))

        # colsample_bytree in [0.5, 1.0]
        colsample_bytree = float(
            self.colsample_min + p[3] * (self.colsample_max - self.colsample_min)
        )

        # n_estimators in [100, n_est_max]
        n_estimators = int(
            np.round(self.n_est_min + p[4] * (self.n_est_max - self.n_est_min))
        )

        # min_child_weight in [1, 10]
        min_child_weight = int(
            np.round(self.min_child_min + p[5] * (self.min_child_max - self.min_child_min))
        )

        return {
            "learning_rate": lr,
            "max_depth": max_depth,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "n_estimators": n_estimators,
            "min_child_weight": min_child_weight,
        }


def evaluate_params(
    params: dict[str, Any],
    X: pd.DataFrame | np.ndarray,
    y: pd.Series | np.ndarray,
    folds: list[tuple[np.ndarray, np.ndarray]],
    seed: int,
) -> float:
    """Evaluate XGBoost parameter set using precomputed CV folds.

    Args:
        params: Decoded hyperparameter dictionary.
        X: Feature matrix.
        y: Target array.
        folds: List of (train_idx, val_idx) fold splits.
        seed: Random seed for XGBoost initialization.

    Returns:
        Mean validation RMSE across the CV folds.
    """
    X_arr = X.values if isinstance(X, pd.DataFrame) else np.asarray(X)
    y_arr = y.values if isinstance(y, (pd.Series, pd.DataFrame)) else np.asarray(y)

    rmses: list[float] = []
    for train_idx, val_idx in folds:
        X_tr, y_tr = X_arr[train_idx], y_arr[train_idx]
        X_va, y_val = X_arr[val_idx], y_arr[val_idx]

        reg = xgb.XGBRegressor(
            **params,
            random_state=seed,
            n_jobs=-1,
            tree_method="hist",
            eval_metric="rmse",
        )
        reg.fit(X_tr, y_tr)
        preds = reg.predict(X_va)
        rmse = float(root_mean_squared_error(y_val, preds))
        rmses.append(rmse)

    return float(np.mean(rmses))


def qpso_tune_xgboost(
    X: pd.DataFrame | np.ndarray,
    y: pd.Series | np.ndarray,
    n_particles: int = 15,
    n_iterations: int = 25,
    beta_start: float = 1.0,
    beta_end: float = 0.4,
    n_splits: int = 3,
    n_estimators_max: int = 600,
    seed: int = 42,
    verbose: bool = True,
) -> tuple[dict[str, Any], list[float]]:
    """Run QPSO to optimize XGBoost hyperparameters over CV RMSE.

    Args:
        X: Feature dataset.
        y: Target fuel consumption values.
        n_particles: Swarm size (default 15).
        n_iterations: Optimization iterations (default 25).
        beta_start: Contraction-expansion coefficient at start (default 1.0).
        beta_end: Contraction-expansion coefficient at finish (default 0.4).
        n_splits: K-fold splits for fitness evaluation (default 3).
        n_estimators_max: Upper bound for n_estimators (default 600).
        seed: Deterministic random seed for RNG.
        verbose: Whether to print progress during optimization.

    Returns:
        Tuple of (best_hyperparameters_dict, convergence_history_list).
    """
    rng = np.random.default_rng(seed)
    space = QPSOSearchSpace(n_estimators_max=n_estimators_max)
    d = space.DIMENSION

    # Pre-generate CV folds once
    n_samples = len(X)
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=seed)
    folds = list(kf.split(np.arange(n_samples)))

    # Initialize particle positions uniformly in [0, 1]^d
    particles = rng.uniform(0.0, 1.0, size=(n_particles, d))
    pbest = particles.copy()
    pbest_fitness = np.full(n_particles, np.inf)

    gbest = particles[0].copy()
    gbest_fitness = np.inf

    # Initial fitness evaluation
    if verbose:
        print(f"QPSO: Initializing swarm ({n_particles} particles, {d} dimensions)...")

    for i in range(n_particles):
        params_i = space.decode(particles[i])
        fit_i = evaluate_params(params_i, X, y, folds, seed=seed)
        pbest_fitness[i] = fit_i
        if fit_i < gbest_fitness:
            gbest_fitness = fit_i
            gbest = particles[i].copy()

    history: list[float] = [float(gbest_fitness)]
    if verbose:
        print(f"QPSO Iter 0/{n_iterations} | Best CV RMSE: {gbest_fitness:.4f}")

    # QPSO main loop
    for t in range(n_iterations):
        # Linear beta decay: 1.0 -> 0.4
        if n_iterations > 1:
            beta = beta_start - (t / (n_iterations - 1)) * (beta_start - beta_end)
        else:
            beta = beta_end

        # mbest = mean of all personal bests
        mbest = np.mean(pbest, axis=0)

        for i in range(n_particles):
            # Stochastic attractor p = phi * pbest_i + (1 - phi) * gbest
            phi = rng.uniform(0.0, 1.0, size=d)
            p = phi * pbest[i] + (1.0 - phi) * gbest

            # Quantum delta potential well position update
            u = rng.uniform(1e-12, 1.0, size=d)
            signs = rng.choice([-1.0, 1.0], size=d)
            step = signs * beta * np.abs(mbest - particles[i]) * np.log(1.0 / u)

            # Update position and clip strictly to [0, 1]
            particles[i] = np.clip(p + step, 0.0, 1.0)

            # Evaluate fitness
            params_i = space.decode(particles[i])
            fit_i = evaluate_params(params_i, X, y, folds, seed=seed)

            if fit_i < pbest_fitness[i]:
                pbest_fitness[i] = fit_i
                pbest[i] = particles[i].copy()
                if fit_i < gbest_fitness:
                    gbest_fitness = fit_i
                    gbest = particles[i].copy()

        history.append(float(gbest_fitness))
        if verbose and ((t + 1) % 5 == 0 or t == n_iterations - 1):
            print(f"QPSO Iter {t + 1}/{n_iterations} | Best CV RMSE: {gbest_fitness:.4f} (beta={beta:.3f})")

    best_params = space.decode(gbest)
    return best_params, history
