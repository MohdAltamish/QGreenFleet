# Data Dictionary

## Datasets
| Name | Source | Grain | Used for |
|---|---|---|---|
| EU MRV THETIS 2022–2023 | mrv.emsa.europa.eu | ship-year (21,622 rows) | training the QPSO-XGBoost fuel model, synthetic calibration |
| Kaggle ship performance set | kaggle.com | voyage | explored only: no learnable fuel signal (stage-2 R² ≤ 0), not used for the production model |
| IMO 4th GHG Study | imo.org | per fuel | WtW emission factors |
| Synthetic fleet | generated | vessel/route | optimization + scalability |

## Feature schema (MRV prediction model)
| Field | Type | Unit | Notes |
|---|---|---|---|
| speed_kn | float | knots | monotone constraint (fuel rises with speed) |
| eedi | float | gCO2/t·nm | ship's own EEDI; for fleet vessels estimated from DWT via IMO reference lines (MEPC.231(65)) |
| category | cat | — | ship category |
| target | float | fuel per nm (log-transformed) | from MRV annual fuel / distance |

Draft and weather are not model features: they are applied as rule-based factors in `FuelPredictor`.

## Emission factors table (fill from IMO study — indicative)
| Fuel | LHV MJ/kg | WtW gCO2e/MJ (indicative) |
|---|---|---|
| HFO | 40.2 | ~92 |
| LNG | 48.0 | ~76 (incl. methane slip) |
| Methanol (grey/green) | 19.9 | ~100 / ~10 |
| H2 (green) | 120.0 | ~10 |
| NH3 (green) | 18.6 | ~12 |
> Replace with exact values + citation before final demo.

## Synthetic generator params
vessel counts by type, DWT distributions fitted to MRV, route distances 500–8000 nm, demand ~ lognormal.
