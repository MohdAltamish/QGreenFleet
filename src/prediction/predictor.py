"""Production predictor interface for the fleet optimization engine.

Implements a two-stage hybrid prediction surrogate:
    1. Macro Empirical Stage (Real EU MRV Model):
       Predicts baseline fuel_per_nm (kg/nm) directly from verified statutory
       EU MRV THETIS operational records as a function of vessel category and
       cruising speed (accounting for cubic admiralty resistance), converted
       to metric tons per day:
           tons/day = fuel_per_nm_kg * speed_kn * 24 / 1000
    2. Micro Hydrodynamic Stage (Voyage Surrogate Adjustment):
       Applies a multiplicative draft and weather condition multiplier:
           adjustment = clip(pred(draft, weather) / pred(mean_draft, weather=1), 0.7, 1.3)
    3. Graceful Fallback:
       If models/mrv_best.pkl is absent, falls back to the calibrated single-stage model.
"""

from __future__ import annotations

import json
from pathlib import Path
import pickle
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.prediction.calibration import calibrated, normalize_type_key

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = _PROJECT_ROOT / "models" / "best.pkl"
DEFAULT_META_PATH = _PROJECT_ROOT / "models" / "best_meta.json"
DEFAULT_MRV_MODEL_PATH = _PROJECT_ROOT / "models" / "mrv_best.pkl"
DEFAULT_MRV_META_PATH = _PROJECT_ROOT / "models" / "mrv_best_meta.json"

# Nominal mean drafts per vessel category for baseline voyage normalization
TYPE_MEAN_DRAFTS: dict[str, float] = {
    "container": 12.0,
    "bulk": 10.5,
    "tanker": 11.5,
}


class FuelPredictor:
    """Production inference interface used by optimization algorithms and APIs."""

    def __init__(
        self,
        model_path: Path | str | None = None,
        meta_path: Path | str | None = None,
        mrv_model_path: Path | str | None = None,
        mrv_meta_path: Path | str | None = None,
    ) -> None:
        """Load trained voyage model, MRV model, and feature metadata from disk.

        Args:
            model_path: Path to voyage model file (default models/best.pkl).
            meta_path: Path to voyage metadata JSON (default models/best_meta.json).
            mrv_model_path: Path to MRV model file (default models/mrv_best.pkl).
            mrv_meta_path: Path to MRV metadata JSON (default models/mrv_best_meta.json).
        """
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self.meta_path = Path(meta_path) if meta_path else DEFAULT_META_PATH

        # If a custom model_path is provided without supplying mrv_model_path,
        # preserve single-stage evaluation for custom model testing
        if model_path is not None and mrv_model_path is None:
            self.mrv_model_path = None
            self.mrv_meta_path = None
        else:
            self.mrv_model_path = Path(mrv_model_path) if mrv_model_path else DEFAULT_MRV_MODEL_PATH
            self.mrv_meta_path = Path(mrv_meta_path) if mrv_meta_path else DEFAULT_MRV_META_PATH

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Voyage model file not found at {self.model_path}. "
                "Train the models first using 'python -m src.prediction.train'."
            )
        if not self.meta_path.exists():
            raise FileNotFoundError(
                f"Metadata file not found at {self.meta_path}. "
                "Train the models first using 'python -m src.prediction.train'."
            )

        self.model = joblib.load(self.model_path)
        meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        self.model_name: str = meta.get("model_name", "unknown")
        self.feature_columns: list[str] = meta.get("feature_columns", [])
        self.metrics: dict[str, float] = meta.get("metrics", {})

        # Attempt to load high-fidelity real EU MRV model (Stage 1)
        self.has_mrv: bool = False
        self.mrv_model: Any = None
        self.mrv_meta: dict[str, Any] = {}

        if (
            self.mrv_model_path is not None
            and self.mrv_meta_path is not None
            and self.mrv_model_path.exists()
            and self.mrv_meta_path.exists()
        ):
            try:
                with open(self.mrv_model_path, "rb") as f:
                    self.mrv_model = pickle.load(f)
                self.mrv_meta = json.loads(self.mrv_meta_path.read_text(encoding="utf-8"))
                self.has_mrv = True
            except Exception:
                self.has_mrv = False
                self.mrv_model = None

    def build_features(
        self,
        speed_arr: np.ndarray,
        draft_m: float | np.ndarray,
        weather_severity: int | float | np.ndarray,
        ship_type: str,
        route_type: str = "Transoceanic",
        maintenance_status: str = "Fair",
    ) -> pd.DataFrame:
        """Assemble feature dataframe strictly matching training column order.

        Args:
            speed_arr: 1D array of vessel speeds in knots.
            draft_m: Vessel draft in meters (scalar or array).
            weather_severity: Weather intensity code (0=calm, 1=moderate, 2=rough).
            ship_type: Vessel classification (container, bulk, tanker).
            route_type: Operational route type.
            maintenance_status: Vessel maintenance condition.

        Returns:
            DataFrame with exact feature column ordering expected by model.
        """
        n = len(speed_arr)
        norm_ship = normalize_type_key(ship_type)
        norm_route = route_type.strip().lower()
        norm_maint = maintenance_status.strip().lower()

        data: dict[str, np.ndarray] = {}
        for col in self.feature_columns:
            if col == "speed_kn":
                data[col] = speed_arr
            elif col == "speed_cubed":
                data[col] = speed_arr ** 3
            elif col == "draft_m":
                data[col] = np.asarray(draft_m, dtype=float) if np.ndim(draft_m) > 0 else np.full(n, float(draft_m), dtype=float)
            elif col == "weather_severity":
                data[col] = np.asarray(weather_severity, dtype=float) if np.ndim(weather_severity) > 0 else np.full(n, float(weather_severity), dtype=float)
            elif col.startswith("type_"):
                col_type = col.replace("type_", "").strip().lower()
                is_match = (
                    col_type in norm_ship
                    or norm_ship in col_type
                    or (norm_ship == "container" and "container" in col_type)
                    or (norm_ship == "bulk" and "bulk" in col_type)
                    or (norm_ship == "tanker" and "tanker" in col_type)
                )
                data[col] = np.full(n, 1 if is_match else 0, dtype=int)
            elif col.startswith("route_"):
                col_route = col.replace("route_", "").strip().lower()
                is_match = col_route in norm_route or norm_route in col_route
                data[col] = np.full(n, 1 if is_match else 0, dtype=int)
            elif col.startswith("maint_"):
                col_maint = col.replace("maint_", "").strip().lower()
                is_match = col_maint in norm_maint or norm_maint in col_maint
                data[col] = np.full(n, 1 if is_match else 0, dtype=int)
            else:
                data[col] = np.zeros(n, dtype=float)

        return pd.DataFrame(data, columns=self.feature_columns)

    def compute_adjustment_ratio(
        self,
        draft_m: float | np.ndarray,
        weather_severity: int | float | np.ndarray,
        ship_type: str,
        speed_kn: float | np.ndarray = 15.0,
    ) -> float | np.ndarray:
        """Compute voyage-level multiplicative hydrodynamic adjustment factor.

        Calculates ratio of model prediction at (draft, weather) to prediction
        at nominal reference conditions (type-mean draft, weather=1.0), strictly
        clipped to [0.7, 1.3].
        """
        norm_type = normalize_type_key(ship_type)
        mean_draft = TYPE_MEAN_DRAFTS.get(norm_type, 11.5)
        speed_arr = np.atleast_1d(np.asarray(speed_kn, dtype=float))

        feats_actual = self.build_features(
            speed_arr=speed_arr,
            draft_m=draft_m,
            weather_severity=weather_severity,
            ship_type=ship_type,
        )
        pred_actual = self.model.predict(feats_actual)

        feats_ref = self.build_features(
            speed_arr=speed_arr,
            draft_m=mean_draft,
            weather_severity=1.0,
            ship_type=ship_type,
        )
        pred_ref = self.model.predict(feats_ref)

        ratio = pred_actual / np.maximum(1e-6, pred_ref)
        adj = np.clip(ratio, 0.7, 1.3)

        if np.isscalar(speed_kn) and np.isscalar(draft_m):
            return float(adj[0])
        return adj

    def predict_tpd(
        self,
        speed_kn: float | np.ndarray,
        draft_m: float,
        weather_severity: int | float,
        ship_type: str,
        route_type: str = "Transoceanic",
        maintenance_status: str = "Fair",
    ) -> float | np.ndarray:
        """Predict fuel consumption in metric tons per day using two-stage surrogate.

        Args:
            speed_kn: Scalar speed or 1D array of speeds in knots.
            draft_m: Vessel draft in meters.
            weather_severity: Weather condition index (0=calm, 1=moderate, 2=rough).
            ship_type: Vessel classification ('container', 'bulk', 'tanker').
            route_type: Route type description (default 'Transoceanic').
            maintenance_status: Condition ('Fair', 'Good', 'Critical').

        Returns:
            Calibrated fuel consumption in tons/day matching scalar/array input shape.
        """
        is_scalar = np.isscalar(speed_kn) or isinstance(speed_kn, (float, int))
        speed_arr = np.atleast_1d(np.asarray(speed_kn, dtype=float))
        norm_type = normalize_type_key(ship_type)

        # Stage 1: Real EU MRV Operational Baseline (if available)
        if self.has_mrv and self.mrv_model is not None:
            n = len(speed_arr)
            defaults = self.mrv_meta.get("fleet_defaults", {}).get(
                norm_type,
                {"eedi_value": 10.0, "laden_ratio": 0.65, "fuel_per_dwt_nm": 0.0025},
            )

            mrv_data = {
                "avg_speed_kn": speed_arr,
                "speed_cubed": speed_arr ** 3,
                "eedi_value": np.full(n, float(defaults.get("eedi_value", 10.0))),
                "laden_ratio": np.full(n, float(defaults.get("laden_ratio", 0.65))),
                "fuel_per_dwt_nm": np.full(n, float(defaults.get("fuel_per_dwt_nm", 0.0025))),
                "category_bulk": np.full(n, 1 if norm_type == "bulk" else 0),
                "category_container": np.full(n, 1 if norm_type == "container" else 0),
                "category_tanker": np.full(n, 1 if norm_type == "tanker" else 0),
            }
            feat_order = self.mrv_meta.get("feature_names", list(mrv_data.keys())[:8])
            mrv_df = pd.DataFrame(mrv_data)[feat_order]

            fuel_per_nm_kg = np.maximum(0.1, self.mrv_model.predict(mrv_df))
            # Convert kg/nm -> metric tons per day: kg/nm * nm/h * 24h / 1000 kg/t
            macro_tpd = fuel_per_nm_kg * speed_arr * 24.0 / 1000.0

            # Stage 2: Micro Voyage Hydrodynamic Adjustment (draft & weather)
            adj = self.compute_adjustment_ratio(
                draft_m=draft_m,
                weather_severity=weather_severity,
                ship_type=ship_type,
                speed_kn=speed_arr,
            )
            final_tpd = macro_tpd * adj

            if is_scalar:
                return float(final_tpd[0])
            return np.asarray(final_tpd, dtype=float)

        # Fallback Path: Single-stage calibrated surrogate
        features_df = self.build_features(
            speed_arr=speed_arr,
            draft_m=draft_m,
            weather_severity=weather_severity,
            ship_type=ship_type,
            route_type=route_type,
            maintenance_status=maintenance_status,
        )

        raw_pred = self.model.predict(features_df)
        cal_pred = calibrated(raw_pred, ship_type=ship_type)

        if is_scalar:
            return float(cal_pred[0])
        return np.asarray(cal_pred, dtype=float)
