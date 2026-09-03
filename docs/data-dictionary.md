# Data Dictionary

## Datasets
| Name | Source | Grain | Used for |
|---|---|---|---|
| EU MRV THETIS | mrv.emsa.europa.eu | ship-year | training (per-type curves), synthetic calibration |
| Kaggle ship fuel voyage set | kaggle.com | voyage/hour | main regression training |
| IMO 4th GHG Study | imo.org | per fuel | WtW emission factors |
| Synthetic fleet | generated | vessel/route | optimization + scalability |

## Feature schema (prediction)
| Field | Type | Unit | Notes |
|---|---|---|---|
| speed_kn | float | knots | 5–25 |
| draft_pct / load_pct | float | % | proxy for displacement |
| wind_speed | float | m/s | optional, default 0 |
| wave_height | float | m | optional, default 0 |
| vessel_type | cat | — | container/bulk/tanker |
| dwt | float | t | |
| engine_kw | float | kW | |
| target: fuel_tpd | float | tons/day | label |

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
