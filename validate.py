"""
Cross-validation of solar physics against PVGIS TMY hourly data.

Standard module: Jinko Solar JKM400M-6RL3-V (400W monocrystalline)
  — one of the world's best-selling residential panels (2023/24)

Test locations:
  Austin TX   (sunbelt, high irradiance)
  London UK   (low irradiance, high latitude)
  Sydney AU   (southern hemisphere)

Reference sources:
  PVGIS v5.2  — EU JRC, TMY-based simulation
  NREL ATB 2023 — published US capacity factors
  IEA PVPS 2023 — published specific yields by country
"""

import math
import sys
import requests
import numpy as np
import pvlib

# -- Standard residential module -----------------------------------------------
MODULE        = "Jinko Solar JKM400M-6RL3-V 400W"
PANEL_POWER_W = 400
PANEL_EFF     = 0.213          # 21.3% STC efficiency
PANEL_AREA    = PANEL_POWER_W / (1000 * PANEL_EFF)   # 1.878 m²
N_PANELS      = 10             # 4.0 kWp system
TEMP_COEFF    = -0.0035        # -0.35 %/°C  (Pmax)
ALBEDO        = 0.25           # concrete/gravel
INVERTER_EFF  = 0.96           # string inverter DC→AC

# System DC losses (same defaults as our app)
# mismatch 2% + wiring 2% + LID 1.5% + availability 3% + soiling 2%
DERATE = (1-.02) * (1-.02) * (1-.015) * (1-.03) * (1-.02)   # ≈ 0.862

CAPACITY_KW   = N_PANELS * PANEL_POWER_W / 1000   # 4.0 kWp

LOCATIONS = [
    ("Austin TX",  30.267, -97.743, 20, 180, "US"),
    ("London UK",  51.508,  -0.128, 35, 180, "GB"),
    ("Sydney AU", -33.869, 151.209, 30,   0, "AU"),  # north-facing in SH → azimuth 0
]

# Literature benchmarks (kWh/kWp/year)
# Sources: NREL ATB 2023, PVGIS 2022 country reports, IEA PVPS Task 1 2023
LITERATURE = {
    "Austin TX":  (1500, 1700, "NREL PVWatts + ATB 2023"),
    "London UK":  ( 900, 1050, "PVGIS 2022 UK report + BRE 2022"),
    "Sydney AU":  (1400, 1600, "PVGIS 2022 AU + CEC 2022"),
}


def fetch_pvgis_tmy(lat, lon):
    """Fetch PVGIS TMY hourly data (8760 rows)."""
    r = requests.get(
        "https://re.jrc.ec.europa.eu/api/v5_2/tmy",
        params={"lat": lat, "lon": lon, "outputformat": "json",
                "startyear": 2005, "endyear": 2020},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["outputs"]["tmy_hourly"]


def fetch_pvgis_annual(lat, lon, tilt, azimuth_deg):
    """Fetch PVGIS PVcalc annual AC energy (kWh/year) — 14% system losses."""
    r = requests.get(
        "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc",
        params={
            "lat": lat, "lon": lon,
            "peakpower": CAPACITY_KW,
            "loss": 14,              # PVGIS default 14% system losses
            "angle": abs(tilt),
            "aspect": azimuth_deg - 180,
            "outputformat": "json",
            "pvtechchoice": "crystSi",
        },
        timeout=30,
    )
    r.raise_for_status()
    out = r.json()["outputs"]
    annual = out["totals"]["fixed"]["E_y"]
    monthly = [m["E_m"] for m in out["monthly"]["fixed"]]
    return annual, monthly


def simulate_annual(hourly_rows, lat, lon, tilt, azimuth):
    """
    Run our physics chain over a full TMY year.
    Returns (annual_ac_kwh, monthly_kwh[12]).
    """
    import pandas as pd

    # Parse PVGIS TMY timestamps  (format: "20070101:0010")
    times = pd.to_datetime(
        [row["time(UTC)"] for row in hourly_rows],
        format="%Y%m%d:%H%M",
        utc=True,
    )

    dni_arr  = np.array([max(row.get("Gb(n)", 0) or 0, 0) for row in hourly_rows])
    dhi_arr  = np.array([max(row.get("Gd(h)", 0) or 0, 0) for row in hourly_rows])
    ghi_arr  = np.array([max(row.get("G(h)",  0) or 0, 0) for row in hourly_rows])
    temp_arr = np.array([row.get("T2m",  25) or 25        for row in hourly_rows])
    wind_arr = np.array([max(row.get("WS10m", 1) or 1, 0) for row in hourly_rows])

    loc       = pvlib.location.Location(lat, lon, tz="UTC")
    sp        = loc.get_solarposition(times)
    dni_extra = pvlib.irradiance.get_extra_radiation(times).values
    airmass   = pvlib.atmosphere.get_relative_airmass(sp["apparent_zenith"].values)

    annual_kwh  = 0.0
    monthly_kwh = np.zeros(12)

    for i in range(len(times)):
        zen = float(sp["apparent_zenith"].iloc[i])
        if zen >= 90:
            continue

        saz = float(sp["azimuth"].iloc[i])
        dni = float(dni_arr[i])
        dhi = float(dhi_arr[i])
        ghi = float(ghi_arr[i])
        am  = float(airmass[i]) if not np.isnan(airmass[i]) else 2.0
        dne = float(dni_extra[i])

        try:
            poa = pvlib.irradiance.get_total_irradiance(
                tilt, azimuth, zen, saz, dni, ghi, dhi,
                dni_extra=dne, airmass=am, albedo=ALBEDO, model='perez',
            )
            poa_g = float(poa["poa_global"] or 0)
        except Exception:
            poa_g = 0.0

        if poa_g <= 0:
            continue

        # SAPM cell temperature (open-rack glass/glass parameters)
        t_cell = pvlib.temperature.sapm_cell(
            poa_g, temp_arr[i], wind_arr[i], a=-3.56, b=-0.075, deltaT=3
        )
        temp_factor = 1 + TEMP_COEFF * (float(t_cell) - 25)
        dc_kw = poa_g * PANEL_AREA * PANEL_EFF * N_PANELS * max(temp_factor, 0) / 1000
        ac_kw = dc_kw * INVERTER_EFF * DERATE

        annual_kwh += ac_kw   # × 1 h = kWh
        monthly_kwh[times[i].month - 1] += ac_kw

    return annual_kwh, monthly_kwh


# -- Run -----------------------------------------------------------------------

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

print("=" * 65)
print(f"  Solar Physics Validation")
print(f"  Module : {MODULE}")
print(f"  System : {N_PANELS} × {PANEL_POWER_W}W = {CAPACITY_KW:.1f} kWp")
print(f"  Derate : {DERATE:.4f}  |  Inverter eff: {INVERTER_EFF}")
print("=" * 65)

all_results = []

for name, lat, lon, tilt, azimuth, country in LOCATIONS:
    print(f"\n{'-'*65}")
    print(f"  {name}  ({lat:.2f}°, {lon:.2f}°)  tilt={tilt}°  az={azimuth}°")
    print(f"{'-'*65}")

    try:
        print("  Fetching PVGIS TMY hourly data ...", end=" ", flush=True)
        hourly = fetch_pvgis_tmy(lat, lon)
        print(f"{len(hourly)} rows")

        print("  Fetching PVGIS reference output ...", end=" ", flush=True)
        pvgis_annual, pvgis_monthly = fetch_pvgis_annual(lat, lon, tilt, azimuth)
        print(f"{pvgis_annual:,.0f} kWh/yr")

        print("  Running our physics chain ...", end=" ", flush=True)
        our_annual, our_monthly = simulate_annual(hourly, lat, lon, tilt, azimuth)
        print(f"{our_annual:,.0f} kWh/yr")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        continue

    specific_yield = our_annual / CAPACITY_KW
    cap_factor     = our_annual / (CAPACITY_KW * 8760) * 100
    diff_pct       = (our_annual / pvgis_annual - 1) * 100 if pvgis_annual else 0

    lit_lo, lit_hi, lit_src = LITERATURE[name]
    lit_mid_kwh = (lit_lo + lit_hi) / 2 * CAPACITY_KW

    print()
    print(f"  {'Metric':<32} {'Value':>12}")
    print(f"  {'-'*46}")
    print(f"  {'Our model (kWh/year)':<32} {our_annual:>12,.0f}")
    print(f"  {'PVGIS reference (kWh/year)':<32} {pvgis_annual:>12,.0f}")
    print(f"  {'Difference vs PVGIS':<32} {diff_pct:>+11.1f}%")
    print(f"  {'Specific yield (kWh/kWp/yr)':<32} {specific_yield:>12,.0f}")
    print(f"  {'Capacity factor':<32} {cap_factor:>11.1f}%")
    print(f"  {'Literature range (kWh/kWp/yr)':<32} {lit_lo:>6}–{lit_hi:<6}  [{lit_src}]")
    in_range = lit_lo <= specific_yield <= lit_hi
    print(f"  {'In literature range?':<32} {'YES OK' if in_range else 'NO — outside range':>12}")

    print()
    print(f"  Monthly breakdown (kWh):")
    print(f"  {'Mo':<5} {'Our':>8} {'PVGIS':>8} {'Diff':>7}")
    print(f"  {'-'*32}")
    for m in range(12):
        d = (our_monthly[m]/pvgis_monthly[m]-1)*100 if pvgis_monthly[m] else 0
        flag = " !" if abs(d) > 20 else ""
        print(f"  {MONTHS[m]:<5} {our_monthly[m]:>8.0f} {pvgis_monthly[m]:>8.0f} {d:>+6.1f}%{flag}")
    print(f"  {'-'*32}")
    print(f"  {'Total':<5} {our_annual:>8.0f} {pvgis_annual:>8.0f} {diff_pct:>+6.1f}%")

    all_results.append((name, our_annual, pvgis_annual, specific_yield, diff_pct,
                        lit_lo, lit_hi, in_range))

# -- Summary -------------------------------------------------------------------
print(f"\n{'='*65}")
print("  SUMMARY")
print(f"{'='*65}")
print(f"  {'Location':<14} {'Our (kWh/yr)':>14} {'PVGIS (kWh/yr)':>15} {'Diff':>7} {'In lit. range?':>15}")
print(f"  {'-'*65}")
for name, our, pvg, sy, dp, lo, hi, ok in all_results:
    print(f"  {name:<14} {our:>14,.0f} {pvg:>15,.0f} {dp:>+6.1f}% {'YES OK' if ok else 'NO FAIL':>15}")

print(f"\n  Note: PVGIS reference uses 14% fixed system losses.")
print(f"  Our model uses explicit loss chain: derate={DERATE:.4f},")
print(f"  inverter={INVERTER_EFF}, SAPM cell temp, Perez sky model.")
print(f"  Expected our model to run ~{(1 - DERATE*INVERTER_EFF)*100:.1f}% total losses")
print(f"  vs PVGIS 14% losses. Small systematic offset is expected.")
