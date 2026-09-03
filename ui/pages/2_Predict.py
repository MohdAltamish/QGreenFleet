"""Page 2: Fuel Consumption Predictive Surrogate Model & Admirality Power Curves."""

from __future__ import annotations

from pathlib import Path
import sys
import pandas as pd
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.prediction.predictor import FuelPredictor
from ui.utils.chart_helpers import speed_fuel_curve
from ui.utils.fleet_loader import ensure_session_state


st.set_page_config(page_title="QGreenFleet | Fuel Predictor", page_icon="⛽", layout="wide")

ensure_session_state()

st.title("⛽ Fuel Consumption Prediction Engine")
st.markdown("Physics-informed Machine Learning surrogate trained on voyage telemetry and calibrated against **21,622 EU MRV vessel-years**.")


@st.cache_resource
def get_predictor() -> FuelPredictor:
    return FuelPredictor()


predictor = get_predictor()

# ===================================================================== #
#  Interactive Voyage Fuel Estimator                                     #
# ===================================================================== #
st.subheader("Interactive Voyage Consumption Inference")

col1, col2, col3, col4 = st.columns(4)
with col1:
    ship_type = st.selectbox("Ship Classification", options=["container", "bulk", "tanker"], index=0)
with col2:
    speed_kn = st.slider("Speed Over Ground (knots)", min_value=5.0, max_value=25.0, value=15.0, step=0.5)
with col3:
    draft_m = st.slider("Mean Operational Draft (m)", min_value=4.0, max_value=18.0, value=10.0, step=0.5)
with col4:
    weather_lbl = st.selectbox("Sea State & Weather", options=["Calm (Beaufort 0-3)", "Moderate (Beaufort 4-5)", "Rough (Beaufort 6+)"], index=1)
    weather_map = {"Calm (Beaufort 0-3)": 0, "Moderate (Beaufort 4-5)": 1, "Rough (Beaufort 6+)": 2}
    weather_val = weather_map[weather_lbl]

# Inference computation
fuel_tpd_cal = predictor.predict_tpd(speed_kn, draft_m, weather_val, ship_type)

# Uncalibrated baseline estimation for comparison
cal_factors = {"container": 8.9351, "bulk": 4.4886, "tanker": 5.5481}
raw_estimate = fuel_tpd_cal / cal_factors.get(ship_type, 1.0)

mcol1, mcol2, mcol3, mcol4 = st.columns(4)
with mcol1:
    st.metric("Calibrated Fuel Burn", f"{fuel_tpd_cal:.2f} t/day", delta=f"{cal_factors[ship_type]:.2f}× EU MRV Calibrated")
with mcol2:
    st.metric("Hourly Consumption", f"{(fuel_tpd_cal*1000/24):.1f} kg/hr")
with mcol3:
    st.metric("Uncalibrated Kaggle Scale", f"{raw_estimate:.2f} t/day")
with mcol4:
    st.metric("Surrogate Active", predictor.model_name)

st.divider()

# ===================================================================== #
#  Speed-Fuel Power Curves & Parity Plot                                 #
# ===================================================================== #
st.subheader("Non-Linear Speed-Fuel Admiralty Curves")

c_left, c_right = st.columns([3, 2])

with c_left:
    fig_curve = speed_fuel_curve(predictor, draft_m=draft_m, weather_severity=weather_val)
    st.plotly_chart(fig_curve, use_container_width=True)

with c_right:
    st.markdown("#### Parity & Calibration Validation")
    parity_img = _PROJECT_ROOT / "outputs" / "parity_physics.png"
    if parity_img.exists():
        st.image(str(parity_img), caption="Figure: Predictive parity plot on holdout test partition.", use_container_width=True)
    else:
        st.info("Parity chart available after training execution.")

st.divider()

# ===================================================================== #
#  Model Benchmarking Registry Table                                     #
# ===================================================================== #
st.subheader("Surrogate Model Selection & Accuracy Registry")

model_summary = [
    {"Model Candidate": "PhysicsBaseline (Admiralty)", "5-Fold CV RMSE": "3.277 ± 0.077", "Test RMSE": "3.256", "Test MAPE": "50.7%", "Selected": "★ Selected"},
    {"Model Candidate": "QPSO-XGBoost", "5-Fold CV RMSE": "3.280 ± 0.076", "Test RMSE": "3.264", "Test MAPE": "50.8%", "Selected": ""},
    {"Model Candidate": "RandomForest", "5-Fold CV RMSE": "3.402 ± 0.109", "Test RMSE": "3.374", "Test MAPE": "51.8%", "Selected": ""},
    {"Model Candidate": "Default XGBoost", "5-Fold CV RMSE": "3.636 ± 0.131", "Test RMSE": "3.606", "Test MAPE": "54.4%", "Selected": ""},
]

df_models = pd.DataFrame(model_summary)
st.dataframe(df_models, use_container_width=True, hide_index=True)

st.markdown(
    """
    > **Key Insight**: Quantum-behaved Particle Swarm Optimization (QPSO) hyperparameter tuning reduced default XGBoost cross-validation RMSE by **9.8%**, achieving competitive performance with physics-based cubic formulations while capturing environmental interactions.
    """
)
