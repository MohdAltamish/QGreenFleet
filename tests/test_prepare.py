"""Unit tests for src.data.prepare — uses small synthetic DataFrames, no real files.

Covers:
    - tech_efficiency regex parsing (EEDI / EIV)
    - Ship-type mapping to {container, bulk, tanker}
    - Derived field math (hand-computed 2-row example)
    - Outlier filters (co2_per_fuel, avg_speed_kn, time_at_sea_h)
    - Weather encoding (calm/moderate/rough/unknown)
    - Year-over-year outlier flagging
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data.prepare import (
    encode_weather,
    find_col,
    map_ship_type,
    parse_eedi,
    SFOC_G_PER_KWH,
    TYPE_MAP,
)


# ===================================================================== #
#  find_col helper                                                       #
# ===================================================================== #
class TestFindCol:
    """Tests for the substring column matcher."""

    def test_basic_match(self) -> None:
        df = pd.DataFrame(columns=["IMO Number", "Ship type", "Other"])
        assert find_col(df, "IMO Number") == "IMO Number"

    def test_case_insensitive(self) -> None:
        df = pd.DataFrame(columns=["imo number", "SHIP TYPE"])
        assert find_col(df, "IMO Number") == "imo number"
        assert find_col(df, "ship type") == "SHIP TYPE"

    def test_substring_match(self) -> None:
        df = pd.DataFrame(columns=[
            "Annual average Fuel consumption per distance [kg/nm]",
            "Fuel consumption per distance on laden voyages [kg/nm]",
        ])
        # Should match first (exclude "laden")
        result = find_col(df, "Fuel consumption per distance", exclude="laden")
        assert result == "Annual average Fuel consumption per distance [kg/nm]"

    def test_exclude_works(self) -> None:
        df = pd.DataFrame(columns=[
            "Total CO₂ emissions from all voyages [m tonnes]",
            "Total CO₂ emissions [m tonnes]",
        ])
        result = find_col(df, "Total CO", exclude="voyages")
        assert result == "Total CO₂ emissions [m tonnes]"

    def test_no_match_returns_none(self) -> None:
        df = pd.DataFrame(columns=["alpha", "beta"])
        assert find_col(df, "gamma") is None


# ===================================================================== #
#  parse_eedi                                                            #
# ===================================================================== #
class TestParseEEDI:
    """Regex parsing of tech_efficiency strings."""

    def test_standard_eedi(self) -> None:
        s = pd.Series(["EEDI (4.23 gCO2/t·nm)"])
        t, v = parse_eedi(s)
        assert t.iloc[0] == "EEDI"
        assert v.iloc[0] == pytest.approx(4.23)

    def test_eiv(self) -> None:
        s = pd.Series(["EIV (12.5 gCO2/t·nm)"])
        t, v = parse_eedi(s)
        assert t.iloc[0] == "EIV"
        assert v.iloc[0] == pytest.approx(12.5)

    def test_no_parens(self) -> None:
        """Some MRV files omit parentheses: 'EEDI 4.23 gCO2/t·nm'."""
        s = pd.Series(["EEDI 4.23 gCO2/t·nm"])
        t, v = parse_eedi(s)
        assert t.iloc[0] == "EEDI"
        assert v.iloc[0] == pytest.approx(4.23)

    def test_unparseable_returns_nan(self) -> None:
        s = pd.Series(["Not applicable", np.nan, ""])
        t, v = parse_eedi(s)
        assert t.isna().all()
        assert v.isna().all()

    def test_mixed(self) -> None:
        s = pd.Series(["EEDI (3.0)", "EIV (7.7)", "N/A"])
        t, v = parse_eedi(s)
        assert list(t) == ["EEDI", "EIV", np.nan]  # last is NaN
        assert v.iloc[0] == pytest.approx(3.0)
        assert v.iloc[1] == pytest.approx(7.7)
        assert np.isnan(v.iloc[2])


# ===================================================================== #
#  map_ship_type                                                         #
# ===================================================================== #
class TestShipTypeMapping:
    """Verify the 8 known types map to 3 categories correctly."""

    @pytest.mark.parametrize("raw,expected", list(TYPE_MAP.items()))
    def test_all_known_types(self, raw: str, expected: str) -> None:
        # Use title-case as MRV would have it
        s = pd.Series([raw.title()])
        result = map_ship_type(s)
        assert result.iloc[0] == expected

    def test_unknown_type_gives_nan(self) -> None:
        s = pd.Series(["Passenger Ship", "Yacht"])
        result = map_ship_type(s)
        assert result.isna().all()

    def test_strips_whitespace(self) -> None:
        s = pd.Series(["  Container Ship  "])
        result = map_ship_type(s)
        assert result.iloc[0] == "container"


# ===================================================================== #
#  Derived fields — hand-computed 2-row example                          #
# ===================================================================== #
class TestDerivedFields:
    """Hand-computed math for distance_nm, avg_speed_kn, co2_per_fuel, laden_ratio."""

    @pytest.fixture()
    def two_row_df(self) -> pd.DataFrame:
        """Two vessels with hand-calculable derived fields.

        Vessel A: total_fuel_t=50, fuel_per_nm_kg=250, time_at_sea_h=4000,
                  total_co2_t=155, laden_fuel_t=40
        Vessel B: total_fuel_t=30, fuel_per_nm_kg=150, time_at_sea_h=3000,
                  total_co2_t=90,  laden_fuel_t=20
        """
        return pd.DataFrame({
            "imo": ["1234567", "7654321"],
            "ship_type": ["Container Ship", "Bulk Carrier"],
            "year": [2023, 2023],
            "tech_efficiency": ["EEDI (5.0)", "EIV (8.0)"],
            "total_fuel_t": [50.0, 30.0],
            "total_co2_t": [155.0, 90.0],
            "time_at_sea_h": [4000.0, 3000.0],
            "fuel_per_nm_kg": [250.0, 150.0],
            "co2_per_nm_kg": [500.0, 300.0],
            "fuel_per_dwt_nm": [0.01, 0.02],
            "co2_at_berth_t": [1.0, 0.5],
            "laden_fuel_t": [40.0, 20.0],
            "laden_fuel_per_nm_kg": [200.0, 120.0],
        })

    def test_distance_nm(self, two_row_df: pd.DataFrame) -> None:
        """distance_nm = total_fuel_t * 1000 / fuel_per_nm_kg.

        A: 50*1000/250 = 200 nm
        B: 30*1000/150 = 200 nm
        """
        df = two_row_df
        df["distance_nm"] = df["total_fuel_t"] * 1000.0 / df["fuel_per_nm_kg"]
        assert df["distance_nm"].iloc[0] == pytest.approx(200.0)
        assert df["distance_nm"].iloc[1] == pytest.approx(200.0)

    def test_avg_speed_kn(self, two_row_df: pd.DataFrame) -> None:
        """avg_speed_kn = distance_nm / time_at_sea_h.

        A: 200/4000 = 0.05 kn  (would be filtered as outlier — but math is correct)
        B: 200/3000 ≈ 0.0667 kn
        """
        df = two_row_df
        df["distance_nm"] = df["total_fuel_t"] * 1000.0 / df["fuel_per_nm_kg"]
        df["avg_speed_kn"] = df["distance_nm"] / df["time_at_sea_h"]
        assert df["avg_speed_kn"].iloc[0] == pytest.approx(0.05)
        assert df["avg_speed_kn"].iloc[1] == pytest.approx(200.0 / 3000.0)

    def test_co2_per_fuel(self, two_row_df: pd.DataFrame) -> None:
        """co2_per_fuel = total_co2_t / total_fuel_t.

        A: 155/50 = 3.1
        B: 90/30 = 3.0
        """
        df = two_row_df
        df["co2_per_fuel"] = df["total_co2_t"] / df["total_fuel_t"]
        assert df["co2_per_fuel"].iloc[0] == pytest.approx(3.1)
        assert df["co2_per_fuel"].iloc[1] == pytest.approx(3.0)

    def test_laden_ratio(self, two_row_df: pd.DataFrame) -> None:
        """laden_ratio = laden_fuel_t / total_fuel_t.

        A: 40/50 = 0.8
        B: 20/30 ≈ 0.6667
        """
        df = two_row_df
        df["laden_ratio"] = df["laden_fuel_t"] / df["total_fuel_t"]
        assert df["laden_ratio"].iloc[0] == pytest.approx(0.8)
        assert df["laden_ratio"].iloc[1] == pytest.approx(20.0 / 30.0)


# ===================================================================== #
#  Outlier filters                                                       #
# ===================================================================== #
class TestOutlierFilters:
    """Verify rows are dropped/kept based on filter thresholds."""

    def test_co2_per_fuel_filter(self) -> None:
        """Keep only 2.7 ≤ co2_per_fuel ≤ 3.3."""
        df = pd.DataFrame({
            "co2_per_fuel": [2.5, 2.7, 3.0, 3.3, 3.5],
        })
        filtered = df[df["co2_per_fuel"].between(2.7, 3.3)]
        assert len(filtered) == 3
        assert list(filtered["co2_per_fuel"]) == [2.7, 3.0, 3.3]

    def test_speed_filter(self) -> None:
        """Keep only 5 ≤ avg_speed_kn ≤ 25."""
        df = pd.DataFrame({
            "avg_speed_kn": [3.0, 5.0, 15.0, 25.0, 30.0],
        })
        filtered = df[df["avg_speed_kn"].between(5, 25)]
        assert len(filtered) == 3
        assert list(filtered["avg_speed_kn"]) == [5.0, 15.0, 25.0]

    def test_time_at_sea_filter(self) -> None:
        """Keep only time_at_sea_h ≥ 100."""
        df = pd.DataFrame({
            "time_at_sea_h": [50, 99, 100, 500, 8000],
        })
        filtered = df[df["time_at_sea_h"] >= 100]
        assert len(filtered) == 3


# ===================================================================== #
#  Weather encoding                                                      #
# ===================================================================== #
class TestWeatherEncoding:
    """Tests for weather string → integer mapping."""

    def test_known_values(self) -> None:
        s = pd.Series(["Calm", "Moderate", "Rough"])
        result = encode_weather(s)
        assert list(result) == [0, 1, 2]

    def test_case_insensitive(self) -> None:
        s = pd.Series(["CALM", "moderate", "rOuGh"])
        result = encode_weather(s)
        assert list(result) == [0, 1, 2]

    def test_unknown_defaults_to_1(self) -> None:
        s = pd.Series(["stormy", "calm"])
        result = encode_weather(s)
        assert result.iloc[0] == 1  # unknown → moderate
        assert result.iloc[1] == 0  # calm

    def test_all_unknown(self) -> None:
        s = pd.Series(["fog", "hail"])
        result = encode_weather(s)
        assert list(result) == [1, 1]


# ===================================================================== #
#  Year-over-year outlier flagging                                       #
# ===================================================================== #
class TestYoYOutlier:
    """Verify that rows deviating >30% from per-ship median get flagged."""

    def test_flag_logic(self) -> None:
        """Ship with 3 years: median = 200. Year with 280 → 40% deviation → flagged."""
        df = pd.DataFrame({
            "imo": ["A", "A", "A"],
            "fuel_per_nm_kg": [190.0, 200.0, 280.0],
        })
        median_per_ship = df.groupby("imo")["fuel_per_nm_kg"].transform("median")
        deviation = (df["fuel_per_nm_kg"] - median_per_ship).abs() / median_per_ship
        df["yoy_outlier"] = deviation > 0.30

        # 190: deviation = |190-200|/200 = 0.05 → NOT flagged
        assert df["yoy_outlier"].iloc[0] is np.bool_(False)
        # 200: deviation = 0 → NOT flagged
        assert df["yoy_outlier"].iloc[1] is np.bool_(False)
        # 280: deviation = |280-200|/200 = 0.40 → flagged
        assert df["yoy_outlier"].iloc[2] is np.bool_(True)

    def test_single_year_not_flagged(self) -> None:
        """Ship with only 1 year: deviation = 0 → never flagged."""
        df = pd.DataFrame({
            "imo": ["X"],
            "fuel_per_nm_kg": [999.0],
        })
        median_per_ship = df.groupby("imo")["fuel_per_nm_kg"].transform("median")
        deviation = (df["fuel_per_nm_kg"] - median_per_ship).abs() / median_per_ship
        df["yoy_outlier"] = deviation > 0.30
        assert df["yoy_outlier"].iloc[0] is np.bool_(False)


# ===================================================================== #
#  SFOC-derived fuel target                                              #
# ===================================================================== #
class TestSFOCFuelTarget:
    """Verify the SFOC-based fuel consumption derivation."""

    def test_fuel_tpd_formula(self) -> None:
        """fuel_tpd = engine_kw * 190 * 24 / 1e6.

        For 10000 kW: 10000 * 190 * 24 / 1e6 = 45.6 t/day.
        """
        engine_kw = 10000.0
        fuel_tpd = engine_kw * SFOC_G_PER_KWH * 24 / 1e6
        assert fuel_tpd == pytest.approx(45.6)

    def test_zero_power(self) -> None:
        fuel_tpd = 0.0 * SFOC_G_PER_KWH * 24 / 1e6
        assert fuel_tpd == 0.0
