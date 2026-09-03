"""Calibration module for scaling raw model predictions to real-world MRV scale.

Loads per-ship-type calibration factors from data/processed/calibration.json
or falls back to default empirically derived ratios from the EU MRV calibration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, overload

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_FILE = _PROJECT_ROOT / "data" / "processed" / "calibration.json"

# Default fallback factors (MRV median / Kaggle median)
DEFAULT_CALIBRATION: dict[str, float] = {
    "bulk": 4.48,
    "container": 8.93,
    "tanker": 5.54,
}


def load_calibration_factors(path: Path | None = None) -> dict[str, float]:
    """Load per-type calibration factors from disk or fall back to defaults.

    Args:
        path: Optional path to calibration.json. Defaults to
            data/processed/calibration.json.

    Returns:
        Dictionary mapping canonical ship type to float scaling factor.
    """
    target = path or CALIBRATION_FILE
    if target.exists():
        try:
            content = json.loads(target.read_text(encoding="utf-8"))
            if "scale_factors" in content and isinstance(content["scale_factors"], dict):
                return {
                    str(k).strip().lower(): float(v)
                    for k, v in content["scale_factors"].items()
                }
        except Exception:
            pass
    return DEFAULT_CALIBRATION.copy()


def normalize_type_key(ship_type: str) -> str:
    """Normalize ship type string to canonical category key.

    Args:
        ship_type: Vessel type string (e.g. 'Container Ship', 'bulk', 'tanker').

    Returns:
        Normalized key in {'bulk', 'container', 'tanker'} or original lowercased string.
    """
    cleaned = ship_type.strip().lower()
    if "container" in cleaned:
        return "container"
    if "bulk" in cleaned:
        return "bulk"
    if "tanker" in cleaned:
        return "tanker"
    return cleaned


@overload
def calibrated(raw_pred: float, ship_type: str) -> float: ...


@overload
def calibrated(raw_pred: np.ndarray, ship_type: str) -> np.ndarray: ...


def calibrated(raw_pred: float | np.ndarray, ship_type: str) -> float | np.ndarray:
    """Multiply raw model prediction(s) by the per-type calibration factor.

    Args:
        raw_pred: Unscaled model prediction as a float or numpy array (tons/day).
        ship_type: Ship type string (e.g. 'container', 'bulk', 'tanker').

    Returns:
        Calibrated prediction in the same type/shape as raw_pred.

    Raises:
        ValueError: If ship_type cannot be resolved to a known calibration factor.
    """
    factors = load_calibration_factors()
    key = normalize_type_key(ship_type)

    if key not in factors:
        valid = sorted(factors.keys())
        raise ValueError(
            f"Unknown ship type '{ship_type}'. Available calibrated types: {valid}"
        )

    factor = factors[key]
    if isinstance(raw_pred, (int, float, np.floating)):
        return float(raw_pred * factor)

    arr = np.asarray(raw_pred)
    return arr * factor
