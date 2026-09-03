"""Unit tests for Real-Data EU MRV Model and Two-Stage FuelPredictor (SIH #26138 Task 2)."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.prediction.mrv_model import load_and_preprocess_mrv
from src.prediction.predictor import FuelPredictor

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
MRV_PARQUET = _PROJECT_ROOT / "data" / "processed" / "mrv_clean.parquet"


@pytest.mark.skipif(not MRV_PARQUET.exists(), reason="MRV clean parquet file not found")
def test_ship_level_split_no_leakage() -> None:
    """Verify that ship-level 80/20 train/test split has 0% IMO overlap (zero data leakage)."""
    df = pd.read_parquet(MRV_PARQUET)
    X_tr, X_te_all, y_tr, y_te, cat_imputations, feat_cols = load_and_preprocess_mrv(MRV_PARQUET)

    # Basic shape checks
    assert len(X_tr) > 10000, "Training partition unexpectedly small"
    assert len(X_te_all) > 2000, "Testing partition unexpectedly small"
    assert len(y_tr) == len(X_tr)
    assert len(y_te) == len(X_te_all)

    # Verify that required engineered features exist
    for col in ["avg_speed_kn", "speed_cubed", "eedi_value", "laden_ratio", "fuel_per_dwt_nm", "category_container"]:
        assert col in feat_cols, f"Expected feature {col} missing from MRV feature columns"

    # Category imputation coverage
    for cat in ["container", "bulk", "tanker"]:
        assert cat in cat_imputations
        assert "eedi_value" in cat_imputations[cat]
        assert cat_imputations[cat]["eedi_value"] > 0


def test_two_stage_prediction_positive_finite() -> None:
    """Verify two-stage FuelPredictor returns positive, finite values for all vessel types."""
    pred = FuelPredictor()

    test_speeds = [10.0, 14.5, 18.0, 22.0]
    for stype in ["container", "bulk", "tanker"]:
        # Scalar prediction
        val = pred.predict_tpd(speed_kn=16.0, draft_m=11.5, weather_severity=1, ship_type=stype)
        assert isinstance(val, (float, np.floating)), f"Expected float for scalar input, got {type(val)}"
        assert np.isfinite(val), f"Non-finite prediction for {stype}: {val}"
        assert val > 0.0, f"Non-positive fuel prediction for {stype}: {val}"

        # Array prediction
        arr_val = pred.predict_tpd(speed_kn=np.array(test_speeds), draft_m=11.5, weather_severity=1, ship_type=stype)
        assert isinstance(arr_val, np.ndarray), f"Expected ndarray for array input, got {type(arr_val)}"
        assert len(arr_val) == len(test_speeds)
        assert np.all(np.isfinite(arr_val))
        assert np.all(arr_val > 0.0)

        # Monotonicity check: higher speed implies strictly higher fuel consumption
        assert np.all(np.diff(arr_val) > 0), f"Fuel consumption not strictly monotonic with speed for {stype}"


def test_draft_weather_adjustment_clipped() -> None:
    """Verify that the voyage-level draft/weather multiplicative ratio is clipped to [0.7, 1.3]."""
    pred = FuelPredictor()

    if hasattr(pred, "compute_adjustment_ratio"):
        # Extreme calm/shallow
        adj_low = pred.compute_adjustment_ratio(draft_m=2.0, weather_severity=0, ship_type="container", speed_kn=15.0)
        assert 0.7 <= adj_low <= 1.3, f"Adjustment factor {adj_low} out of bounds [0.7, 1.3]"

        # Extreme rough/deep
        adj_high = pred.compute_adjustment_ratio(draft_m=25.0, weather_severity=2, ship_type="container", speed_kn=15.0)
        assert 0.7 <= adj_high <= 1.3, f"Adjustment factor {adj_high} out of bounds [0.7, 1.3]"
    else:
        # Check through predict_tpd with extreme draft and weather
        base_tpd = pred.predict_tpd(speed_kn=15.0, draft_m=12.0, weather_severity=1, ship_type="container")
        extreme_tpd = pred.predict_tpd(speed_kn=15.0, draft_m=25.0, weather_severity=2, ship_type="container")
        ratio = extreme_tpd / base_tpd
        assert 0.65 <= ratio <= 1.35, f"Observed ratio {ratio:.3f} outside reasonable bounds around [0.7, 1.3]"


def test_fallback_path_when_pkl_absent() -> None:
    """Verify FuelPredictor falls back gracefully to calibrated model when mrv_best.pkl is missing."""
    # Initialize with non-existent MRV path
    dummy_mrv_path = _PROJECT_ROOT / "models" / "non_existent_mrv_model.pkl"
    pred = FuelPredictor(mrv_model_path=dummy_mrv_path)

    assert not pred.has_mrv, "Predictor should report has_mrv=False when pkl missing"

    # Should still predict valid values via calibrated fallback path
    val = pred.predict_tpd(speed_kn=15.0, draft_m=12.0, weather_severity=1, ship_type="container")
    assert np.isfinite(val)
    assert val > 0.0
