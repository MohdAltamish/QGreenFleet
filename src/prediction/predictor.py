"""Production predictor interface for the fleet optimization engine.

Two stages, and it is explicit about which parts are learned:
    1. Learned level (EU MRV model): the QPSO-XGBoost model trained on EU MRV
       THETIS ship-years predicts fuel per nautical mile (kg/nm) at the
       vessel's operating speed (its design speed; the category median speed
       when no vessel is given), from category and EEDI. A vessel's EEDI is
       estimated from its deadweight with the IMO reference lines when not
       supplied.
    2. Physics, not learning, for the rest:
       - Speed: admiralty law, fuel/day ∝ v³ (kg/nm ∝ v²). Across MRV ships
         speed is confounded with size, so the tree model cannot be trusted
         for the speed curve itself.
       - Draft: displacement scaling (T / T_ref)^(2/3).
       - Weather: sea-margin factor per sea state (calm 0.93, moderate 1.00,
         rough 1.15; moderate is the average condition MRV annual data carry,
         and ~15% is the conventional design sea margin).
       - Low engine load: below the operating speed the engine runs at part
         load (load ≈ (v / v_ref)³), where specific fuel consumption rises.
         factor = 1 + 0.15 * (1 - load)² — about +4% at 50% load and +8% at
         25%, the usual shape of 2-stroke SFOC curves. Keeps slow-steaming
         savings conservative instead of trusting the pure cube law.
       The combined draft x weather factor is clipped to [0.7, 1.3].
       tons/day = kg/nm * speed_kn * 24 / 1000.
    3. Fallback: if models/mrv_best.pkl is absent, the calibrated single-stage
       voyage model is used.
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

# Reference drafts per category: the loading condition MRV annual averages represent.
TYPE_MEAN_DRAFTS: dict[str, float] = {
    "container": 12.0,
    "bulk": 10.5,
    "tanker": 11.5,
}

# Sea-margin factor by sea state (0 calm, 1 moderate = MRV average, 2 rough).
# ponytail: fixed literature-style factors; replace with a fitted added-resistance
# model once voyage data with real weather signal is available.
WEATHER_FACTORS: tuple[float, float, float] = (0.93, 1.00, 1.15)

TWO_STAGE_NAME = "QPSO-XGBoost (EU MRV) + admiralty/sea-margin rules"

# IMO EEDI reference lines, EEDI_ref = a * capacity^(-c) (MEPC.231(65)); capacity
# is DWT, or 70% of DWT for container ships.
EEDI_REFERENCE_LINES: dict[str, tuple[float, float, float]] = {
    "bulk": (961.79, 0.477, 1.0),
    "tanker": (1218.80, 0.488, 1.0),
    "container": (174.22, 0.201, 0.7),
}


def estimate_eedi(ship_type: str, dwt: float | np.ndarray) -> np.ndarray:
    """IMO reference-line EEDI (g-CO2 / t·nm) for a vessel of this type and size."""
    a, c, share = EEDI_REFERENCE_LINES.get(normalize_type_key(ship_type), EEDI_REFERENCE_LINES["bulk"])
    return a * np.maximum(np.asarray(dwt, dtype=float) * share, 1.0) ** (-c)


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

        if self.has_mrv:
            # Headline accuracy is the MRV model scored the way the app uses it,
            # not the (signal-free) voyage model.
            self.voyage_model_name = self.model_name
            self.model_name = TWO_STAGE_NAME
            fleet = self.mrv_meta.get("fleet_inference_metrics") or self.mrv_meta.get("test_metrics", {})
            heldout = self.mrv_meta.get("test_metrics", {})
            cv = self.mrv_meta.get("cv_5fold", {})
            self.metrics = {
                "test_r2": fleet.get("r2"),
                "test_mape": fleet.get("mape"),
                "test_rmse": fleet.get("rmse"),
                "heldout_r2": heldout.get("r2"),
                "heldout_mape": heldout.get("mape"),
                "cv_rmse_mean": cv.get("rmse_mean"),
                "cv_rmse_std": cv.get("rmse_std"),
                "units": "kg/nm",
                "basis": "EU MRV held-out ships at their own speed, EEDI unknown (conservative)",
            }

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
        """Rule-based draft x weather multiplier, clipped to [0.7, 1.3].

        draft: (T / T_ref)^(2/3) — admiralty displacement scaling at constant
        block coefficient. weather: WEATHER_FACTORS interpolated over the
        0-2 sea-state scale. speed_kn only sets the output shape.
        """
        norm_type = normalize_type_key(ship_type)
        ref_draft = TYPE_MEAN_DRAFTS.get(norm_type, 11.5)
        speed_arr = np.atleast_1d(np.asarray(speed_kn, dtype=float))

        draft_arr = np.broadcast_to(np.asarray(draft_m, dtype=float), speed_arr.shape)
        weather_arr = np.broadcast_to(np.asarray(weather_severity, dtype=float), speed_arr.shape)
        draft_factor = (np.maximum(draft_arr, 0.1) / ref_draft) ** (2.0 / 3.0)
        weather_factor = np.interp(weather_arr, [0.0, 1.0, 2.0], WEATHER_FACTORS)
        adj = np.clip(draft_factor * weather_factor, 0.7, 1.3)

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
        ref_speed_kn: float | np.ndarray | None = None,
        eedi_value: float | np.ndarray | None = None,
    ) -> float | np.ndarray:
        """Predict fuel consumption in metric tons per day using two-stage surrogate.

        Args:
            speed_kn: Scalar speed or 1D array of speeds in knots.
            draft_m: Vessel draft in meters.
            weather_severity: Weather condition index (0=calm, 1=moderate, 2=rough).
            ship_type: Vessel classification ('container', 'bulk', 'tanker').
            route_type: Route type description (default 'Transoceanic').
            maintenance_status: Condition ('Fair', 'Good', 'Critical').
            ref_speed_kn: The vessel's operating (design) speed, scalar or per
                element. The learned level is taken there and the admiralty law
                scales it to speed_kn. Defaults to the category median speed.
            eedi_value: The vessel's EEDI, scalar or per element. Defaults to
                the category median (EEDI unknown).

        Returns:
            Calibrated fuel consumption in tons/day matching scalar/array input shape.
        """
        is_scalar = np.isscalar(speed_kn) or isinstance(speed_kn, (float, int))
        speed_arr = np.atleast_1d(np.asarray(speed_kn, dtype=float))
        norm_type = normalize_type_key(ship_type)

        # Stage 1: learned kg/nm level at the category reference speed,
        # then physics for speed, draft and weather.
        if self.has_mrv and self.mrv_model is not None:
            n = len(speed_arr)
            default_ref = float(self.mrv_meta.get("reference_speed_kn", {}).get(norm_type, 12.0))
            default_eedi = float(self.mrv_meta.get("fleet_defaults", {}).get(norm_type, {}).get("eedi_value", 10.0))
            v_ref = np.broadcast_to(np.asarray(default_ref if ref_speed_kn is None else ref_speed_kn, dtype=float), (n,))
            eedi = np.broadcast_to(np.asarray(default_eedi if eedi_value is None else eedi_value, dtype=float), (n,))
            rows = pd.DataFrame({
                "avg_speed_kn": v_ref,
                "speed_cubed": v_ref ** 3,
                "eedi_value": eedi,
                "category_bulk": np.full(n, int(norm_type == "bulk")),
                "category_container": np.full(n, int(norm_type == "container")),
                "category_tanker": np.full(n, int(norm_type == "tanker")),
            })
            feat_order = self.mrv_meta.get("feature_names", list(rows.columns))
            raw = self.mrv_model.predict(rows[feat_order])
            kg_nm_ref = np.expm1(raw) if self.mrv_meta.get("target_transform") == "log1p" else raw
            kg_nm_ref = np.maximum(0.1, kg_nm_ref)

            # Admiralty law: kg/nm ∝ v², so tons/day ∝ v³ — with the part-load
            # SFOC penalty below the operating speed.
            load = np.clip((speed_arr / v_ref) ** 3, 0.0, 1.0)
            sfoc_factor = 1.0 + 0.15 * (1.0 - load) ** 2
            fuel_per_nm_kg = kg_nm_ref * (speed_arr / v_ref) ** 2 * sfoc_factor
            macro_tpd = fuel_per_nm_kg * speed_arr * 24.0 / 1000.0

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
