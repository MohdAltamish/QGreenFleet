"""Page 1: Fleet Data Ingestion, Synthetic Generation, and Geographic Routing Map."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.data.generate_synthetic import generate
from ui.utils.fleet_loader import compute_bau_baseline, ensure_session_state, load_fleet


st.set_page_config(page_title="QGreenFleet | Fleet Data", page_icon="🚢", layout="wide")

ensure_session_state()

st.title("🚢 Fleet & Commercial Route Management")
st.markdown("Upload existing commercial fleet schedules or synthesize realistic fleets calibrated to official EU MRV statistics.")

tab_load, tab_gen = st.tabs(["📂 Load Fleet JSON", "⚡ Generate Calibrated Fleet"])

# ===================================================================== #
#  Tab 1: Load Fleet JSON                                               #
# ===================================================================== #
with tab_load:
    st.subheader("Upload Fleet Specification")
    uploaded_file = st.file_uploader("Upload Fleet JSON file", type=["json"])

    if uploaded_file is not None:
        try:
            content = json.load(uploaded_file)
            vessels, routes, err = load_fleet(content)
            if err:
                st.error(err)
            else:
                st.session_state.fleet = {"vessels": vessels, "routes": routes, "path": uploaded_file.name}
                st.success(f"Successfully loaded {len(vessels)} vessels and {len(routes)} commercial routes!")
                # Recompute BAU baseline
                if st.session_state.predictor:
                    st.session_state.bau_baseline = compute_bau_baseline(
                        vessels=vessels,
                        routes=routes,
                        predictor=st.session_state.predictor,
                    )
        except Exception as exc:
            st.error(f"Error parsing JSON: {exc}")

    # Display Current Active Fleet
    if st.session_state.fleet:
        vessels = st.session_state.fleet["vessels"]
        routes = st.session_state.fleet["routes"]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"#### Active Vessels ({len(vessels)})")
            df_v = pd.DataFrame(vessels)
            st.dataframe(df_v[["id", "type", "dwt", "capacity_teu", "design_speed", "charter_per_day"]], use_container_width=True, height=280)

        with col2:
            st.markdown(f"#### Commercial Routes ({len(routes)})")
            df_r = pd.DataFrame(routes)
            display_cols = [c for c in ["id", "from", "to", "distance_nm", "demand_teu", "schedule_days", "shore_power"] if c in df_r.columns]
            st.dataframe(df_r[display_cols], use_container_width=True, height=280)
    else:
        st.info("Upload a fleet JSON file or generate one using the next tab.")


# ===================================================================== #
#  Tab 2: Generate Calibrated Synthetic Fleet                            #
# ===================================================================== #
with tab_gen:
    st.subheader("Synthetic Fleet Synthesizer")
    st.markdown("Generates naval architectures calibrated against **21,622 verified EU MRV THETIS** annual vessel reports.")

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        n_vessels = st.slider("Fleet Size (Vessels)", min_value=5, max_value=200, value=20, step=5)
    with col_s2:
        n_routes = st.slider("Route Corridors", min_value=2, max_value=20, value=5, step=1)
    with col_s3:
        seed = st.number_input("Random Generator Seed", min_value=0, max_value=9999, value=42)

    if st.button("Synthesize Fleet", type="primary"):
        with st.spinner("Calibrating naval parameters against EU MRV distributions..."):
            out_path = generate(n_vessels=n_vessels, n_routes=n_routes, seed=int(seed))
            vessels, routes, err = load_fleet(out_path)
            if not err:
                st.session_state.fleet = {"vessels": vessels, "routes": routes, "path": str(out_path)}
                if st.session_state.predictor:
                    st.session_state.bau_baseline = compute_bau_baseline(
                        vessels=vessels,
                        routes=routes,
                        predictor=st.session_state.predictor,
                    )
                st.success(f"Generated {n_vessels} vessels across {n_routes} routes saved to {out_path.name}!")
                st.rerun()
            else:
                st.error(err)


# ===================================================================== #
#  Interactive Folium Maritime Map                                       #
# ===================================================================== #
st.divider()
st.subheader("Global Commercial Corridors & Port Infrastructure")

port_locs = {
    "Singapore": [1.290270, 103.851959],
    "Shanghai": [31.230416, 121.473701],
    "Rotterdam": [51.924420, 4.477733],
    "Busan": [35.179554, 129.075642],
    "Tokyo": [35.676192, 139.650311],
    "Hamburg": [53.551085, 9.993682],
    "Los_Angeles": [33.743184, -118.267254],
}

m = folium.Map(location=[25.0, 50.0], zoom_start=2, tiles="CartoDB positron")

if st.session_state.fleet:
    routes = st.session_state.fleet.get("routes", [])
    for r in routes:
        p_from = r.get("from", "Singapore")
        p_to = r.get("to", "Shanghai")
        c1 = port_locs.get(p_from, [1.3, 103.8])
        c2 = port_locs.get(p_to, [31.2, 121.5])

        # Route arc line
        folium.PolyLine(
            locations=[c1, c2],
            color="#27ae60",
            weight=3,
            opacity=0.8,
            popup=f"Route {r.get('id')}: {p_from} → {p_to} ({r.get('distance_nm')} nm, {r.get('demand_teu')} TEU)",
        ).add_to(m)

    # Ports markers
    for p_name, coords in port_locs.items():
        is_sp = p_name in ["Shanghai", "Rotterdam", "Los_Angeles"]
        icon_color = "orange" if is_sp else "blue"
        popup_text = f"<b>{p_name}</b><br>⚡ Shore Power Available" if is_sp else f"<b>{p_name}</b><br>Conventional Port"
        folium.Marker(
            location=coords,
            popup=popup_text,
            icon=folium.Icon(color=icon_color, icon="plug" if is_sp else "ship", prefix="fa"),
        ).add_to(m)

components.html(m._repr_html_(), height=420)
