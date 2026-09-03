"""Unit tests for src.prediction modules using small synthetic datasets."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split

from src.prediction.calibration import calibrated, load_calibration_factors, normalize_type_key
from src.prediction.models import PhysicsBaseline
from src.prediction.predictor import FuelPredictor
from src.prediction.qpso_tuner import QPSOSearchSpace, qpso_tune_xgboost


# ===================================================================== #
#  1. Physics Baseline Test                                              #
# ===================================================================== #
def test_physics_baseline_recovers_cubic_relationship() -> None:
    """Physics baseline must recover exact cubic relationship (R² > 0.99)."""
    rng = np.random.default_rng(42)
    n = 100

    speed = rng.uniform(8.0, 22.0, size=n)
    speed_cubed = speed ** 3
    draft = rng.uniform(6.0, 15.0, size=n)

    # Noiseless synthetic ground truth: fuel = 0.003 * speed^3 + 1.5 * draft + 2.0
    y = 0.003 * speed_cubed + 1.5 * draft + 2.0

    df = pd.DataFrame({
        "speed_kn": speed,
        "speed_cubed": speed_cubed,
        "draft_m": draft,
        "weather_severity": rng.integers(0, 3, size=n),
    })

    model = PhysicsBaseline(feature_names=list(df.columns))
    model.fit(df, y)
    preds = model.predict(df)

    r2 = r2_score(y, preds)
    assert r2 > 0.99, f"Physics baseline R² was {r2:.4f}, expected > 0.99"


# ===================================================================== #
#  2. QPSO Hyperparameter Optimization Tests                            #
# ===================================================================== #
def test_qpso_search_space_bounds() -> None:
    """Decoded hyperparameter values must strictly satisfy domain constraints."""
    space = QPSOSearchSpace(n_estimators_max=800)

    # Test lower boundaries
    zeros = np.zeros(space.DIMENSION)
    p_min = space.decode(zeros)
    assert p_min["learning_rate"] == pytest.approx(0.01)
    assert p_min["max_depth"] == 3
    assert p_min["subsample"] == pytest.approx(0.5)
    assert p_min["colsample_bytree"] == pytest.approx(0.5)
    assert p_min["n_estimators"] == 100
    assert p_min["min_child_weight"] == 1

    # Test upper boundaries
    ones = np.ones(space.DIMENSION)
    p_max = space.decode(ones)
    assert p_max["learning_rate"] == pytest.approx(0.3)
    assert p_max["max_depth"] == 10
    assert p_max["subsample"] == pytest.approx(1.0)
    assert p_max["colsample_bytree"] == pytest.approx(1.0)
    assert p_max["n_estimators"] == 800
    assert p_max["min_child_weight"] == 10


def test_qpso_beta_decay_and_monotonic_convergence() -> None:
    """QPSO beta decay must match endpoints and gbest fitness must be non-increasing."""
    n_iter = 10
    beta_start = 1.0
    beta_end = 0.4

    betas = [
        beta_start - (t / (n_iter - 1)) * (beta_start - beta_end)
        for t in range(n_iter)
    ]
    assert betas[0] == pytest.approx(1.0)
    assert betas[-1] == pytest.approx(0.4)

    # Run small synthetic tuning job (10 samples, 4 particles, 5 iterations)
    rng = np.random.default_rng(123)
    X = pd.DataFrame(rng.normal(size=(40, 5)), columns=[f"feat_{i}" for i in range(5)])
    y = rng.uniform(10.0, 50.0, size=40)

    best_params, history = qpso_tune_xgboost(
        X,
        y,
        n_particles=4,
        n_iterations=5,
        seed=42,
        verbose=False,
    )

    # History length = initial eval (iter 0) + 5 iterations = 6
    assert len(history) == 6

    # Verify monotonic non-increasing property for gbest
    for i in range(len(history) - 1):
        assert history[i] >= history[i + 1] - 1e-9, (
            f"History increased at index {i}: {history[i]} -> {history[i+1]}"
        )

    # Check that decoded best parameters satisfy bounds
    space = QPSOSearchSpace()
    assert 0.01 <= best_params["learning_rate"] <= 0.3
    assert 3 <= best_params["max_depth"] <= 10
    assert 0.5 <= best_params["subsample"] <= 1.0


# ===================================================================== #
#  3. FuelPredictor Interface & Calibration Tests                       #
# ===================================================================== #
def test_fuel_predictor_assembly_and_calibration(tmp_path: Path) -> None:
    """Predictor must assemble features in metadata order and apply calibration."""
    feature_columns = [
        "speed_kn",
        "speed_cubed",
        "draft_m",
        "weather_severity",
        "type_Bulk Carrier",
        "type_Container Ship",
        "type_Tanker",
        "route_Transoceanic",
        "maint_Fair",
    ]

    # Create dummy linear model predicting: speed_kn * 2.0
    # Coefficients: [2.0, 0, 0, 0, 0, 0, 0, 0, 0]
    reg = LinearRegression(fit_intercept=False)
    reg.coef_ = np.array([2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    reg.intercept_ = 0.0

    model_path = tmp_path / "best.pkl"
    meta_path = tmp_path / "best_meta.json"

    joblib.dump(reg, model_path)
    meta = {
        "model_name": "TestModel",
        "feature_columns": feature_columns,
        "metrics": {"test_rmse": 0.5},
    }
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    predictor = FuelPredictor(model_path=model_path, meta_path=meta_path)

    # 1. Feature assembly check
    features_df = predictor.build_features(
        speed_arr=np.array([12.0]),
        draft_m=10.5,
        weather_severity=1,
        ship_type="Container Ship",
    )
    assert list(features_df.columns) == feature_columns
    assert features_df["type_Container Ship"].iloc[0] == 1
    assert features_df["type_Bulk Carrier"].iloc[0] == 0
    assert features_df["speed_cubed"].iloc[0] == 12.0 ** 3

    # 2. Calibration factor application check
    # Raw prediction for speed 10.0 = 20.0 tons/day
    factors = load_calibration_factors()
    expected_cal = 20.0 * factors["container"]

    cal_scalar = predictor.predict_tpd(
        speed_kn=10.0,
        draft_m=10.0,
        weather_severity=0,
        ship_type="container",
    )
    assert isinstance(cal_scalar, float)
    assert cal_scalar == pytest.approx(expected_cal, rel=1e-3)

    # 3. Vectorized speed input check
    speeds = np.array([10.0, 15.0, 20.0])
    cal_vector = predictor.predict_tpd(
        speed_kn=speeds,
        draft_m=10.0,
        weather_severity=0,
        ship_type="container",
    )
    assert isinstance(cal_vector, np.ndarray)
    assert cal_vector.shape == (3,)
    assert cal_vector[0] == pytest.approx(expected_cal, rel=1e-3)
    assert cal_vector[1] == pytest.approx(30.0 * factors["container"], rel=1e-3)


def test_calibration_unknown_type_raises() -> None:
    """Unknown ship type must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown ship type"):
        calibrated(100.0, "Spaceship")


# ===================================================================== #
#  4. Stratified Split Test                                             #
# ===================================================================== #
def test_stratified_train_test_split() -> None:
    """Train/test split must preserve ship type proportions within 2%."""
    n = 1000
    # Proportions: 40% bulk, 30% container, 20% tanker, 10% other
    ship_types = np.array(
        ["bulk"] * 400 + ["container"] * 300 + ["tanker"] * 200 + ["other"] * 100
    )
    df = pd.DataFrame({
        "feat1": np.arange(n),
        "ship_type": ship_types,
        "fuel_tpd": np.random.default_rng(42).uniform(10, 50, size=n),
    })

    train_df, test_df = train_test_split(
        df,
        test_size=0.20,
        random_state=42,
        stratify=df["ship_type"],
    )

    orig_dist = df["ship_type"].value_counts(normalize=True).to_dict()
    train_dist = train_df["ship_type"].value_counts(normalize=True).to_dict()
    test_dist = test_df["ship_type"].value_counts(normalize=True).to_dict()

    for k in orig_dist:
        assert abs(train_dist[k] - orig_dist[k]) < 0.02, (
            f"Train proportion for {k} diverged by {abs(train_dist[k] - orig_dist[k]):.4f}"
        )
        assert abs(test_dist[k] - orig_dist[k]) < 0.02, (
            f"Test proportion for {k} diverged by {abs(test_dist[k] - orig_dist[k]):.4f}"
        )
