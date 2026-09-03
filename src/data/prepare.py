"""Data preparation pipeline for QGreenFleet.

Cleans two raw datasets into training-ready Parquet files and produces a
calibration check plot comparing Kaggle-implied fuel rates vs MRV medians.

Tasks:
    A — Clean EU MRV THETIS Excel files  → data/processed/mrv_clean.parquet
    B — Clean Kaggle ship performance CSV → data/processed/voyages_clean.parquet
    C — Calibration boxplot              → outputs/calibration_check.png

Run::

    python -m src.data.prepare

Each task skips gracefully with a printed warning if its input file is missing.

Sources cited in derived fields:
    - SFOC 190 g/kWh: MAN Energy Solutions "Basic Principles of Ship Propulsion"
      (2018) Table 4; Wärtsilä 46F Product Guide, ISO conditions.
"""

from __future__ import annotations

import os
import re
import warnings
from pathlib import Path

# Ensure matplotlib uses a writable temp directory for fonts/cache
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib
matplotlib.use("Agg")  # non-interactive backend; safe on headless environments
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths (relative to repo root)
# ---------------------------------------------------------------------------
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
RAW: Path = _PROJECT_ROOT / "data" / "raw"
OUT: Path = _PROJECT_ROOT / "data" / "processed"
OUTPUTS: Path = _PROJECT_ROOT / "outputs"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Specific Fuel Oil Consumption — MAN/Wärtsilä mid-speed marine diesel typical
# value at ISO reference conditions. Source: MAN Energy Solutions "Basic
# Principles of Ship Propulsion" (2018), Table 4; Wärtsilä 46F Product Guide.
SFOC_G_PER_KWH: int = 190

# Ship-type canonicalisation (MRV and Kaggle free-text → 3 categories).
TYPE_MAP: dict[str, str] = {
    "container ship": "container",
    "container": "container",
    "bulk carrier": "bulk",
    "bulk": "bulk",
    "general cargo ship": "bulk",
    "combination carrier": "bulk",
    "oil tanker": "tanker",
    "chemical tanker": "tanker",
    "oil/chemical tanker": "tanker",
    "gas carrier": "tanker",
    "lng carrier": "tanker",
    "tanker": "tanker",
}

# Weather encoding for Kaggle weather_condition column.
WEATHER_MAP: dict[str, int] = {"calm": 0, "moderate": 1, "rough": 2}


# ===================================================================== #
#  Helpers                                                               #
# ===================================================================== #
def find_col(
    df: pd.DataFrame,
    pattern: str,
    exclude: str | None = None,
) -> str | None:
    """Return the first column whose name contains *pattern* (case-insensitive).

    If *exclude* is given, skip columns containing that substring.
    Returns ``None`` if no match is found.
    """
    pat = pattern.lower()
    exc = exclude.lower() if exclude else None
    for c in df.columns:
        cs = str(c).lower()
        if pat in cs and (exc is None or exc not in cs):
            return c
    return None


def _safe_col(df: pd.DataFrame, pattern: str, exclude: str | None = None) -> pd.Series:
    """Like :func:`find_col` but returns a NaN series if not found."""
    col = find_col(df, pattern, exclude)
    if col is not None:
        return df[col]
    return pd.Series(np.nan, index=df.index)


def parse_eedi(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Parse tech_efficiency strings like ``'EEDI (4.23 gCO2/t·nm)'``.

    Returns:
        (eedi_type, eedi_value) — str and float Series.
    """
    extracted = series.astype(str).str.extract(r"(EEDI|EIV)\s*\(?([\d.]+)")
    eedi_type = extracted[0]
    eedi_value = pd.to_numeric(extracted[1], errors="coerce")
    return eedi_type, eedi_value


def map_ship_type(series: pd.Series) -> pd.Series:
    """Normalise free-text ship types to {container, bulk, tanker}."""
    return series.astype(str).str.strip().str.lower().map(TYPE_MAP)


def encode_weather(series: pd.Series) -> pd.Series:
    """Map weather strings to severity integers (calm=0, moderate=1, rough=2).

    Unknown values default to 1 with a printed warning.
    """
    cleaned = series.astype(str).str.strip().str.lower()
    mapped = cleaned.map(WEATHER_MAP)
    n_unknown = mapped.isna().sum()
    if n_unknown > 0:
        unknown_vals = cleaned[mapped.isna()].unique().tolist()
        print(
            f"WARNING: {n_unknown} rows have unknown weather values "
            f"{unknown_vals}; defaulting to 1 (moderate)"
        )
        mapped = mapped.fillna(1).astype(int)
    else:
        mapped = mapped.astype(int)
    return mapped


# ===================================================================== #
#  Task A — Clean MRV                                                    #
# ===================================================================== #
def load_mrv_year(path: Path) -> pd.DataFrame:
    """Load a single MRV THETIS Excel file (3-row header → header at row index 2)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = pd.read_excel(path, header=2)

    out = pd.DataFrame()
    out["imo"] = _safe_col(df, "IMO Number")
    out["ship_type"] = _safe_col(df, "Ship type")
    out["year"] = _safe_col(df, "Reporting Period")
    out["tech_efficiency"] = _safe_col(df, "Technical efficiency")
    out["total_fuel_t"] = _safe_col(df, "Total fuel consumption")
    out["total_co2_t"] = _safe_col(df, "Total CO", exclude="voyages")
    out["time_at_sea_h"] = _safe_col(df, "Annual Time spent at sea")
    out["fuel_per_nm_kg"] = _safe_col(
        df, "Fuel consumption per distance", exclude="laden"
    )
    out["co2_per_nm_kg"] = _safe_col(
        df, "emissions per distance", exclude="laden"
    )
    out["fuel_per_dwt_nm"] = _safe_col(
        df, "Fuel consumption per transport work (dwt)", exclude="laden"
    )
    out["co2_at_berth_t"] = _safe_col(df, "at berth")
    out["laden_fuel_t"] = _safe_col(df, "assigned to On laden")
    laden_dist = find_col(df, "Fuel consumption per distance on laden")
    out["laden_fuel_per_nm_kg"] = df[laden_dist] if laden_dist else np.nan
    return out


def clean_mrv(raw_dir: Path = RAW, out_dir: Path = OUT) -> pd.DataFrame | None:
    """Clean all MRV THETIS Excel files → ``mrv_clean.parquet``.

    Returns:
        Cleaned DataFrame, or ``None`` if no input files were found.
    """
    files = sorted(raw_dir.glob("mrv_*.xlsx"))
    if not files:
        print("!! No mrv_*.xlsx files in data/raw/ — skipping MRV")
        return None

    df = pd.concat([load_mrv_year(f) for f in files], ignore_index=True)
    n0 = len(df)
    print(f"MRV: loaded {n0} rows from {len(files)} file(s)")

    # ---- Numeric coercion ----
    num_cols = [
        c for c in df.columns
        if c not in ("imo", "ship_type", "year", "tech_efficiency")
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # ---- Drop rows missing critical fields ----
    before = len(df)
    df = df.dropna(subset=["total_fuel_t", "fuel_per_nm_kg", "time_at_sea_h"])
    print(f"MRV: {before} -> {len(df)} after null drop (total_fuel_t/fuel_per_nm_kg/time_at_sea_h)")

    # ---- Parse EEDI / EIV ----
    df["eedi_type"], df["eedi_value"] = parse_eedi(df["tech_efficiency"])

    # ---- Ship-type mapping (keep only container/bulk/tanker) ----
    df["category"] = map_ship_type(df["ship_type"])
    before = len(df)
    df = df.dropna(subset=["category"])
    print(f"MRV: {before} -> {len(df)} after ship-type filter")

    # ---- Derived fields (Eq refs: mathematical-model.md §Fuel consumption) ----
    df["distance_nm"] = df["total_fuel_t"] * 1000.0 / df["fuel_per_nm_kg"]
    df["avg_speed_kn"] = df["distance_nm"] / df["time_at_sea_h"]
    df["co2_per_fuel"] = df["total_co2_t"] / df["total_fuel_t"]
    df["laden_ratio"] = df["laden_fuel_t"] / df["total_fuel_t"]

    # ---- Outlier filters ----
    before = len(df)
    df = df[df["co2_per_fuel"].between(2.7, 3.3)]
    print(f"MRV: {before} -> {len(df)} after co2_per_fuel filter")

    before = len(df)
    df = df[df["avg_speed_kn"].between(5, 25)]
    print(f"MRV: {before} -> {len(df)} after avg_speed_kn filter")

    before = len(df)
    df = df[df["time_at_sea_h"] >= 100]
    print(f"MRV: {before} -> {len(df)} after time_at_sea_h filter")

    # ---- Year-over-year consistency flag ----
    median_per_ship = df.groupby("imo")["fuel_per_nm_kg"].transform("median")
    deviation = (df["fuel_per_nm_kg"] - median_per_ship).abs() / median_per_ship
    df["yoy_outlier"] = deviation > 0.30
    n_flagged = int(df["yoy_outlier"].sum())
    print(f"MRV: flagged {n_flagged} rows as yoy_outlier (>30% deviation from ship median)")

    # ---- Save ----
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "mrv_clean.parquet"
    df.to_parquet(out_path, index=False, engine="pyarrow")
    print(
        f"MRV: saved {len(df)} rows to {out_path} | "
        f"types: {df['category'].value_counts().to_dict()}"
    )
    return df


# ===================================================================== #
#  Task B — Clean Kaggle                                                 #
# ===================================================================== #
def clean_kaggle(raw_dir: Path = RAW, out_dir: Path = OUT) -> pd.DataFrame | None:
    """Clean Kaggle Ship Performance CSV → ``voyages_clean.parquet``.

    The Kaggle dataset has no fuel consumption column, so we derive the
    training target via SFOC:  fuel_tpd = engine_kW × 190 g/kWh × 24 h / 1e6.

    Returns:
        Cleaned DataFrame, or ``None`` if input file is missing.
    """
    path = raw_dir / "ship_performance.csv"
    if not path.exists():
        # Also check alternative naming like Ship_Performance_Dataset.csv
        alts = list(raw_dir.glob("*[sS]hip_[pP]erformance*.csv"))
        if alts:
            path = alts[0]
        else:
            print("!! data/raw/ship_performance.csv missing — skipping Kaggle")
            return None

    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    n0 = len(df)
    print(f"Kaggle: loaded {n0} rows from {path.name}")

    # ---- Locate columns by substring (robust to naming differences) ----
    def col(sub: str) -> str | None:
        return next((c for c in df.columns if sub in c), None)

    speed_c = col("speed")
    draft_c = col("draft")
    power_c = col("power")
    weather_c = col("weather")
    type_c = col("ship_type") or col("type")
    route_c = col("route")
    maint_c = col("maint")

    # ---- Drop nulls in critical columns ----
    required = [c for c in [speed_c, draft_c, power_c] if c is not None]
    before = len(df)
    df = df.dropna(subset=required)
    print(f"Kaggle: {before} -> {len(df)} after null drop (speed/draft/power)")

    # ---- Derived fuel target ----
    # SFOC 190 g/kWh — MAN Energy Solutions "Basic Principles of Ship Propulsion"
    # (2018), Table 4; Wärtsilä 46F Product Guide, ISO conditions.
    # fuel_tpd = engine_power_kW × SFOC × 24h / 1e6  [tons/day]
    df["fuel_tpd"] = df[power_c] * SFOC_G_PER_KWH * 24 / 1e6

    # ---- Weather encoding ----
    if weather_c:
        df["weather_severity"] = encode_weather(df[weather_c])
    else:
        df["weather_severity"] = 1

    # ---- Speed processing ----
    df["speed_kn"] = df[speed_c].clip(5, 25)

    # ---- Draft ----
    df["draft_m"] = df[draft_c]
    before = len(df)
    df = df[df["draft_m"] > 0]
    print(f"Kaggle: {before} -> {len(df)} after draft_m > 0 filter")

    # ---- Physics feature (design.md: speed³ ∝ resistance) ----
    df["speed_cubed"] = df["speed_kn"] ** 3

    # ---- One-hot encode categoricals ----
    for c, prefix in [(type_c, "type"), (route_c, "route"), (maint_c, "maint")]:
        if c is not None:
            dummies = pd.get_dummies(df[c], prefix=prefix, dtype=int)
            df = pd.concat([df, dummies], axis=1)

    # ---- Select final feature set ----
    raw_cats = {c for c in (type_c, route_c, maint_c) if c is not None}
    base_cols = ["speed_kn", "speed_cubed", "draft_m", "weather_severity", "fuel_tpd"]
    onehot_cols = sorted(
        c for c in df.columns
        if c.startswith(("type_", "route_", "maint_")) and c not in raw_cats
    )
    keep = base_cols + onehot_cols
    df_out = df[keep].copy()

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "voyages_clean.parquet"
    df_out.to_parquet(out_path, index=False, engine="pyarrow")
    print(
        f"Kaggle: saved {len(df_out)} rows to {out_path} | "
        f"features: {len(keep) - 1}"
    )
    return df_out


# ===================================================================== #
#  Task C — Calibration check                                            #
# ===================================================================== #
def calibration_check(
    mrv_path: Path | None = None,
    kaggle_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    """Compare Kaggle-implied fuel-per-nm against MRV medians.

    Produces a side-by-side boxplot and prints per-type median ratios.
    """
    mrv_file = mrv_path or (OUT / "mrv_clean.parquet")
    kaggle_file = kaggle_path or (OUT / "voyages_clean.parquet")
    plot_path = output_path or (OUTPUTS / "calibration_check.png")

    if not mrv_file.exists():
        print("!! mrv_clean.parquet not found — skipping calibration check")
        return
    if not kaggle_file.exists():
        print("!! voyages_clean.parquet not found — skipping calibration check")
        return

    mrv = pd.read_parquet(mrv_file)
    kaggle = pd.read_parquet(kaggle_file)

    # Kaggle-implied fuel_per_nm:  fuel_tpd * 1000 / (speed_kn * 24)  [kg/nm]
    kaggle["fuel_per_nm_kg"] = kaggle["fuel_tpd"] * 1000.0 / (kaggle["speed_kn"] * 24)

    # Infer ship type from one-hot columns for grouping
    type_cols = [c for c in kaggle.columns if c.startswith("type_")]
    if type_cols:
        raw_types = (
            kaggle[type_cols]
            .idxmax(axis=1)
            .str.replace("type_", "", regex=False)
            .str.lower()
        )
        kaggle["category"] = map_ship_type(raw_types).fillna(raw_types)
    else:
        kaggle["category"] = "unknown"

    # Categories present in both datasets
    common_cats = sorted(
        set(mrv["category"].unique()) & set(kaggle["category"].unique())
    )

    if not common_cats:
        print("!! No common ship-type categories — skipping calibration plot")
        print("MRV categories:", sorted(mrv["category"].unique()))
        print("Kaggle categories:", sorted(kaggle["category"].unique()))
        return

    # ---- Compute and save calibration factors (k = MRV / Kaggle) ----
    import json

    print("\n--- Calibration: Kaggle vs MRV fuel_per_nm_kg ---")
    calibration_dict: dict[str, dict[str, float]] = {}
    scale_factors: dict[str, float] = {}

    for cat in common_cats:
        mrv_med = float(mrv.loc[mrv["category"] == cat, "fuel_per_nm_kg"].median())
        kag_med = float(kaggle.loc[kaggle["category"] == cat, "fuel_per_nm_kg"].median())
        ratio = kag_med / mrv_med if mrv_med > 0 else float("nan")
        scale_factor = mrv_med / kag_med if kag_med > 0 else 1.0
        scale_factors[cat] = round(scale_factor, 4)
        calibration_dict[cat] = {
            "mrv_median_kg_per_nm": round(mrv_med, 2),
            "kaggle_median_kg_per_nm": round(kag_med, 2),
            "kaggle_to_mrv_ratio": round(ratio, 4),
            "scale_factor_k": round(scale_factor, 4),
        }
        print(
            f"  {cat:>12s}: Kaggle={kag_med:.1f} kg/nm | MRV={mrv_med:.1f} kg/nm "
            f"| ratio={ratio:.2f} | scale_factor (k)={scale_factor:.2f}"
        )

    calib_file = OUT / "calibration.json"
    calib_payload = {
        "description": "Per-type calibration factors k = MRV_median / Kaggle_median. Apply to predictions: fuel_calibrated = fuel_raw * k.",
        "scale_factors": scale_factors,
        "details": calibration_dict,
    }
    calib_file.write_text(json.dumps(calib_payload, indent=2))
    print(f"Calibration factors written to {calib_file}")

    # ---- Boxplot ----
    fig, axes = plt.subplots(1, len(common_cats), figsize=(5 * len(common_cats), 5))
    if len(common_cats) == 1:
        axes = [axes]

    for ax, cat in zip(axes, common_cats):
        mrv_vals = mrv.loc[mrv["category"] == cat, "fuel_per_nm_kg"].dropna()
        kag_vals = kaggle.loc[kaggle["category"] == cat, "fuel_per_nm_kg"].dropna()
        ax.boxplot(
            [mrv_vals, kag_vals],
            tick_labels=["MRV", "Kaggle"],
            widths=0.5,
            patch_artist=True,
            boxprops=dict(facecolor="#cce5ff"),
            medianprops=dict(color="#003366"),
        )
        ax.set_title(cat.title())
        ax.set_ylabel("fuel_per_nm (kg/nm)")

    fig.suptitle("Calibration: MRV vs Kaggle fuel per nm", fontsize=14)
    fig.tight_layout()
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    print(f"Calibration plot saved to {plot_path}")


# ===================================================================== #
#  CLI entry point                                                       #
# ===================================================================== #
def main() -> None:
    """Entry point for ``python -m src.data.prepare``."""
    print("=" * 60)
    print("QGreenFleet Data Preparation Pipeline")
    print("=" * 60)

    print("\n--- Task A: Clean MRV ---")
    clean_mrv()

    print("\n--- Task B: Clean Kaggle ---")
    clean_kaggle()

    print("\n--- Task C: Calibration Check ---")
    calibration_check()

    print("\nDone. Output in data/processed/")


if __name__ == "__main__":
    main()
