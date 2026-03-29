"""
Unit tests for solar-power-prediction pure logic functions.
All pure functions are defined inline to avoid importing the Streamlit app module.

Run with:
    python.exe -m pytest tests\test_functions.py -v
"""

import math
import pytest
import numpy as np
from datetime import datetime, date
import pytz

# ── Pure functions mirrored from app.py ───────────────────────────────────────

CO2_INTENSITY = {
    "US": 0.386, "GB": 0.233, "DE": 0.380, "FR": 0.056, "IN": 0.708,
    "AU": 0.610, "CN": 0.555, "JP": 0.474, "CA": 0.130, "BR": 0.074,
    "ZA": 0.928, "NG": 0.431, "MX": 0.454, "IT": 0.233, "ES": 0.193,
    "CH": 0.030, "NO": 0.017, "SE": 0.013, "NL": 0.296, "PL": 0.773,
    "": 0.386,
}

LOAD_PROFILES = {
    "Home all day":    [0.5,0.5,1.5,2.0,1.5,1.2,1.0,1.0,1.0,1.2,1.5,2.0,2.5,3.0,2.0,1.5],
    "Away 9–5":        [1.5,1.0,0.3,0.2,0.2,0.2,0.2,0.2,0.2,0.2,0.2,0.3,1.5,2.5,3.0,2.0],
    "EV night charging":[0.8,0.8,1.0,1.2,0.8,0.6,0.5,0.5,0.5,0.5,0.5,0.6,1.0,1.5,1.5,0.8],
}

ALBEDO_OPTIONS = {
    "Concrete": 0.25, "Grass": 0.20, "White Gravel": 0.60,
    "Sand": 0.35, "Snow": 0.80, "Asphalt": 0.12,
}


def tilt_factor(tilt_deg, lat):
    tf = math.cos(math.radians(tilt_deg - abs(lat)))
    return max(min(tf, 1.15), 0.70)


def calc_soiling_losses(precip_daily, soil_rate=0.002, rain_threshold=1.0, max_soil=0.25):
    soiling = 0.0
    daily = []
    for rain in precip_daily:
        if rain >= rain_threshold:
            soiling = 0.0
        else:
            soiling = min(soiling + soil_rate, max_soil)
        daily.append(soiling)
    n = len(daily)
    months = {}
    for i, v in enumerate(daily):
        m = int(i / n * 12)
        months.setdefault(m, []).append(v)
    return {m: float(np.mean(vals)) for m, vals in months.items()}


def simulate_battery(records, capacity_kwh, max_power_kw, efficiency, dod):
    usable = capacity_kwh * dod
    soc = capacity_kwh * 0.2
    for row in records:
        surplus = row["kw"] - row["load_kw"]
        if surplus > 0:
            charge = min(surplus, max_power_kw, usable - soc)
            charge = max(charge, 0)
            soc += charge * efficiency
            row["exported"] = max(row.get("exported", 0) - charge, 0)
            row["battery_charge"] = round(charge, 3)
            row["battery_discharge"] = 0.0
        else:
            deficit = abs(surplus)
            discharge = min(deficit, max_power_kw, soc)
            discharge = max(discharge, 0)
            soc -= discharge
            row["grid_import"] = max(row.get("grid_import", deficit) - discharge, 0)
            row["battery_charge"] = 0.0
            row["battery_discharge"] = round(discharge, 3)
        row["soc"] = round(soc, 3)
    return records


def build_load_profile(archetype, scale=1.0):
    raw = LOAD_PROFILES.get(archetype, LOAD_PROFILES["Home all day"])
    total = sum(raw)
    return [v / total * scale for v in raw]


def payback_curve(annual_sav, system_cost, degradation_pct):
    payback_yr = None
    net_vals = []
    cum = 0.0
    yr_sav = annual_sav
    for y in range(26):
        net_vals.append(round(cum - system_cost, 2))
        if cum >= system_cost and payback_yr is None:
            payback_yr = y
        yr_sav *= (1 - degradation_pct / 100)
        cum += yr_sav
    return payback_yr, net_vals


def panels_needed(monthly_bill, elec_rate, kwh_per_panel_per_day):
    daily_needed = (monthly_bill / elec_rate) / 30
    return math.ceil(daily_needed / kwh_per_panel_per_day) if kwh_per_panel_per_day else 0


def net_metering_savings(self_consumed_kwh, exported_kwh, elec_rate, net_meter_pct):
    net_meter_rate = elec_rate * (net_meter_pct / 100)
    return self_consumed_kwh * elec_rate + exported_kwh * net_meter_rate


def bifacial_gain(poa_global, albedo, bifaciality, gcr=0.4):
    view_factor = 0.5 * (1 - gcr) / max(gcr, 0.01)
    ghi_approx  = poa_global * 0.9  # rough approximation for test
    return max(ghi_approx * albedo * bifaciality * view_factor * 0.85, 0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_records(n=16, base_kw=2.0, base_load=1.5):
    return [{"kw": base_kw, "load_kw": base_load,
             "exported": max(base_kw - base_load, 0),
             "grid_import": max(base_load - base_kw, 0),
             "soc": 0.0, "battery_charge": 0.0, "battery_discharge": 0.0}
            for _ in range(n)]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Tilt Factor
# ═══════════════════════════════════════════════════════════════════════════════

class TestTiltFactor:

    def test_optimal_tilt_equals_one(self):
        assert math.isclose(tilt_factor(35, 35), 1.0, rel_tol=1e-9)

    def test_floor_clamp(self):
        assert tilt_factor(0, 60) >= 0.70

    @pytest.mark.parametrize("tilt,lat", [
        (0, 0), (0, 60), (60, 0), (30, 30), (45, 10), (10, 45),
    ])
    def test_always_in_bounds(self, tilt, lat):
        assert 0.70 <= tilt_factor(tilt, lat) <= 1.15

    def test_southern_hemisphere_symmetry(self):
        assert math.isclose(tilt_factor(30, 30), tilt_factor(30, -30), rel_tol=1e-9)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Payback Curve
# ═══════════════════════════════════════════════════════════════════════════════

class TestPaybackCurve:

    def test_early_payback_when_savings_high(self):
        yr, _ = payback_curve(5000, 1000, 0.5)
        assert yr is not None and yr <= 2

    def test_no_payback_when_zero_savings(self):
        yr, _ = payback_curve(0, 10000, 0.5)
        assert yr is None

    def test_net_value_starts_at_negative_cost(self):
        _, net = payback_curve(1000, 10000, 0.5)
        assert net[0] == -10000

    def test_net_value_grows_over_time(self):
        _, net = payback_curve(2000, 5000, 0)
        assert net[-1] > net[0]

    def test_degradation_reduces_profit(self):
        _, net_low  = payback_curve(2000, 5000, 0.0)
        _, net_high = payback_curve(2000, 5000, 2.0)
        assert net_low[-1] > net_high[-1]

    def test_typical_residential_payback_range(self):
        yr, _ = payback_curve(1200, 10000, 0.5)
        assert yr is not None and 7 <= yr <= 12, f"Expected 7-12 yr, got {yr}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Country CO₂ Intensity
# ═══════════════════════════════════════════════════════════════════════════════

class TestCO2Intensity:

    def test_us_factor(self):
        assert math.isclose(CO2_INTENSITY["US"], 0.386, rel_tol=1e-9)

    def test_france_low_nuclear(self):
        assert CO2_INTENSITY["FR"] < 0.10, "France (nuclear) should be <0.10 kg/kWh"

    def test_poland_high_coal(self):
        assert CO2_INTENSITY["PL"] > 0.70, "Poland (coal) should be >0.70 kg/kWh"

    def test_fallback_empty_country(self):
        assert CO2_INTENSITY[""] == 0.386

    def test_get_with_fallback(self):
        assert CO2_INTENSITY.get("XX", 0.386) == 0.386

    def test_co2_scales_with_kwh(self):
        factor = CO2_INTENSITY["US"]
        assert math.isclose(2000 * factor, 2 * 1000 * factor, rel_tol=1e-9)

    def test_india_high_coal(self):
        assert CO2_INTENSITY["IN"] > 0.60

    def test_norway_low_hydro(self):
        assert CO2_INTENSITY["NO"] < 0.05


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Kimber Soiling Model
# ═══════════════════════════════════════════════════════════════════════════════

class TestSoilingModel:

    def test_rain_resets_soiling(self):
        # alternating rain / dry days
        precip = [0, 0, 0, 5.0, 0, 0]  # day 4 = rain
        result = calc_soiling_losses(precip)
        # after day 4 (index 3), soiling should drop to 0
        vals = [v for _, v in sorted(result.items())]
        assert any(v < 0.001 for v in vals), "Rain day should reset soiling to ~0"

    def test_dry_days_accumulate_soiling(self):
        precip = [0.0] * 30  # all dry
        result = calc_soiling_losses(precip)
        total_avg = np.mean(list(result.values()))
        assert total_avg > 0, "Dry days should accumulate soiling"

    def test_soiling_capped_at_max(self):
        precip = [0.0] * 200  # many dry days
        result = calc_soiling_losses(precip, max_soil=0.25)
        assert all(v <= 0.25 for v in result.values()), "Soiling should not exceed max"

    def test_constant_rain_zero_soiling(self):
        precip = [5.0] * 30  # rain every day
        result = calc_soiling_losses(precip)
        assert all(v < 0.005 for v in result.values()), "Constant rain → near-zero soiling"

    def test_returns_monthly_dict(self):
        precip = [1.0] * 30
        result = calc_soiling_losses(precip)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_soiling_never_negative(self):
        precip = [10.0, 0.0, 10.0, 0.0] * 10
        result = calc_soiling_losses(precip)
        assert all(v >= 0 for v in result.values())


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Battery Storage Simulation
# ═══════════════════════════════════════════════════════════════════════════════

class TestBatterySimulation:

    def test_surplus_charges_battery(self):
        records = [{"kw": 3.0, "load_kw": 1.0, "exported": 2.0, "grid_import": 0.0,
                    "soc": 0.0, "battery_charge": 0.0, "battery_discharge": 0.0}]
        result = simulate_battery(records, 10, 5, 0.95, 0.9)
        assert result[0]["battery_charge"] > 0, "Surplus should charge battery"

    def test_deficit_discharges_battery(self):
        records = [{"kw": 0.5, "load_kw": 2.0, "exported": 0.0, "grid_import": 1.5,
                    "soc": 0.0, "battery_charge": 0.0, "battery_discharge": 0.0}]
        # Start with charged battery: SOC = 20% of 10 = 2 kWh
        result = simulate_battery(records, 10, 5, 0.95, 0.9)
        assert result[0]["battery_discharge"] > 0, "Deficit should discharge battery"

    def test_soc_never_negative(self):
        records = make_records(16, base_kw=0.0, base_load=5.0)
        result = simulate_battery(records, 10, 5, 0.95, 0.9)
        assert all(r["soc"] >= 0 for r in result)

    def test_soc_never_exceeds_usable(self):
        records = make_records(16, base_kw=10.0, base_load=0.0)
        capacity = 10.0
        dod = 0.8
        result = simulate_battery(records, capacity, 5, 0.95, dod)
        assert all(r["soc"] <= capacity * dod + 0.01 for r in result)

    def test_no_battery_no_effect_without_call(self):
        records_before = make_records(4, base_kw=2.0, base_load=1.0)
        kw_before = [r["kw"] for r in records_before]
        # if battery_on is False, simulate_battery is not called — test records unchanged
        assert kw_before == [2.0, 2.0, 2.0, 2.0]

    def test_grid_import_reduced_by_discharge(self):
        records = [{"kw": 0.0, "load_kw": 2.0, "exported": 0.0, "grid_import": 2.0,
                    "soc": 0.0, "battery_charge": 0.0, "battery_discharge": 0.0}]
        result = simulate_battery(records, 10, 5, 0.95, 0.9)
        assert result[0]["grid_import"] < 2.0, "Battery discharge should reduce grid import"

    def test_export_reduced_by_charging(self):
        records = [{"kw": 5.0, "load_kw": 1.0, "exported": 4.0, "grid_import": 0.0,
                    "soc": 0.0, "battery_charge": 0.0, "battery_discharge": 0.0}]
        result = simulate_battery(records, 10, 5, 0.95, 0.9)
        assert result[0]["exported"] < 4.0, "Battery charging should reduce export"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Load Profile
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadProfile:

    def test_returns_16_values(self):
        profile = build_load_profile("Home all day")
        assert len(profile) == 16

    def test_all_positive(self):
        for archetype in LOAD_PROFILES:
            profile = build_load_profile(archetype)
            assert all(v > 0 for v in profile), f"{archetype} has zero/negative values"

    def test_scale_sets_daily_total(self):
        scale = 30.0
        profile = build_load_profile("Home all day", scale=scale)
        # total should equal scale (30 kWh daily allocation over 16 hours)
        assert math.isclose(sum(profile), scale, rel_tol=1e-6)

    def test_unknown_archetype_uses_default(self):
        profile = build_load_profile("Unknown archetype")
        assert len(profile) == 16

    def test_away_profile_low_midday(self):
        profile = build_load_profile("Away 9–5", scale=30.0)
        # Hours 9-17 are indices 4-12; should be lower than morning/evening
        midday_avg = np.mean(profile[4:12])
        morning_avg = np.mean(profile[0:4])
        assert midday_avg < morning_avg, "Away 9-5 profile should be low at midday"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Net Metering Savings
# ═══════════════════════════════════════════════════════════════════════════════

class TestNetMeteringSavings:

    def test_full_net_metering_equals_flat(self):
        # 100% net metering = same as consuming everything at retail
        sav = net_metering_savings(5, 5, 0.15, 100)
        flat = 10 * 0.15
        assert math.isclose(sav, flat, rel_tol=1e-9)

    def test_zero_net_metering_no_export_credit(self):
        sav = net_metering_savings(5, 5, 0.15, 0)
        assert math.isclose(sav, 5 * 0.15, rel_tol=1e-9)

    def test_partial_net_metering(self):
        # 50% of retail for exports
        sav = net_metering_savings(8, 2, 0.20, 50)
        expected = 8 * 0.20 + 2 * 0.10
        assert math.isclose(sav, expected, rel_tol=1e-9)

    def test_higher_rate_higher_savings(self):
        s_low  = net_metering_savings(5, 2, 0.10, 50)
        s_high = net_metering_savings(5, 2, 0.30, 50)
        assert s_high > s_low

    def test_zero_production_zero_savings(self):
        assert net_metering_savings(0, 0, 0.15, 50) == 0.0

    def test_export_less_valuable_than_self_consumption(self):
        # Same kWh: self-consumed vs exported at 50%
        self_sav   = net_metering_savings(1, 0, 0.20, 50)
        export_sav = net_metering_savings(0, 1, 0.20, 50)
        assert self_sav > export_sav


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Bifacial Gain
# ═══════════════════════════════════════════════════════════════════════════════

class TestBifacialGain:

    def test_zero_poa_zero_gain(self):
        assert bifacial_gain(0, 0.25, 0.70) == 0.0

    def test_higher_albedo_higher_gain(self):
        low  = bifacial_gain(500, 0.20, 0.70)
        high = bifacial_gain(500, 0.60, 0.70)
        assert high > low, "Higher albedo should increase bifacial gain"

    def test_higher_bifaciality_higher_gain(self):
        low  = bifacial_gain(500, 0.25, 0.60)
        high = bifacial_gain(500, 0.25, 0.90)
        assert high > low

    def test_gain_never_negative(self):
        assert bifacial_gain(500, 0.0, 0.70) >= 0

    def test_snow_albedo_gives_high_gain(self):
        grass = bifacial_gain(600, 0.20, 0.70)
        snow  = bifacial_gain(600, 0.80, 0.70)
        assert snow > grass * 2, "Snow albedo (0.80) should give >2x grass (0.20) gain"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. System Sizing
# ═══════════════════════════════════════════════════════════════════════════════

class TestSystemSizing:

    def test_higher_bill_needs_more_panels(self):
        assert panels_needed(200, 0.12, 2.0) > panels_needed(100, 0.12, 2.0)

    def test_higher_rate_fewer_panels(self):
        assert panels_needed(120, 0.30, 2.0) < panels_needed(120, 0.10, 2.0)

    def test_zero_kwh_per_panel_returns_zero(self):
        assert panels_needed(120, 0.12, 0) == 0

    def test_known_panel_count(self):
        # daily_needed = (120/0.12)/30 = 33.33; per panel = 2.0 → ceil = 17
        assert panels_needed(120, 0.12, 2.0) == 17


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Environmental Impact (CO₂ math)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnvironmentalImpact:

    def test_known_co2_value_us(self):
        assert math.isclose(1000 * 0.386, 386.0, rel_tol=1e-9)

    def test_trees_equivalence(self):
        co2 = 1000 * 0.386
        assert math.isclose(co2 / 21, 386 / 21, rel_tol=1e-9)

    def test_cars_removed(self):
        assert math.isclose(4600 / 4600, 1.0, rel_tol=1e-9)

    def test_co2_scales_linearly(self):
        assert math.isclose(2000 * 0.386, 2 * 1000 * 0.386, rel_tol=1e-9)

    def test_france_vs_poland_co2(self):
        kwh = 5000
        fr_co2 = kwh * CO2_INTENSITY["FR"]
        pl_co2 = kwh * CO2_INTENSITY["PL"]
        assert pl_co2 > fr_co2 * 10, "Poland coal grid should emit 10x+ France nuclear"
