"""Real-Data EU MRV Prediction Engine (SIH #26138 Task 2).

Trains XGBoost and QPSO-tuned XGBoost surrogates directly on 21,622 verified
EU MRV THETIS operational records with strict ship-level (zero data leakage)
train/test splitting.

Target:
    fuel_per_nm_kg: Annual operational fuel consumption in kg per nautical mile
    (fitted on log1p scale; metrics reported on the original scale).

Features:
    avg_speed_kn, avg_speed_kn**3 (both monotone-increasing), eedi_value,
    category (one-hot: container, bulk, tanker).

    fuel_per_dwt_nm and laden_ratio are deliberately excluded: the first is the
    target divided by deadweight (leakage when present, 90% missing otherwise)
    and neither is known for a fleet vessel at inference time.

Two accuracy figures are reported, because they answer different questions:
    - test_metrics: held-out ships, with each ship's own EEDI where MRV has it.
    - fleet_inference_metrics: the same ships with EEDI unknown (category
      median), the case for a vessel whose EEDI cannot be estimated.
    Both score each ship at its own operating speed. Changes of speed around
    that point follow the admiralty law (predictor.py), which annual MRV
    averages cannot validate because, across ships, speed tracks size.

Usage::

    python -m src.prediction.mrv_model
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pickle
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score, root_mean_squared_error
from sklearn.model_selection import GroupKFold, train_test_split
import xgboost as xgb

from src.prediction.qpso_tuner import qpso_tune_xgboost

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
cache_dir = _PROJECT_ROOT / ".cache" / "matplotlib"
cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))

DEFAULT_PARQUET = _PROJECT_ROOT / "data" / "processed" / "mrv_clean.parquet"
DEFAULT_MODELS_DIR = _PROJECT_ROOT / "models"
DEFAULT_OUTPUTS_DIR = _PROJECT_ROOT / "outputs"

FEATURES = [
    "avg_speed_kn",
    "speed_cubed",
    "eedi_value",
    "category_bulk",
    "category_container",
    "category_tanker",
]
# Fuel per nm must not fall as speed rises (monotone +1 on both speed terms).
MONOTONE = "(" + ",".join("1" if f in ("avg_speed_kn", "speed_cubed") else "0" for f in FEATURES) + ")"
XGB_FIXED = {"monotone_constraints": MONOTONE}


def load_and_preprocess_mrv(
    parquet_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, dict[str, dict[str, float]], list[str]]:
    """Load EU MRV dataset, impute per-category medians, and perform ship-level split.

    Guarantees 0% IMO overlap between train and test sets (zero data leakage).

    Returns:
        (X_train, X_test, y_train, y_test, imputation_dict, feature_columns)
    """
    df = pd.read_parquet(parquet_path)

    # 1. Clean invalid targets and speeds
    df = df.dropna(subset=["fuel_per_nm_kg", "avg_speed_kn"]).copy()
    df = df[(df["fuel_per_nm_kg"] > 0) & (df["avg_speed_kn"] > 3.0) & (df["avg_speed_kn"] < 35.0)]
    # EEDI above 100 g-CO2/(t·nm) is a spreadsheet parse artefact (max seen: 4,012).
    df.loc[df["eedi_value"] > 100.0, "eedi_value"] = np.nan

    # 2. Ship-level stratified train/test split (80/20) by primary category
    ship_categories = df.groupby("imo")["category"].agg(lambda s: s.mode()[0] if not s.mode().empty else s.iloc[0])
    unique_imos = ship_categories.index.to_numpy()
    unique_cats = ship_categories.to_numpy()

    train_imos, test_imos = train_test_split(
        unique_imos,
        test_size=0.20,
        random_state=42,
        stratify=unique_cats,
    )

    # Verify zero ship overlap
    assert len(set(train_imos).intersection(set(test_imos))) == 0, "Data leakage: IMO overlap detected!"

    train_df = df[df["imo"].isin(train_imos)].copy()
    test_df = df[df["imo"].isin(test_imos)].copy()

    # 3. Compute per-category median imputation on TRAIN only to prevent leakage
    impute_cols = ["eedi_value"]
    cat_imputations: dict[str, dict[str, float]] = {}

    for cat in ["bulk", "container", "tanker"]:
        cat_imputations[cat] = {}
        cat_sub = train_df[train_df["category"] == cat]
        for col in impute_cols:
            med_val = float(cat_sub[col].median()) if not cat_sub[col].dropna().empty else 0.0
            cat_imputations[cat][col] = med_val

    # Global fallbacks if needed
    global_meds = {col: float(train_df[col].median()) for col in impute_cols}

    def apply_imputation(d_in: pd.DataFrame) -> pd.DataFrame:
        d = d_in.copy()
        for col in impute_cols:
            for cat, vals in cat_imputations.items():
                mask = (d["category"] == cat) & (d[col].isna() | np.isinf(d[col]))
                d.loc[mask, col] = vals.get(col, global_meds[col])
            # Remaining NaNs
            d[col] = d[col].fillna(global_meds[col])
        return d

    train_df = apply_imputation(train_df)
    test_df = apply_imputation(test_df)

    # 4. Engineer features
    def build_features(d_in: pd.DataFrame) -> pd.DataFrame:
        d = d_in.copy()
        d["speed_cubed"] = d["avg_speed_kn"] ** 3
        # One-hot encode category
        d["category_bulk"] = (d["category"] == "bulk").astype(int)
        d["category_container"] = (d["category"] == "container").astype(int)
        d["category_tanker"] = (d["category"] == "tanker").astype(int)

        return d[FEATURES]

    X_train = build_features(train_df)
    X_test = build_features(test_df)
    y_train = train_df["fuel_per_nm_kg"].astype(float)
    y_test = test_df["fuel_per_nm_kg"].astype(float)

    # Preserve category in test for breakdown reporting; ship IMO on train for
    # grouped cross-validation (pandas attrs keep the public return shape).
    X_test_with_cat = X_test.copy()
    X_test_with_cat["category"] = test_df["category"].values
    X_train.attrs["groups"] = train_df["imo"].to_numpy()
    X_train.attrs["category"] = train_df["category"].to_numpy()

    return X_train, X_test_with_cat, y_train, y_test, cat_imputations, list(X_train.columns)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute RMSE, MAPE, and R2 regression metrics."""
    rmse = float(root_mean_squared_error(y_true, y_pred))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.maximum(y_true, 1e-6))) * 100.0)
    r2 = float(r2_score(y_true, y_pred))
    return {"rmse": rmse, "mape": mape, "r2": r2}


def train_and_evaluate(
    parquet_path: Path = DEFAULT_PARQUET,
    models_dir: Path = DEFAULT_MODELS_DIR,
    outputs_dir: Path = DEFAULT_OUTPUTS_DIR,
    run_qpso: bool = True,
) -> dict[str, Any]:
    """Train Default and QPSO-Tuned XGBoost models on EU MRV data and export reports."""
    print("=" * 70)
    print("Training EU MRV fuel prediction model")
    print("=" * 70)

    models_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    X_tr, X_te_all, y_tr, y_te, cat_imputations, feat_cols = load_and_preprocess_mrv(parquet_path)
    X_te = X_te_all[feat_cols].copy()
    categories_te = X_te_all["category"].to_numpy()

    print(f"Loaded MRV clean dataset: Train shape {X_tr.shape}, Test shape {X_te.shape}")

    groups_tr = X_tr.attrs["groups"]
    cats_tr = X_tr.attrs["category"]

    def fit(params: dict[str, Any], X: pd.DataFrame, y: pd.Series) -> xgb.XGBRegressor:
        m = xgb.XGBRegressor(**params, **XGB_FIXED, random_state=42, n_jobs=-1, tree_method="hist")
        m.fit(X, np.log1p(y))
        return m

    def predict(m: xgb.XGBRegressor, X: pd.DataFrame) -> np.ndarray:
        return np.expm1(m.predict(X))

    # 1. Default-hyperparameter XGBoost (same features and constraints)
    print("\n--- Training Default XGBoost Baseline ---")
    default_params = {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8}
    default_xgb = fit(default_params, X_tr, y_tr)
    pred_def_te = predict(default_xgb, X_te)
    metrics_def = compute_metrics(y_te.to_numpy(), pred_def_te)
    print(f"Default XGBoost Test: R²={metrics_def['r2']:.4f} | MAPE={metrics_def['mape']:.2f}% | RMSE={metrics_def['rmse']:.2f} kg/nm")

    # 2. QPSO hyperparameter search (ship-grouped folds, same constraints)
    best_params = dict(default_params)
    if run_qpso:
        print("\n--- Running Quantum-behaved PSO Hyperparameter Tuning ---")
        best_params, _ = qpso_tune_xgboost(
            X=X_tr,
            y=y_tr,
            n_particles=10,
            n_iterations=15,
            n_splits=3,
            n_estimators_max=500,
            seed=42,
            verbose=True,
            groups=groups_tr,
            fixed_params=XGB_FIXED,
            log_target=True,
        )
        print(f"QPSO Optimal Hyperparameters: {best_params}")

    # 3. Fit final model
    print("\n--- Fitting Final QPSO-Tuned XGBoost Model ---")
    best_model = fit(best_params, X_tr, y_tr)
    pred_best_te = predict(best_model, X_te)
    metrics_best = compute_metrics(y_te.to_numpy(), pred_best_te)
    print(f"QPSO-XGBoost Test: R²={metrics_best['r2']:.4f} | MAPE={metrics_best['mape']:.2f}% | RMSE={metrics_best['rmse']:.2f} kg/nm")

    # 5-fold CV grouped by ship, so no vessel's other years sit in validation
    cv_rmses = []
    for tr_idx, va_idx in GroupKFold(n_splits=5).split(X_tr, groups=groups_tr):
        m = fit(best_params, X_tr.iloc[tr_idx], y_tr.iloc[tr_idx])
        cv_rmses.append(float(root_mean_squared_error(y_tr.iloc[va_idx], predict(m, X_tr.iloc[va_idx]))))
    cv_mean = float(np.mean(cv_rmses))
    cv_std = float(np.std(cv_rmses))
    print(f"5-Fold ship-grouped CV RMSE: {cv_mean:.2f} ± {cv_std:.2f} kg/nm")

    # Reference speed per category = training median; the app evaluates the
    # model there and applies speed through the admiralty law.
    reference_speed = {
        cat: float(np.median(X_tr["avg_speed_kn"].to_numpy()[cats_tr == cat])) for cat in ["bulk", "container", "tanker"]
    }

    # Level accuracy when EEDI is unknown: held-out ships at their own
    # operating speed, EEDI replaced by the category median. (The speed
    # response around that operating point is the admiralty law, which MRV
    # annual averages cannot test — across ships, speed tracks size.)
    y_te_arr = y_te.to_numpy()
    X_unknown = X_te.copy()
    X_unknown["eedi_value"] = [cat_imputations[c]["eedi_value"] for c in categories_te]
    metrics_fleet = compute_metrics(y_te_arr, predict(best_model, X_unknown))

    # Naive reference: each category's training median kg/nm.
    naive_pred = np.array([float(np.median(y_tr.to_numpy()[cats_tr == c])) for c in categories_te])
    metrics_naive = compute_metrics(y_te_arr, naive_pred)
    print(
        f"Fleet-inference Test: R²={metrics_fleet['r2']:.4f} | MAPE={metrics_fleet['mape']:.2f}% "
        f"(category-median baseline R²={metrics_naive['r2']:.4f}, MAPE={metrics_naive['mape']:.2f}%)"
    )

    # Per-category performance breakdown
    cat_breakdown: dict[str, dict[str, float]] = {}
    for cat in ["container", "bulk", "tanker"]:
        cat_mask = categories_te == cat
        if np.any(cat_mask):
            cat_m = compute_metrics(y_te_arr[cat_mask], pred_best_te[cat_mask])
            cat_breakdown[cat] = cat_m
            print(f"[{cat.upper():<9}] Test: R²={cat_m['r2']:.4f} | MAPE={cat_m['mape']:.2f}% | RMSE={cat_m['rmse']:.2f} kg/nm (N={np.sum(cat_mask)})")

    # 4. Save Model Artifacts
    model_pkl_path = models_dir / "mrv_best.pkl"
    meta_json_path = models_dir / "mrv_best_meta.json"

    with open(model_pkl_path, "wb") as f:
        pickle.dump(best_model, f)  # predicts log1p(kg/nm); see meta["target_transform"]
    print(f"\nSaved best model to {model_pkl_path}")

    meta_dict = {
        "model_type": "QPSO-XGBoost",
        "dataset": f"EU MRV THETIS ({len(X_tr) + len(X_te):,} ship-years, ship-level 80/20 split)",
        "train_samples": len(X_tr),
        "test_samples": len(X_te),
        "target": "fuel_per_nm_kg",
        "target_transform": "log1p",
        "monotone_constraints": MONOTONE,
        "test_metrics": metrics_best,
        "fleet_inference_metrics": metrics_fleet,
        "category_median_baseline_metrics": metrics_naive,
        "default_xgb_metrics": metrics_def,
        "cv_5fold": {"rmse_mean": cv_mean, "rmse_std": cv_std, "grouped_by": "imo"},
        "per_category": cat_breakdown,
        "hyperparameters": best_params,
        "feature_names": feat_cols,
        "category_imputations": cat_imputations,
        "reference_speed_kn": reference_speed,
        # EEDI is unknown for fleet vessels, so inference uses the category median.
        "fleet_defaults": {cat: {"eedi_value": vals["eedi_value"]} for cat, vals in cat_imputations.items()},
    }
    meta_json_path.write_text(json.dumps(meta_dict, indent=2), encoding="utf-8")
    print(f"Saved model metadata to {meta_json_path}")

    # 5. Generate Parity Plot (outputs/parity_mrv.png)
    parity_path = outputs_dir / "parity_mrv.png"
    fig, ax = plt.subplots(figsize=(7, 6))

    colors = {"container": "#2980b9", "bulk": "#8e44ad", "tanker": "#d35400"}
    y_test_arr = y_te.to_numpy()

    for cat, col in colors.items():
        m = categories_te == cat
        if np.any(m):
            ax.scatter(y_test_arr[m], pred_best_te[m], alpha=0.35, s=16, label=f"{cat.title()} (N={np.sum(m):,})", color=col)

    lim_max = max(float(np.percentile(y_test_arr, 99.5)), float(np.percentile(pred_best_te, 99.5)))
    ax.plot([0, lim_max], [0, lim_max], "k--", lw=1.8, label="Ideal Parity (y = x)")

    ax.set_xlim(0, lim_max)
    ax.set_ylim(0, lim_max)
    ax.set_xlabel("Actual Annual Fuel Rate (kg / nm)", fontsize=11)
    ax.set_ylabel("Predicted Fuel Rate (kg / nm)", fontsize=11)
    ax.set_title(f"EU MRV held-out ships (R² = {metrics_best['r2']:.3f}, MAPE = {metrics_best['mape']:.1f}%)", fontsize=12, fontweight="bold")
    ax.legend(frameon=True, loc="upper left")
    ax.grid(True, linestyle=":", alpha=0.5)

    fig.tight_layout()
    fig.savefig(parity_path, dpi=150)
    plt.close(fig)
    print(f"Saved parity plot to {parity_path}")

    # 6. Generate outputs/mrv_model_report.md
    report_md_path = outputs_dir / "mrv_model_report.md"
    lines = [
        "# EU MRV Fuel Prediction Model Report",
        "",
        f"Trained on **{len(X_tr) + len(X_te):,} verified annual ship reports from the EU MRV THETIS database**, "
        "split 80/20 **by ship (IMO)** so no vessel appears in both training and test.",
        "",
        "## What the model predicts",
        "Annual-average fuel per nautical mile (kg/nm) from speed, EEDI and vessel category. "
        "`fuel_per_dwt_nm` and `laden_ratio` are excluded: the first is the target divided by deadweight, "
        "and neither is known for a fleet vessel at prediction time.",
        "",
        "## Accuracy (held-out ships)",
        "",
        "| Evaluation | R² | MAPE | RMSE (kg/nm) |",
        "| :--- | :---: | :---: | :---: |",
        f"| QPSO-XGBoost, ship's own EEDI where MRV reports it | {metrics_best['r2']:.3f} | {metrics_best['mape']:.1f}% | {metrics_best['rmse']:.1f} |",
        f"| QPSO-XGBoost, EEDI unknown (category median) | {metrics_fleet['r2']:.3f} | {metrics_fleet['mape']:.1f}% | {metrics_fleet['rmse']:.1f} |",
        f"| XGBoost, default hyperparameters | {metrics_def['r2']:.3f} | {metrics_def['mape']:.1f}% | {metrics_def['rmse']:.1f} |",
        f"| Naive: category median | {metrics_naive['r2']:.3f} | {metrics_naive['mape']:.1f}% | {metrics_naive['rmse']:.1f} |",
        "",
        f"5-fold CV RMSE (grouped by ship): {cv_mean:.1f} ± {cv_std:.1f} kg/nm.",
        "",
        "### Per category (ship's own EEDI)",
        "",
        "| Category | Test ships | R² | MAPE | RMSE (kg/nm) |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]
    for cat, m in cat_breakdown.items():
        n_c = int(np.sum(categories_te == cat))
        lines.append(f"| {cat.title()} | {n_c:,} | {m['r2']:.3f} | {m['mape']:.1f}% | {m['rmse']:.1f} |")
    lines.extend([
        "",
        "## Limits — read before quoting a number",
        "- MRV rows are **annual averages** mixing speeds, loads and weather, so a single-voyage prediction "
        "cannot be more precise than the spread between ships of the same type and EEDI.",
        "- Every row scores a ship **at its own operating speed**. How one ship's consumption changes when it "
        "speeds up or slows down is taken from the admiralty law (fuel/day ∝ v³), not from this model: across "
        "MRV ships, speed is confounded with size, so the data cannot identify that curve.",
        "- Fleet vessels have no measured EEDI; the app estimates it from deadweight with the IMO EEDI reference "
        "lines (MEPC.231(65)). With no EEDI at all, use the \"EEDI unknown\" row. Type-level predictions (no "
        "vessel given) use each category's median speed: "
        + ", ".join(f"{c} {v:.1f} kn" for c, v in reference_speed.items())
        + ".",
        "- Draft and weather adjustments are rule-based (see `src/prediction/predictor.py`), not learned: the "
        "voyage-level dataset has no measurable relation between its features and fuel.",
        "",
        "![Parity plot](parity_mrv.png)",
    ])

    report_md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved MRV model report to {report_md_path}")

    return meta_dict


def main() -> None:
    """CLI Entry Point."""
    parser = argparse.ArgumentParser(description="Train EU MRV Prediction Model.")
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET, help="Path to clean MRV parquet")
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR, help="Models output dir")
    parser.add_argument("--outputs-dir", type=Path, default=DEFAULT_OUTPUTS_DIR, help="Outputs dir")
    parser.add_argument("--fast", action="store_true", help="Skip QPSO search for fast training")
    args = parser.parse_args()

    train_and_evaluate(
        parquet_path=args.parquet,
        models_dir=args.models_dir,
        outputs_dir=args.outputs_dir,
        run_qpso=not args.fast,
    )


if __name__ == "__main__":
    main()
