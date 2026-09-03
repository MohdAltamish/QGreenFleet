"""Predictive models for vessel fuel consumption in QGreenFleet.

All models adhere to a standard interface:
    fit(X, y) -> self
    predict(X) -> np.ndarray (tons/day)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
import xgboost as xgb

from src.prediction.qpso_tuner import qpso_tune_xgboost


class BaseModel(BaseEstimator, RegressorMixin):
    """Abstract base class establishing the common fit/predict interface."""

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> BaseModel:
        """Fit the model to training data."""
        raise NotImplementedError

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Predict fuel consumption (tons/day)."""
        raise NotImplementedError

    def get_params(self, deep: bool = True) -> dict[str, Any]:
        """Return model hyperparameters."""
        return {}


class PhysicsBaseline(BaseModel):
    """Admiralty-law physics baseline: fuel ~ k1 * speed^3 + k2 * draft.

    Only uses speed_cubed and draft_m features to enforce first-principles prior.
    """

    def __init__(self, feature_names: list[str] | None = None) -> None:
        """Initialize physics baseline.

        Args:
            feature_names: Optional feature column names if X is passed as array.
        """
        self.feature_names = feature_names
        self.reg_: LinearRegression | None = None
        self.speed_idx_: int | None = None
        self.draft_idx_: int | None = None

    def _extract_physics_features(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Extract [speed_cubed, draft_m] columns from input data."""
        if isinstance(X, pd.DataFrame):
            if "speed_cubed" in X.columns and "draft_m" in X.columns:
                return X[["speed_cubed", "draft_m"]].values
            raise ValueError("Input DataFrame must contain 'speed_cubed' and 'draft_m'")

        arr = np.asarray(X)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)

        if arr.shape[1] == 2:
            return arr

        if self.feature_names is not None and "speed_cubed" in self.feature_names and "draft_m" in self.feature_names:
            s_idx = self.feature_names.index("speed_cubed")
            d_idx = self.feature_names.index("draft_m")
            return arr[:, [s_idx, d_idx]]

        if self.speed_idx_ is not None and self.draft_idx_ is not None:
            return arr[:, [self.speed_idx_, self.draft_idx_]]

        # Default fallback to first two columns
        return arr[:, :2]

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> PhysicsBaseline:
        """Fit linear regression on [speed_cubed, draft_m]."""
        if isinstance(X, pd.DataFrame):
            self.feature_names = list(X.columns)
            self.speed_idx_ = self.feature_names.index("speed_cubed") if "speed_cubed" in self.feature_names else None
            self.draft_idx_ = self.feature_names.index("draft_m") if "draft_m" in self.feature_names else None

        X_phys = self._extract_physics_features(X)
        y_arr = y.values if isinstance(y, (pd.Series, pd.DataFrame)) else np.asarray(y)

        self.reg_ = LinearRegression(fit_intercept=True)
        self.reg_.fit(X_phys, y_arr)
        return self

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Predict fuel consumption using the fitted physics relationship."""
        if self.reg_ is None:
            raise RuntimeError("Model is not fitted yet.")
        X_phys = self._extract_physics_features(X)
        return self.reg_.predict(X_phys)

    def get_params(self, deep: bool = True) -> dict[str, Any]:
        params = {"feature_names": self.feature_names}
        if self.reg_ is not None:
            params["coef"] = self.reg_.coef_.tolist() if hasattr(self.reg_, "coef_") else None
            params["intercept"] = float(self.reg_.intercept_) if hasattr(self.reg_, "intercept_") else None
        return params


class RandomForestModel(BaseModel):
    """Random Forest Regressor baseline."""

    def __init__(self, n_estimators: int = 300, random_state: int = 42) -> None:
        """Initialize random forest model.

        Args:
            n_estimators: Number of trees in forest.
            random_state: RNG seed.
        """
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.model_ = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=-1,
        )

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> RandomForestModel:
        """Fit random forest on training features and target."""
        X_arr = X.values if isinstance(X, pd.DataFrame) else np.asarray(X)
        y_arr = y.values if isinstance(y, (pd.Series, pd.DataFrame)) else np.asarray(y)
        self.model_.fit(X_arr, y_arr)
        return self

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Predict using fitted random forest."""
        X_arr = X.values if isinstance(X, pd.DataFrame) else np.asarray(X)
        return self.model_.predict(X_arr)

    def get_params(self, deep: bool = True) -> dict[str, Any]:
        return {"n_estimators": self.n_estimators, "random_state": self.random_state}


class XGBoostModel(BaseModel):
    """Standard XGBoost regressor with sensible default hyperparameters."""

    def __init__(
        self,
        n_estimators: int = 500,
        learning_rate: float = 0.05,
        max_depth: int = 6,
        subsample: float = 0.9,
        random_state: int = 42,
    ) -> None:
        """Initialize XGBoost regressor with baseline hyperparameter values."""
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.subsample = subsample
        self.random_state = random_state
        self.model_ = xgb.XGBRegressor(
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            subsample=self.subsample,
            random_state=self.random_state,
            n_jobs=-1,
            eval_metric="rmse",
        )

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> XGBoostModel:
        """Fit XGBoost model."""
        X_arr = X.values if isinstance(X, pd.DataFrame) else np.asarray(X)
        y_arr = y.values if isinstance(y, (pd.Series, pd.DataFrame)) else np.asarray(y)
        self.model_.fit(X_arr, y_arr)
        return self

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Predict fuel consumption."""
        X_arr = X.values if isinstance(X, pd.DataFrame) else np.asarray(X)
        return self.model_.predict(X_arr)

    def get_params(self, deep: bool = True) -> dict[str, Any]:
        return {
            "n_estimators": self.n_estimators,
            "learning_rate": self.learning_rate,
            "max_depth": self.max_depth,
            "subsample": self.subsample,
            "random_state": self.random_state,
        }


class QPSOXGBoost(BaseModel):
    """XGBoost model with hyperparameters tuned by QPSO."""

    def __init__(
        self,
        n_particles: int = 15,
        n_iterations: int = 25,
        random_state: int = 42,
        verbose: bool = True,
    ) -> None:
        """Initialize QPSO-tuned XGBoost model."""
        self.n_particles = n_particles
        self.n_iterations = n_iterations
        self.random_state = random_state
        self.verbose = verbose
        self.best_params_: dict[str, Any] | None = None
        self.convergence_history_: list[float] = []
        self.model_: xgb.XGBRegressor | None = None

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> QPSOXGBoost:
        """Run QPSO to find optimal hyperparameters, then fit final model."""
        self.best_params_, self.convergence_history_ = qpso_tune_xgboost(
            X=X,
            y=y,
            n_particles=self.n_particles,
            n_iterations=self.n_iterations,
            seed=self.random_state,
            verbose=self.verbose,
        )

        X_arr = X.values if isinstance(X, pd.DataFrame) else np.asarray(X)
        y_arr = y.values if isinstance(y, (pd.Series, pd.DataFrame)) else np.asarray(y)

        self.model_ = xgb.XGBRegressor(
            **self.best_params_,
            random_state=self.random_state,
            n_jobs=-1,
            eval_metric="rmse",
        )
        self.model_.fit(X_arr, y_arr)
        return self

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Predict using the optimal QPSO-tuned XGBoost model."""
        if self.model_ is None:
            raise RuntimeError("Model is not fitted yet.")
        X_arr = X.values if isinstance(X, pd.DataFrame) else np.asarray(X)
        return self.model_.predict(X_arr)

    def get_params(self, deep: bool = True) -> dict[str, Any]:
        params = {
            "n_particles": self.n_particles,
            "n_iterations": self.n_iterations,
            "random_state": self.random_state,
        }
        if self.best_params_ is not None:
            params.update(self.best_params_)
        return params
