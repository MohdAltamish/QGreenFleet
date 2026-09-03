"""Training and evaluation pipeline for vessel fuel consumption models.

Executes cross-validation, test set evaluation, model artifact serialization,
report generation, and diagnostic parity/convergence plotting.

Usage::

    python -m src.prediction.train --model all --seed 42
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

# Ensure headless matplotlib configuration
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_percentage_error, r2_score, root_mean_squared_error
from sklearn.model_selection import KFold, train_test_split

from src.prediction.models import (
    BaseModel,
    PhysicsBaseline,
    QPSOXGBoost,
    RandomForestModel,
    XGBoostModel,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = _PROJECT_ROOT / "data" / "processed" / "voyages_clean.parquet"
DEFAULT_MODELS_DIR = _PROJECT_ROOT / "models"
DEFAULT_OUTPUTS_DIR = _PROJECT_ROOT / "outputs"


def load_dataset(data_path: Path) -> tuple[pd.DataFrame, pd.Series, pd.Series, list[str]]:
    """Load processed voyage dataset and prepare feature/target matrices.

    Args:
        data_path: Path to voyages_clean.parquet.

    Returns:
        Tuple of (X, y, ship_type_series, feature_columns).

    Raises:
        FileNotFoundError: If the clean dataset is not present.
    """
    if not data_path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {data_path}.\n"
            "Please run 'python -m src.data.prepare' first to generate clean Parquet files."
        )

    df = pd.read_parquet(data_path)
    if "fuel_tpd" not in df.columns:
        raise ValueError(f"Target column 'fuel_tpd' not found in {data_path}.")

    y = df["fuel_tpd"]
    feature_cols = [c for c in df.columns if c != "fuel_tpd"]
    X = df[feature_cols].copy()

    # Reconstruct categorical ship type from one-hot columns for stratified split
    type_cols = [c for c in feature_cols if c.startswith("type_")]
    if type_cols:
        ship_types = df[type_cols].idxmax(axis=1).str.replace("type_", "", regex=False)
    else:
        ship_types = pd.Series("unknown", index=df.index)

    return X, y, ship_types, feature_cols


def evaluate_cv(
    model_factory: Any,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    n_splits: int = 5,
    seed: int = 42,
) -> tuple[float, float]:
    """Perform K-fold cross-validation on the training set.

    Args:
        model_factory: Callable returning a fresh model instance.
        X_train: Training feature DataFrame.
        y_train: Training target Series.
        n_splits: Number of CV folds (default 5).
        seed: Random seed.

    Returns:
        Tuple of (mean_cv_rmse, std_cv_rmse).
    """
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=seed)
    rmses: list[float] = []

    for tr_idx, va_idx in kf.split(X_train):
        X_tr, y_tr = X_train.iloc[tr_idx], y_train.iloc[tr_idx]
        X_va, y_va = X_train.iloc[va_idx], y_train.iloc[va_idx]

        model = model_factory()
        model.fit(X_tr, y_tr)
        preds = model.predict(X_va)
        rmse = float(root_mean_squared_error(y_va, preds))
        rmses.append(rmse)

    return float(np.mean(rmses)), float(np.std(rmses))


def plot_parity(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    model_name: str,
    metrics: dict[str, float],
    output_path: Path,
) -> None:
    """Save a parity scatter plot (actual vs predicted) on the test set.

    Args:
        y_true: Ground truth fuel consumption values.
        y_pred: Predicted values.
        model_name: Name of model for plot title.
        metrics: Metric dictionary (RMSE, MAPE, R2).
        output_path: Destination PNG filepath.
    """
    fig, ax = plt.subplots(figsize=(6, 6))

    ax.scatter(y_true, y_pred, alpha=0.4, edgecolors="none", c="#1f77b4", s=30)
    min_val = min(float(np.min(y_true)), float(np.min(y_pred)))
    max_val = max(float(np.max(y_true)), float(np.max(y_pred)))
    margin = (max_val - min_val) * 0.05
    line_min = min_val - margin
    line_max = max_val + margin

    ax.plot([line_min, line_max], [line_min, line_max], "r--", lw=1.5, label="1:1 Parity")
    ax.set_xlim(line_min, line_max)
    ax.set_ylim(line_min, line_max)
    ax.set_xlabel("Actual Fuel Consumption (tons/day)")
    ax.set_ylabel("Predicted Fuel Consumption (tons/day)")
    ax.set_title(f"Parity Plot: {model_name}")

    text_box = (
        f"Test RMSE: {metrics['test_rmse']:.3f}\n"
        f"Test MAPE: {metrics['test_mape']:.2f}%\n"
        f"Test R²:   {metrics['test_r2']:.4f}"
    )
    ax.text(
        0.05,
        0.95,
        text_box,
        transform=ax.transAxes,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        fontsize=9,
    )

    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="lower right")
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_qpso_convergence(history: list[float], output_path: Path) -> None:
    """Save QPSO optimization convergence curve.

    Args:
        history: List of gbest RMSE values per iteration.
        output_path: Destination PNG filepath.
    """
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(range(len(history)), history, "o-", color="#2ca02c", lw=2, markersize=4)
    ax.set_xlabel("QPSO Iteration")
    ax.set_ylabel("Global Best CV RMSE (tons/day)")
    ax.set_title("QPSO XGBoost Hyperparameter Convergence")
    ax.grid(True, linestyle=":", alpha=0.6)

    min_val = min(history)
    ax.annotate(
        f"Min RMSE: {min_val:.4f}",
        xy=(len(history) - 1, min_val),
        xytext=(len(history) * 0.65, min_val * 1.05),
        arrowprops=dict(arrowstyle="->", color="black"),
        fontsize=9,
    )

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def train_pipeline(
    model_choice: str = "all",
    seed: int = 42,
    data_path: Path = DEFAULT_DATA_PATH,
    models_dir: Path = DEFAULT_MODELS_DIR,
    outputs_dir: Path = DEFAULT_OUTPUTS_DIR,
    qpso_particles: int = 15,
    qpso_iterations: int = 25,
) -> dict[str, Any]:
    """Execute complete model training, evaluation, and reporting pipeline.

    Args:
        model_choice: Model to train ("physics", "rf", "xgb", "qpso_xgb", "all").
        seed: Random seed for reproducibility.
        data_path: Parquet dataset location.
        models_dir: Directory to save serialized model artifacts.
        outputs_dir: Directory for reports and plots.
        qpso_particles: Swarm size for QPSO tuning.
        qpso_iterations: Iteration budget for QPSO tuning.

    Returns:
        Dictionary of results and evaluated model objects.
    """
    print("=" * 65)
    print("QGreenFleet Fuel Consumption Model Training Pipeline")
    print(f"Model Selection: {model_choice} | Random Seed: {seed}")
    print("=" * 65)

    X, y, ship_types, feature_cols = load_dataset(data_path)
    print(f"Loaded {len(X)} records with {len(feature_cols)} features.")

    # 80/20 Stratified Split
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=seed,
        stratify=ship_types,
    )
    print(f"Dataset split: {len(X_train)} train rows, {len(X_test)} test rows.")

    models_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # Models catalog mapping
    model_definitions: dict[str, tuple[str, Any]] = {
        "physics": (
            "PhysicsBaseline",
            lambda: PhysicsBaseline(feature_names=feature_cols),
        ),
        "rf": (
            "RandomForestModel",
            lambda: RandomForestModel(n_estimators=300, random_state=seed),
        ),
        "xgb": (
            "XGBoostModel",
            lambda: XGBoostModel(
                n_estimators=500,
                learning_rate=0.05,
                max_depth=6,
                subsample=0.9,
                random_state=seed,
            ),
        ),
        "qpso_xgb": (
            "QPSOXGBoost",
            lambda: QPSOXGBoost(
                n_particles=qpso_particles,
                n_iterations=qpso_iterations,
                random_state=seed,
                verbose=True,
            ),
        ),
    }

    active_keys: list[str] = (
        list(model_definitions.keys()) if model_choice == "all" else [model_choice]
    )

    results: list[dict[str, Any]] = []
    fitted_models: dict[str, BaseModel] = {}
    qpso_history: list[float] = []

    for key in active_keys:
        if key not in model_definitions:
            raise ValueError(
                f"Unknown model key '{key}'. Available: {list(model_definitions.keys())}"
            )

        name, factory = model_definitions[key]
        print(f"\nEvaluating {name} ({key})...")

        # 5-fold CV evaluation on training set (physics, rf, xgb)
        # Note: for QPSO, the internal tuning uses 3-fold CV, but we also benchmark 5-fold CV
        cv_mean, cv_std = evaluate_cv(factory, X_train, y_train, n_splits=5, seed=seed)
        print(f"  5-fold CV RMSE: {cv_mean:.4f} ± {cv_std:.4f}")

        # Fit final model on the full training set
        model = factory()
        model.fit(X_train, y_train)
        fitted_models[key] = model

        # Test set evaluation
        test_preds = model.predict(X_test)
        test_rmse = float(root_mean_squared_error(y_test, test_preds))
        test_mape = float(mean_absolute_percentage_error(y_test, test_preds) * 100.0)
        test_r2 = float(r2_score(y_test, test_preds))

        metrics = {
            "cv_rmse_mean": cv_mean,
            "cv_rmse_std": cv_std,
            "test_rmse": test_rmse,
            "test_mape": test_mape,
            "test_r2": test_r2,
        }

        print(f"  Test RMSE: {test_rmse:.4f} | Test MAPE: {test_mape:.2f}% | Test R²: {test_r2:.4f}")

        # Plot parity
        parity_path = outputs_dir / f"parity_{key}.png"
        plot_parity(y_test.values, test_preds, name, metrics, parity_path)
        print(f"  Parity plot saved to {parity_path}")

        # Record QPSO convergence if applicable
        if key == "qpso_xgb" and hasattr(model, "convergence_history_"):
            qpso_history = model.convergence_history_
            if qpso_history:
                conv_path = outputs_dir / "qpso_convergence.png"
                plot_qpso_convergence(qpso_history, conv_path)
                print(f"  QPSO convergence plot saved to {conv_path}")

        results.append({
            "key": key,
            "name": name,
            "model": model,
            "metrics": metrics,
        })

    # Display comparison table
    print("\n" + "=" * 80)
    print(f"{'Model':<20} | {'5-Fold CV RMSE':<18} | {'Test RMSE':<10} | {'Test MAPE (%)':<14} | {'Test R²':<8}")
    print("-" * 80)
    for r in results:
        m = r["metrics"]
        cv_str = f"{m['cv_rmse_mean']:.4f} ± {m['cv_rmse_std']:.4f}"
        print(f"{r['name']:<20} | {cv_str:<18} | {m['test_rmse']:<10.4f} | {m['test_mape']:<14.2f} | {m['test_r2']:<8.4f}")
    print("=" * 80)

    # Identify best model by test RMSE
    best_entry = min(results, key=lambda x: x["metrics"]["test_rmse"])
    best_key = best_entry["key"]
    best_model = best_entry["model"]
    best_name = best_entry["name"]
    best_metrics = best_entry["metrics"]

    print(f"\nBest Model: {best_name} (Test RMSE: {best_metrics['test_rmse']:.4f})")

    # Serialize best model & metadata
    best_model_path = models_dir / "best.pkl"
    best_meta_path = models_dir / "best_meta.json"

    joblib.dump(best_model, best_model_path)
    print(f"Serialized best model to {best_model_path}")

    meta_payload = {
        "model_name": best_name,
        "model_key": best_key,
        "params": best_model.get_params(),
        "feature_columns": feature_cols,
        "metrics": best_metrics,
        "seed": seed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    best_meta_path.write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")
    print(f"Saved metadata to {best_meta_path}")

    # Generate prediction report markdown
    report_path = outputs_dir / "prediction_report.md"
    _generate_report(results, qpso_history, best_entry, report_path)
    print(f"Markdown report generated at {report_path}")

    return {
        "results": results,
        "best_entry": best_entry,
        "feature_cols": feature_cols,
    }


def _generate_report(
    results: list[dict[str, Any]],
    qpso_history: list[float],
    best_entry: dict[str, Any],
    report_path: Path,
) -> None:
    """Write markdown summary report."""
    lines: list[str] = [
        "# Fuel Consumption Prediction Benchmark Report",
        "",
        f"*Generated on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*",
        "",
        "## 1. Model Performance Comparison",
        "",
        "| Model | 5-Fold CV RMSE (tons/day) | Test RMSE (tons/day) | Test MAPE (%) | Test R² |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in results:
        m = r["metrics"]
        lines.append(
            f"| **{r['name']}** | {m['cv_rmse_mean']:.4f} ± {m['cv_rmse_std']:.4f} | "
            f"{m['test_rmse']:.4f} | {m['test_mape']:.2f}% | {m['test_r2']:.4f} |"
        )

    lines.extend([
        "",
        f"**Selected Best Model:** `{best_entry['name']}` with Test RMSE = `{best_entry['metrics']['test_rmse']:.4f}` tons/day.",
        "",
        "## 2. Parity Visualizations",
        "",
    ])

    for r in results:
        lines.append(f"- **{r['name']}**: `outputs/parity_{r['key']}.png`")

    if qpso_history:
        lines.extend([
            "",
            "## 3. QPSO Hyperparameter Optimization History",
            "",
            "| Iteration | Best CV RMSE (tons/day) |",
            "| :--- | :--- |",
        ])
        for idx, val in enumerate(qpso_history):
            lines.append(f"| {idx} | {val:.4f} |")
        lines.extend([
            "",
            "Convergence curve plotted in `outputs/qpso_convergence.png`.",
        ])

    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Train and benchmark vessel fuel prediction models.")
    parser.add_argument(
        "--model",
        type=str,
        default="all",
        choices=["physics", "rf", "xgb", "qpso_xgb", "all"],
        help="Model to train (default: all)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--data-path", type=Path, default=DEFAULT_DATA_PATH, help="Path to voyages Parquet")
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR, help="Directory to save models")
    parser.add_argument("--outputs-dir", type=Path, default=DEFAULT_OUTPUTS_DIR, help="Directory for reports/plots")
    parser.add_argument("--qpso-particles", type=int, default=15, help="QPSO swarm size")
    parser.add_argument("--qpso-iterations", type=int, default=25, help="QPSO iterations")

    args = parser.parse_args()

    try:
        train_pipeline(
            model_choice=args.model,
            seed=args.seed,
            data_path=args.data_path,
            models_dir=args.models_dir,
            outputs_dir=args.outputs_dir,
            qpso_particles=args.qpso_particles,
            qpso_iterations=args.qpso_iterations,
        )
    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
