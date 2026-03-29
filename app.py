import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pysolar")

import streamlit as st
from streamlit_folium import st_folium
import folium
from datetime import datetime, date, timedelta
import pytz
from pysolar.solar import get_altitude, get_azimuth
import math
import json
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import requests
import os
from dotenv import load_dotenv
import pvlib

load_dotenv()

# ── Secrets ────────────────────────────────────────────────────────────────────

def _secret(key):
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError, AttributeError):
        return os.getenv(key)

OPENWEATHER_API_KEY = _secret("OPENWEATHER_API_KEY")
NREL_API_KEY        = _secret("NREL_API_KEY")
TIMEZONE_API_KEY    = _secret("TIMEZONE_API_KEY")
CESIUM_ION_TOKEN    = _secret("CESIUM_ION_TOKEN") or ""
OPENEI_API_KEY      = _secret("OPENEI_API_KEY")

# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_PANEL_AREA  = 1.68
DEFAULT_PANEL_EFF   = 0.22
DEFAULT_PANEL_COST  = 1000

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

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Solar Dashboard",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.card {
    background: #1e1e2e;
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 14px;
}
.card-title {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #888;
    margin-bottom: 4px;
}
.card-value {
    font-size: 2rem;
    font-weight: 700;
    color: #f5f5f5;
    line-height: 1.1;
}
.card-sub {
    font-size: 0.8rem;
    color: #aaa;
    margin-top: 4px;
}
.badge-good  { color: #4ade80; font-weight:700; }
.badge-ok    { color: #facc15; font-weight:700; }
.badge-poor  { color: #f87171; font-weight:700; }
.section-header {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #666;
    border-bottom: 1px solid #333;
    padding-bottom: 6px;
    margin: 18px 0 10px 0;
}
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── API helpers ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def search_location(query):
    url = (f"http://api.openweathermap.org/geo/1.0/direct"
           f"?q={query}&limit=1&appid={OPENWEATHER_API_KEY}")
    try:
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        d = r.json()
        if d:
            return d[0]["lat"], d[0]["lon"], d[0].get("name", query), d[0].get("country", "")
    except Exception:
        pass
    return None, None, None, None


@st.cache_data(ttl=86400)
def fetch_timezone(lat, lon):
    if not TIMEZONE_API_KEY:
        return "UTC"
    url = (f"http://api.timezonedb.com/v2.1/get-time-zone"
           f"?key={TIMEZONE_API_KEY}&format=json&by=position&lat={lat}&lng={lon}")
    try:
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        return r.json().get("zoneName", "UTC")
    except Exception:
        return "UTC"


@st.cache_data(ttl=1800)
def fetch_open_meteo(lat, lon):
    """Fetch hourly irradiance + weather from Open-Meteo (free, no key)."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=direct_normal_irradiance,diffuse_radiation,shortwave_radiation,"
        "precipitation,temperature_2m,cloudcover,windspeed_10m"
        "&timezone=auto&forecast_days=1"
    )
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly", {})
        times  = hourly.get("time", [])
        result = {}
        for i, t in enumerate(times):
            h = int(t[11:13])
            result[h] = {
                "dni":   hourly.get("direct_normal_irradiance", [0]*24)[i] or 0,
                "dhi":   hourly.get("diffuse_radiation",        [0]*24)[i] or 0,
                "ghi":   hourly.get("shortwave_radiation",      [0]*24)[i] or 0,
                "precip":hourly.get("precipitation",            [0]*24)[i] or 0,
                "temp":  hourly.get("temperature_2m",           [25]*24)[i] or 25,
                "wind":  hourly.get("windspeed_10m",            [1]*24)[i] or 1,
                "cloud": hourly.get("cloudcover",               [30]*24)[i] or 0,
                "desc":  "Live forecast",
            }
        return result
    except Exception:
        return {}


@st.cache_data(ttl=86400)
def fetch_open_meteo_historical_precip(lat, lon):
    """Fetch 30 days of daily precipitation for Kimber soiling model."""
    end   = date.today() - timedelta(days=1)
    start = end - timedelta(days=29)
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={start}&end_date={end}"
        "&daily=precipitation_sum&timezone=auto"
    )
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        precip = data.get("daily", {}).get("precipitation_sum", [])
        return [p or 0.0 for p in precip]
    except Exception:
        return [1.0] * 30  # assume clean panels on fallback


@st.cache_data(ttl=86400)
def fetch_nrel_rate(lat, lon):
    if not NREL_API_KEY:
        return None
    url = (f"https://developer.nlr.gov/api/utility_rates/v3.json"
           f"?api_key={NREL_API_KEY}&lat={lat}&lon={lon}")
    try:
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        rate = r.json().get("outputs", {}).get("residential")
        return float(rate) if isinstance(rate, (int, float)) else None
    except Exception:
        return None


@st.cache_data(ttl=86400)
def fetch_pvwatts_v8(lat, lon, capacity_kw, tilt, losses_pct):
    if not NREL_API_KEY:
        return None
    url = "https://developer.nlr.gov/api/pvwatts/v8.json"
    params = {
        "api_key":         NREL_API_KEY,
        "lat":             lat,
        "lon":             lon,
        "system_capacity": capacity_kw,
        "tilt":            tilt,
        "azimuth":         180,
        "array_type":      1,
        "module_type":     0,
        "losses":          round(losses_pct, 2),
        "dc_ac_ratio":     1.2,
        "inv_eff":         96,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        outputs = r.json().get("outputs", {})
        return {
            "ac_annual":  outputs.get("ac_annual"),
            "ac_monthly": outputs.get("ac_monthly", []),
            "capacity_factor": outputs.get("capacity_factor"),
        }
    except Exception:
        return None


@st.cache_data(ttl=86400)
def fetch_pvgis_monthly(lat, lon, capacity_kw, tilt, azimuth_deg=180):
    """PVGIS PVcalc — monthly AC energy for a typical meteorological year."""
    url = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"
    # PVGIS aspect: 0=South, negative=East, positive=West (degrees from south)
    pvgis_aspect = azimuth_deg - 180
    params = {
        "lat": lat, "lon": lon,
        "peakpower": capacity_kw,
        "loss": 14,
        "angle": tilt,
        "aspect": pvgis_aspect,
        "outputformat": "json",
        "pvtechchoice": "crystSi",
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        monthly = r.json().get("outputs", {}).get("monthly", {}).get("fixed", [])
        return [m.get("E_m", 0) for m in monthly]  # kWh/month
    except Exception:
        return []


@st.cache_data(ttl=86400)
def fetch_pvgis_tilt_comparison(lat, lon, capacity_kw, azimuth_deg=180):
    """Fetch PVGIS monthly energy at 4 tilt angles for comparison chart."""
    results = {}
    for tilt_deg in [0, 30, 60, 90]:
        monthly = fetch_pvgis_monthly(lat, lon, capacity_kw, tilt_deg, azimuth_deg)
        if monthly:
            results[tilt_deg] = monthly
    return results


@st.cache_data(ttl=86400)
def fetch_pvgis_horizon(lat, lon):
    """PVGIS horizon profile — terrain obstruction angles at each azimuth."""
    url = "https://re.jrc.ec.europa.eu/api/v5_2/printhorizon"
    try:
        r = requests.get(url, params={"lat": lat, "lon": lon, "outputformat": "json"}, timeout=10)
        r.raise_for_status()
        profile = r.json().get("outputs", {}).get("horizon_profile", [])
        return [(p["A"], p["H_hor"]) for p in profile]
    except Exception:
        return []


@st.cache_data(ttl=3600)
def fetch_tou_schedule(lat, lon):
    """OpenEI URDB — TOU rate schedule for the nearest US utility."""
    if not OPENEI_API_KEY:
        return None
    url = "https://api.openei.org/utility_rates"
    params = {
        "version": 8, "format": "json", "limit": 5,
        "lat": lat, "lon": lon,
        "sector": "Residential",
        "api_key": OPENEI_API_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        items = r.json().get("items", [])
        for item in items:
            sched = item.get("energyweekdayschedule")
            struct = item.get("energyratestructure")
            if sched and struct:
                # build 24-hour rate array from schedule
                tou = []
                for hour in range(24):
                    month_idx = 0  # use January as representative
                    tier_idx  = sched[month_idx][hour]
                    try:
                        rate = struct[tier_idx][0].get("rate", 0)
                    except (IndexError, TypeError):
                        rate = 0
                    tou.append(float(rate) if rate else 0)
                if any(r > 0 for r in tou):
                    return {"name": item.get("name", "Unknown"), "rates": tou}
        return None
    except Exception:
        return None


# ── Physics ────────────────────────────────────────────────────────────────────

def calc_poa_irradiance(lat, lon, times_aware, dni_series, dhi_series, ghi_series,
                        tilt, azimuth_deg=180,
                        bifacial=False, bifaciality=0.70, albedo=0.25):
    """
    Use pvlib get_total_irradiance (Perez sky model) to compute POA irradiance.
    times_aware : list of timezone-aware datetimes (one per hour)
    dni_series  : list of DNI values (W/m²)
    dhi_series  : list of DHI values (W/m²)
    ghi_series  : list of GHI values (W/m²) — needed for ground-reflected component
    Returns list of POA global irradiance (W/m²).
    """
    idx = pd.DatetimeIndex(times_aware)
    loc = pvlib.location.Location(lat, lon)
    sp  = loc.get_solarposition(idx)

    dni_extra = pvlib.irradiance.get_extra_radiation(idx).values
    airmass   = pvlib.atmosphere.get_relative_airmass(sp["apparent_zenith"].values)

    poa_list = []
    for i in range(len(times_aware)):
        zen  = sp["apparent_zenith"].iloc[i]
        saz  = sp["azimuth"].iloc[i]
        dni  = max(float(dni_series[i]), 0)
        dhi  = max(float(dhi_series[i]), 0)
        ghi  = max(float(ghi_series[i]), 0)
        am   = airmass[i] if not np.isnan(airmass[i]) else 2.0
        dne  = dni_extra[i]

        if zen >= 90:
            poa_list.append(0.0)
            continue

        try:
            # get_total_irradiance returns beam + sky_diffuse + ground_reflected
            poa = pvlib.irradiance.get_total_irradiance(
                tilt, azimuth_deg,
                zen, saz,
                dni, ghi, dhi,
                dni_extra=dne, airmass=am,
                albedo=albedo, model='perez',
            )
            poa_direct  = float(poa.get('poa_direct',  0) or 0)
            poa_diffuse = float(poa.get('poa_diffuse', 0) or 0)

            # Incidence Angle Modifier (IAM) — reflection loss at oblique angles
            # Applied to beam only; ~0.94 effective factor for diffuse (isotropic glass)
            aoi_deg = pvlib.irradiance.aoi(tilt, azimuth_deg, zen, saz)
            iam     = float(pvlib.iam.physical(aoi_deg))
            poa_global = poa_direct * iam + poa_diffuse * 0.94
        except Exception:
            poa_global = 0.0

        if bifacial:
            # Rear-side irradiance: ground-reflected GHI onto the back surface
            gcr = 0.4
            view_factor = 0.5 * (1 - gcr) / max(gcr, 0.01)
            poa_rear    = ghi * albedo * bifaciality * view_factor * 0.85
            poa_global  += max(poa_rear, 0)

        poa_list.append(max(poa_global, 0.0))

    return poa_list


INVERTER_EFF = 0.96  # Standard residential string inverter DC→AC efficiency

def calc_system_power_kw(poa_w_m2, temp_air, wind_speed,
                         n_panels, area, eff, temp_coeff=-0.004):
    """Convert POA irradiance to system AC power using pvlib SAPM cell temp."""
    if poa_w_m2 <= 0:
        return 0.0
    t_cell      = pvlib.temperature.sapm_cell(poa_w_m2, temp_air, wind_speed,
                                               a=-3.56, b=-0.075, deltaT=3)
    temp_factor = 1 + temp_coeff * (float(t_cell) - 25)
    dc_power_kw = poa_w_m2 * area * eff * n_panels * temp_factor / 1000
    return max(dc_power_kw * INVERTER_EFF, 0.0)


def calc_soiling_losses(precip_daily, soil_rate=0.002, rain_threshold=1.0, max_soil=0.25):
    """
    Kimber soiling model.
    Returns monthly average soiling loss fraction [0, max_soil].
    """
    soiling = 0.0
    daily   = []
    for rain in precip_daily:
        if rain >= rain_threshold:
            soiling = 0.0
        else:
            soiling = min(soiling + soil_rate, max_soil)
        daily.append(soiling)
    # aggregate to monthly buckets (days 0-6=wk1, etc. — approximate equal months)
    months = {}
    n = len(daily)
    for i, v in enumerate(daily):
        m = int(i / n * 12)
        months.setdefault(m, []).append(v)
    return {m: float(np.mean(vals)) for m, vals in months.items()}


def simulate_battery(records, capacity_kwh, max_power_kw, efficiency, dod):
    """
    Daily charge/discharge simulation.
    Mutates each record dict with battery_charge, battery_discharge, soc keys.
    Returns updated records.
    """
    usable = capacity_kwh * dod
    soc    = capacity_kwh * 0.2
    for row in records:
        surplus = row["kw"] - row["load_kw"]
        if surplus > 0:
            charge         = min(surplus, max_power_kw, usable - soc)
            charge         = max(charge, 0)
            soc           += charge * efficiency
            row["exported"] = max(row.get("exported", 0) - charge, 0)
            row["battery_charge"]    = round(charge, 3)
            row["battery_discharge"] = 0.0
        else:
            deficit   = abs(surplus)
            discharge = min(deficit, max_power_kw, soc)
            discharge = max(discharge, 0)
            soc      -= discharge
            row["grid_import"]        = max(row.get("grid_import", deficit) - discharge, 0)
            row["battery_charge"]     = 0.0
            row["battery_discharge"]  = round(discharge, 3)
        row["soc"] = round(soc, 3)
    return records


def build_load_profile(archetype, scale=1.0):
    """Return 16 hourly kW load values (hours 5-20) for the chosen archetype.
    scale = daily_load_kwh; sum of returned values equals scale."""
    raw = LOAD_PROFILES.get(archetype, LOAD_PROFILES["Home all day"])
    total = sum(raw)
    return [v / total * scale for v in raw]


def payback_curve(annual_sav, system_cost, degradation_pct, years=25):
    """Return payback year and annual net value curve for a fixed horizon."""
    payback_yr = None
    net_vals = []
    cum = 0.0
    yr_sav = annual_sav
    for y in range(years + 1):
        net_vals.append(round(cum - system_cost, 2))
        if cum >= system_cost and payback_yr is None:
            payback_yr = y
        cum += yr_sav
        yr_sav *= (1 - degradation_pct / 100)
    return payback_yr, net_vals


def monthly_loan_payment(principal, apr_pct, term_years):
    """Standard amortizing loan payment formula."""
    if principal <= 0 or term_years <= 0:
        return 0.0
    r = (apr_pct / 100) / 12
    n = int(term_years * 12)
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def evaluate_financing(annual_sav, net_system_cost, degradation_pct,
                       loan_apr, loan_term_yrs, down_payment_pct,
                       lease_monthly, lease_escalator_pct, lease_term_yrs):
    """Build comparable 25-year outcomes for cash, loan, and lease/PPA modes."""
    years = list(range(26))

    # Cash
    cash_payback, cash_net = payback_curve(annual_sav, net_system_cost, degradation_pct)

    # Loan
    down_payment = net_system_cost * (down_payment_pct / 100)
    financed_principal = max(net_system_cost - down_payment, 0)
    loan_monthly = monthly_loan_payment(financed_principal, loan_apr, loan_term_yrs)
    loan_annual_payment = loan_monthly * 12
    loan_net_vals = []
    loan_cum = -down_payment
    loan_payback = None
    yr_sav = annual_sav
    for y in years:
        loan_net_vals.append(round(loan_cum, 2))
        if loan_cum >= 0 and loan_payback is None:
            loan_payback = y
        payment = loan_annual_payment if y < loan_term_yrs else 0
        loan_cum += (yr_sav - payment)
        yr_sav *= (1 - degradation_pct / 100)

    # Lease / PPA
    lease_annual = lease_monthly * 12
    lease_net_vals = []
    lease_cum = 0.0
    lease_payback = 0
    yr_sav = annual_sav
    for y in years:
        lease_net_vals.append(round(lease_cum, 2))
        lease_payment = lease_annual if y < lease_term_yrs else 0
        lease_cum += (yr_sav - lease_payment)
        yr_sav *= (1 - degradation_pct / 100)
        if y < lease_term_yrs:
            lease_annual *= (1 + lease_escalator_pct / 100)

    return {
        "cash": {
            "payback_yr": cash_payback,
            "net_vals": cash_net,
            "monthly_payment": 0.0,
            "upfront": net_system_cost,
            "profit_25": cash_net[-1],
        },
        "loan": {
            "payback_yr": loan_payback,
            "net_vals": loan_net_vals,
            "monthly_payment": loan_monthly,
            "upfront": down_payment,
            "profit_25": loan_net_vals[-1],
        },
        "lease": {
            "payback_yr": lease_payback,
            "net_vals": lease_net_vals,
            "monthly_payment": lease_monthly,
            "upfront": 0.0,
            "profit_25": lease_net_vals[-1],
        },
    }


def calc_string_sizing(panel_voc, panel_vmp, temp_coeff_voc_pct, min_temp_c,
                       inverter_max_dc_v, mppt_min_v, mppt_max_v,
                       inverter_mppts, strings_per_mppt_max):
    """Return valid module-per-string range based on voltage constraints."""
    cold_delta = 25 - min_temp_c
    temp_gain = abs(temp_coeff_voc_pct) / 100 * cold_delta
    voc_cold = panel_voc * (1 + temp_gain)

    max_by_abs_dc = math.floor(inverter_max_dc_v / voc_cold) if voc_cold > 0 else 0
    min_by_mppt = math.ceil(mppt_min_v / panel_vmp) if panel_vmp > 0 else 0
    max_by_mppt = math.floor(mppt_max_v / panel_vmp) if panel_vmp > 0 else 0

    min_valid = max(1, min_by_mppt)
    max_valid = min(max_by_abs_dc, max_by_mppt)

    return {
        "voc_cold": voc_cold,
        "min_valid": min_valid,
        "max_valid": max_valid,
        "max_total_modules": max_valid * inverter_mppts * strings_per_mppt_max if max_valid > 0 else 0,
    }


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ☀️ Solar Dashboard")

    # ── Location ──────────────────────────────────────────────────────────────
    with st.expander("📍 Location", expanded=True):
        query    = st.text_input("Search location", placeholder="e.g. Mumbai, Austin TX")
        sel_date = st.date_input(
            "Analysis date",
            value=date.today(),
            min_value=date.today() - timedelta(days=365),
            max_value=date.today() + timedelta(days=365),
        )

    # ── Site Comparison ───────────────────────────────────────────────────────
    with st.expander("🗺️ Site Comparison"):
        compare_sites_raw = st.text_area(
            "Compare sites (one address per line)",
            placeholder="Phoenix AZ\nSeattle WA\nMiami FL",
            height=80,
        )

    # ── Solar System ──────────────────────────────────────────────────────────
    with st.expander("⚡ Solar System", expanded=True):
        n_panels   = st.number_input("Number of panels", 1, 500, 10)
        panel_eff  = st.slider("Efficiency (%)", 15, 24, 22) / 100
        panel_area = st.number_input("Area per panel (m²)", 1.0, 3.0, DEFAULT_PANEL_AREA, step=0.01)
        tilt       = st.slider("Panel tilt (°)", 0, 60, 20,
                               help="Set to ~your latitude for optimal fixed mount")
        azimuth    = st.slider("Panel azimuth (°)", 0, 359, 180,
                               help="180 = south-facing (northern hemisphere)")
        temp_coeff = st.slider("Temp coefficient (%/°C)", -0.6, -0.2, -0.4, step=0.05) / 100

        st.markdown("**Advanced**")
        bifacial_on  = st.checkbox("Bifacial panels")
        bifaciality  = st.slider("Bifaciality factor", 0.60, 0.90, 0.70,
                                  step=0.01) if bifacial_on else 0.70
        albedo_label = st.selectbox("Ground surface", list(ALBEDO_OPTIONS.keys()),
                                     index=0) if bifacial_on else "Concrete"
        albedo       = ALBEDO_OPTIONS.get(albedo_label, 0.25)
        show_tilt_cmp = st.checkbox("Show PVGIS tilt comparison", value=True)

    # ── Financials ────────────────────────────────────────────────────────────
    with st.expander("💰 Financials", expanded=True):
        cost_per_panel = st.number_input("Cost per panel ($)", 0, 10000,
                                          DEFAULT_PANEL_COST, step=50)
        battery_cost   = st.number_input("Battery cost ($)", 0, 50000, 0, step=500)
        degradation    = st.number_input("Annual degradation (%/yr)", 0.0, 5.0, 0.5, step=0.1)

        st.markdown("**Loss Factors (PVWatts v8)**")
        loss_soiling     = st.slider("Soiling (%)",     0.0, 10.0, 2.0, step=0.5)
        loss_mismatch    = st.slider("Mismatch (%)",    0.0,  5.0, 2.0, step=0.5)
        loss_wiring      = st.slider("Wiring (%)",      0.0,  5.0, 2.0, step=0.5)
        loss_lid         = st.slider("LID (%)",         0.0,  5.0, 1.5, step=0.5)
        loss_availability= st.slider("Availability (%)",0.0, 10.0, 3.0, step=0.5)

    # ── Incentives ────────────────────────────────────────────────────────────
    with st.expander("🏛️ Incentives"):
        federal_itc_pct = st.slider("Federal ITC (%)", 0, 50, 30,
                                    help="US federal tax credit default is 30%")
        state_rebate = st.number_input("State/local rebate ($)", 0, 50000, 0, step=250)

    # ── Financing ─────────────────────────────────────────────────────────────
    with st.expander("💳 Financing"):
        st.caption("Compare cash vs loan vs lease/PPA using these assumptions.")
        loan_apr = st.number_input("Loan APR (%)", 0.0, 25.0, 6.5, step=0.1)
        loan_term_yrs = st.slider("Loan term (years)", 1, 30, 15)
        down_payment_pct = st.slider("Loan down payment (%)", 0, 100, 20)
        lease_monthly = st.number_input("Lease/PPA monthly payment ($)", 0.0, 5000.0, 120.0, step=5.0)
        lease_escalator_pct = st.number_input("Lease annual escalator (%/yr)", 0.0, 10.0, 2.9, step=0.1)
        lease_term_yrs = st.slider("Lease term (years)", 1, 30, 20)

    # ── Electricity Rate ──────────────────────────────────────────────────────
    with st.expander("🔌 Electricity Rate", expanded=True):
        rate_mode = st.radio("Rate source", ["Auto (NREL)", "Manual"], horizontal=True)

    # ── Load Profile ──────────────────────────────────────────────────────────
    with st.expander("🏠 Load Profile"):
        load_archetype  = st.selectbox("Household archetype", list(LOAD_PROFILES.keys()))
        daily_load_kwh  = st.number_input("Daily electricity use (kWh)", 5.0, 200.0, 30.0, step=1.0)
        net_meter_pct   = st.slider("Net metering credit (% of retail)", 0, 100, 50,
                                     help="100% = full net metering; ~27% = CA NEM 3.0")

    # ── Battery Storage ───────────────────────────────────────────────────────
    with st.expander("🔋 Battery Storage"):
        battery_on       = st.checkbox("Enable battery storage")
        battery_capacity = st.number_input("Capacity (kWh)", 1.0, 200.0, 13.5, step=0.5) if battery_on else 0
        battery_power    = st.number_input("Max power (kW)",  0.5,  20.0,  5.0, step=0.5) if battery_on else 0
        battery_eff      = st.slider("Round-trip efficiency (%)", 70, 98, 90) / 100 if battery_on else 0.90
        battery_dod      = st.slider("Depth of discharge (%)",   50,100, 80) / 100 if battery_on else 0.80

    # ── Monte Carlo ───────────────────────────────────────────────────────────
    with st.expander("📊 Uncertainty"):
        show_mc = st.checkbox("Show P10/P90 uncertainty bands")
        show_sensitivity = st.checkbox("Show sensitivity analysis", value=True)

    # ── String and Inverter Sizing ────────────────────────────────────────────
    with st.expander("🧰 String and Inverter Sizing"):
        show_string_wizard = st.checkbox("Enable sizing wizard")
        panel_voc = st.number_input("Panel Voc at STC (V)", 10.0, 80.0, 49.5, step=0.1)
        panel_vmp = st.number_input("Panel Vmp at STC (V)", 10.0, 80.0, 41.5, step=0.1)
        temp_coeff_voc_pct = st.number_input("Voc temp coeff (%/°C)", -1.0, 0.0, -0.28, step=0.01)
        min_temp_c = st.number_input("Coldest design temp (°C)", -40, 25, -10)
        inverter_max_dc_v = st.number_input("Inverter max DC voltage (V)", 200, 1500, 1000, step=10)
        mppt_min_v = st.number_input("MPPT min voltage (V)", 50, 1000, 200, step=10)
        mppt_max_v = st.number_input("MPPT max voltage (V)", 100, 1000, 850, step=10)
        inverter_mppts = st.number_input("Inverter MPPT count", 1, 8, 2)
        strings_per_mppt_max = st.number_input("Max strings per MPPT", 1, 6, 2)
        module_power_w = st.number_input("Panel DC rating (W)", 100, 800, 420, step=5)
        inverter_ac_kw = st.number_input("Inverter AC rating (kW)", 0.5, 200.0, 8.0, step=0.1)


# ── Gate: require API key + location ──────────────────────────────────────────

if not OPENWEATHER_API_KEY:
    st.error("Add OPENWEATHER_API_KEY to your .env or Streamlit secrets to use this dashboard.")
    st.stop()

if not query:
    st.markdown("## ☀️ Solar Dashboard")
    st.info("Enter a location in the sidebar to get started.")
    st.stop()

lat, lon, loc_name, country = search_location(query)
if not lat:
    st.error("Location not found. Try a different search.")
    st.stop()

# ── Electricity rate ───────────────────────────────────────────────────────────

nrel_rate = fetch_nrel_rate(lat, lon) if rate_mode == "Auto (NREL)" else None

with st.sidebar:
    with st.expander("🔌 Electricity Rate", expanded=True):
        if rate_mode == "Auto (NREL)":
            if nrel_rate:
                st.success(f"NREL rate: **${nrel_rate:.3f}/kWh**")
                elec_rate = nrel_rate
            else:
                st.info("NREL unavailable — enter manually.")
                elec_rate = st.number_input("Rate ($/kWh)", 0.01, 2.0, 0.12, step=0.01, key="rate_manual")
        else:
            elec_rate = st.number_input("Rate ($/kWh)", 0.01, 2.0, 0.12, step=0.01, key="rate_manual2")
            st.caption("India ~$0.08 · USA ~$0.16 · EU ~$0.30 · Japan ~$0.22")

        monthly_bill = st.number_input(
            "Monthly electricity bill ($)", 10.0, 5000.0, 120.0, step=10.0,
            help="Used for system sizing calculator",
        )

# ── CO₂ factor for this country ───────────────────────────────────────────────

co2_factor = CO2_INTENSITY.get(country, CO2_INTENSITY[""])

# ── Compute timezone + weather ────────────────────────────────────────────────

tz_name  = fetch_timezone(lat, lon)
tz       = pytz.timezone(tz_name)
forecast = fetch_open_meteo(lat, lon)
default_w = {"dni": 300, "dhi": 100, "ghi": 400, "temp": 25, "wind": 1, "cloud": 30,
             "precip": 0, "desc": "Estimated (no forecast)"}

# ── Total losses for PVWatts ──────────────────────────────────────────────────

total_loss = 100 * (1 - (1 - loss_soiling/100) * (1 - loss_mismatch/100)
                      * (1 - loss_wiring/100)   * (1 - loss_lid/100)
                      * (1 - loss_availability/100))

# ── Tilt factor (for sizing math, pvlib handles actual transposition) ─────────

tilt_factor = math.cos(math.radians(tilt - abs(lat)))
tilt_factor = max(min(tilt_factor, 1.15), 0.70)

# ── Build hourly datetime list and weather rows ───────────────────────────────

hours = list(range(5, 21))
times_aware = [tz.localize(datetime(sel_date.year, sel_date.month, sel_date.day, h, 0, 0))
               for h in hours]
weather_rows = [forecast.get(h, default_w) for h in hours]

dni_series  = [w["dni"]  for w in weather_rows]
dhi_series  = [w["dhi"]  for w in weather_rows]
ghi_series  = [w["ghi"]  for w in weather_rows]
temp_series = [w["temp"] for w in weather_rows]
wind_series = [w["wind"] for w in weather_rows]

# ── pvlib POA irradiance ──────────────────────────────────────────────────────

poa_series = calc_poa_irradiance(
    lat, lon, times_aware, dni_series, dhi_series, ghi_series,
    tilt, azimuth,
    bifacial=bifacial_on, bifaciality=bifaciality, albedo=albedo,
)

# ── Soiling model (must run before records so loss is applied) ────────────────

precip_hist     = fetch_open_meteo_historical_precip(lat, lon)
monthly_soiling = calc_soiling_losses(precip_hist)
today_soiling   = list(monthly_soiling.values())[-1] if monthly_soiling else 0.02

# Combined derate: Kimber soiling + mismatch + wiring + LID + availability
other_losses_factor = (
    (1 - loss_mismatch / 100)
    * (1 - loss_wiring / 100)
    * (1 - loss_lid / 100)
    * (1 - loss_availability / 100)
)
derate_factor = (1 - today_soiling) * other_losses_factor

# ── Build records ─────────────────────────────────────────────────────────────

load_profile = build_load_profile(load_archetype, scale=daily_load_kwh)

records = []
for i, h in enumerate(hours):
    poa  = poa_series[i]
    temp = temp_series[i]
    wind = wind_series[i]
    kw   = calc_system_power_kw(poa, temp, wind, n_panels, panel_area, panel_eff, temp_coeff) * derate_factor
    load = load_profile[i]
    sc   = min(kw, load)
    exp  = max(kw - load, 0)
    imp  = max(load - kw, 0)
    records.append({
        "hour":       h,
        "label":      f"{h:02d}:00",
        "poa":        round(poa, 1),
        "ghi":        round(weather_rows[i]["ghi"], 1),
        "dni":        round(weather_rows[i]["dni"],  1),
        "dhi":        round(weather_rows[i]["dhi"],  1),
        "kw":         round(kw, 3),
        "load_kw":    round(load, 3),
        "self_consumed": round(sc, 3),
        "exported":   round(exp, 3),
        "grid_import":round(imp, 3),
        "cloud":      weather_rows[i]["cloud"],
        "temp":       temp,
        "wind":       round(wind, 1),
        "soc":        0.0,
        "battery_charge": 0.0,
        "battery_discharge": 0.0,
    })

# ── Battery simulation ────────────────────────────────────────────────────────

if battery_on and battery_capacity > 0:
    records = simulate_battery(records, battery_capacity, battery_power,
                               battery_eff, battery_dod)

df = pd.DataFrame(records)

# ── Monte Carlo uncertainty bands ─────────────────────────────────────────────

p10_kw = p90_kw = None
if show_mc:
    mc_runs   = 200
    base_poa  = np.array([r["poa"] for r in records])
    mc_matrix = np.zeros((mc_runs, len(hours)))
    for run in range(mc_runs):
        cloud_noise = np.random.normal(0, 15, len(hours))
        poa_perturb = base_poa * (1 - 0.008 * cloud_noise)
        poa_perturb = np.clip(poa_perturb, 0, None)
        for i, poa_v in enumerate(poa_perturb):
            mc_matrix[run, i] = calc_system_power_kw(
                poa_v, temp_series[i], wind_series[i],
                n_panels, panel_area, panel_eff, temp_coeff,
            ) * derate_factor
    p10_kw = np.percentile(mc_matrix, 10, axis=0)
    p90_kw = np.percentile(mc_matrix, 90, axis=0)
    df["p10_kw"] = p10_kw
    df["p90_kw"] = p90_kw

# ── Financial calculations ────────────────────────────────────────────────────

daily_kwh        = float(df["kw"].sum())
self_consumed_kwh= float(df["self_consumed"].sum())
exported_kwh     = float(df["exported"].sum())
grid_import_kwh  = float(df["grid_import"].sum())

net_meter_rate   = elec_rate * (net_meter_pct / 100)
daily_sav        = self_consumed_kwh * elec_rate + exported_kwh * net_meter_rate

# ── Annual figures — use PVGIS TMY seasonal data instead of single-day × 365 ──

capacity_kw   = n_panels * panel_area * panel_eff
pvgis_monthly = fetch_pvgis_monthly(lat, lon, capacity_kw, tilt, azimuth)

if pvgis_monthly:
    annual_kwh  = sum(pvgis_monthly)
    # Preserve the self-consumption / export split from the hourly simulation
    sc_frac     = self_consumed_kwh / daily_kwh if daily_kwh > 0 else 0.7
    ex_frac     = exported_kwh / daily_kwh if daily_kwh > 0 else 0.3
    annual_sav  = annual_kwh * (sc_frac * elec_rate + ex_frac * net_meter_rate)
else:
    annual_kwh  = daily_kwh * 365
    annual_sav  = daily_sav * 365
co2_kg      = annual_kwh * co2_factor
trees       = co2_kg / 21
cars        = co2_kg / 4600
gross_system_cost = n_panels * cost_per_panel + battery_cost
federal_itc_value = gross_system_cost * (federal_itc_pct / 100)
net_system_cost   = max(gross_system_cost - federal_itc_value - state_rebate, 0)

# Payback curve
payback_yr, net_vals = payback_curve(annual_sav, net_system_cost, degradation)

# Energy degradation curve
degradation_years = list(range(26))
annual_energy_curve = [annual_kwh * ((1 - degradation / 100) ** y) for y in degradation_years]

# Financing comparison
fin = evaluate_financing(
    annual_sav,
    net_system_cost,
    degradation,
    loan_apr,
    loan_term_yrs,
    down_payment_pct,
    lease_monthly,
    lease_escalator_pct,
    lease_term_yrs,
)

# Sensitivity setup (+/-20% around base case)
def _profit_25(annual_sav_v, system_cost_v, degradation_v):
    return payback_curve(annual_sav_v, system_cost_v, degradation_v)[1][-1]

base_profit_25 = _profit_25(annual_sav, net_system_cost, degradation)
sensitivity_items = [
    ("Annual savings", annual_sav, 1, 1, degradation),
    ("Net system cost", net_system_cost, 1, 1, degradation),
    ("Electric rate", elec_rate, annual_sav / elec_rate if elec_rate > 0 else 0, 1, degradation),
    ("Degradation", degradation, annual_sav, net_system_cost, 1),
]

sensitivity_rows = []
for label, base_v, a_ref, c_ref, d_ref in sensitivity_items:
    if label == "Degradation":
        low_v = max(base_v * 0.8, 0)
        high_v = min(base_v * 1.2, 15)
        low_profit = _profit_25(a_ref, c_ref, low_v)
        high_profit = _profit_25(a_ref, c_ref, high_v)
    elif label == "Annual savings":
        low_profit = _profit_25(base_v * 0.8, net_system_cost, degradation)
        high_profit = _profit_25(base_v * 1.2, net_system_cost, degradation)
    elif label == "Net system cost":
        low_profit = _profit_25(annual_sav, max(base_v * 0.8, 0), degradation)
        high_profit = _profit_25(annual_sav, base_v * 1.2, degradation)
    else:  # Electric rate
        low_rate = base_v * 0.8
        high_rate = base_v * 1.2
        low_profit = _profit_25(annual_sav * (low_rate / base_v), net_system_cost, degradation) if base_v > 0 else base_profit_25
        high_profit = _profit_25(annual_sav * (high_rate / base_v), net_system_cost, degradation) if base_v > 0 else base_profit_25

    sensitivity_rows.append({
        "parameter": label,
        "low_delta": low_profit - base_profit_25,
        "high_delta": high_profit - base_profit_25,
    })

# String and inverter sizing
string_result = calc_string_sizing(
    panel_voc, panel_vmp, temp_coeff_voc_pct, min_temp_c,
    inverter_max_dc_v, mppt_min_v, mppt_max_v,
    inverter_mppts, strings_per_mppt_max,
)
dc_kw_nameplate = n_panels * module_power_w / 1000
dc_ac_ratio = dc_kw_nameplate / inverter_ac_kw if inverter_ac_kw > 0 else 0

# Sizing
daily_needed   = (monthly_bill / elec_rate) / 30 if elec_rate else 10
kwh_per_panel  = daily_kwh / n_panels if n_panels and daily_kwh > 0 else 0.1
panels_needed  = math.ceil(daily_needed / kwh_per_panel) if kwh_per_panel else 0

# Self-consumption stats
self_consump_pct  = self_consumed_kwh / daily_kwh * 100 if daily_kwh > 0 else 0
load_in_window    = float(df["load_kw"].sum())
self_suffic_pct   = min(self_consumed_kwh / load_in_window * 100, 100) if load_in_window > 0 else 0
grid_indep_hrs    = int(df["grid_import"].eq(0).sum())

# Avg cloud
avg_cloud = float(df["cloud"].mean())
if avg_cloud < 30:
    status_label, status_cls = "Excellent", "badge-good"
elif avg_cloud < 60:
    status_label, status_cls = "Good", "badge-ok"
else:
    status_label, status_cls = "Poor", "badge-poor"

peak_kw = float(df["kw"].max())

# ── Dashboard header ───────────────────────────────────────────────────────────

st.markdown(
    f"## {loc_name}, {country} &nbsp;·&nbsp; "
    f"<span style='font-size:1rem;color:#888'>{sel_date.strftime('%A, %B %d %Y')}</span> "
    f"&nbsp;·&nbsp; Conditions: <span class='{status_cls}'>{status_label}</span>",
    unsafe_allow_html=True,
)
st.caption(
    f"{lat:.4f}°, {lon:.4f}° &nbsp;|&nbsp; Timezone: {tz_name} &nbsp;|&nbsp; "
    f"CO₂ factor: {co2_factor} kg/kWh ({country}) &nbsp;|&nbsp; "
    f"Tilt factor: {tilt_factor:.2f} (approx display only — pvlib handles transposition) &nbsp;|&nbsp; "
    f"Soiling today: {today_soiling*100:.1f}% (applied) &nbsp;|&nbsp; "
    f"Derate factor: {derate_factor:.3f} &nbsp;|&nbsp; "
    f"{'Open-Meteo live' if forecast else 'Default weather'}"
)

# ── Row 1: KPI cards ───────────────────────────────────────────────────────────

def kpi(col, title, value, sub=""):
    col.markdown(
        f'<div class="card">'
        f'<div class="card-title">{title}</div>'
        f'<div class="card-value">{value}</div>'
        f'<div class="card-sub">{sub}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
kpi(c1, "Daily Output",    f"{daily_kwh:.1f} kWh",   f"Peak {peak_kw:.1f} kW")
kpi(c2, "Daily Savings",   f"${daily_sav:.2f}",      f"@ ${elec_rate:.3f}/kWh")
kpi(c3, "Annual Savings",  f"${annual_sav:,.0f}",    f"{annual_kwh:,.0f} kWh/yr {'(PVGIS TMY)' if pvgis_monthly else '(est.)'}")
kpi(c4, "Payback",
    f"{payback_yr} yr" if payback_yr else ">25 yr",
    f"${net_system_cost:,.0f} net cost")
kpi(c5, "CO₂ Offset",       f"{co2_kg:.0f} kg/yr",   f"≈ {trees:.0f} trees · {cars:.2f} cars")
kpi(c6, "Panels Needed",    f"{panels_needed}",      f"for ${monthly_bill:.0f}/mo bill")
kpi(c7, "Self-Consumed",    f"{self_consump_pct:.0f}%", f"{self_consumed_kwh:.1f} kWh/day")
kpi(c8, "Self-Sufficient",  f"{self_suffic_pct:.0f}%",  f"{grid_indep_hrs} grid-free hrs")

st.caption(
    f"Gross cost ${gross_system_cost:,.0f} · ITC ${federal_itc_value:,.0f} · "
    f"Rebate ${state_rebate:,.0f} · Net cost ${net_system_cost:,.0f}"
)

# ── Row 2: Hourly chart + Map ──────────────────────────────────────────────────

col_chart, col_map = st.columns([3, 2])

with col_chart:
    st.markdown('<div class="section-header">Hourly Power Output</div>', unsafe_allow_html=True)

    fig = go.Figure()

    # Monte Carlo bands
    if show_mc and p10_kw is not None:
        fig.add_trace(go.Scatter(
            x=df["label"], y=df["p90_kw"], name="P90",
            line=dict(color="rgba(74,222,128,0.2)", width=0),
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=df["label"], y=df["p10_kw"], name="P10/P90 band",
            fill="tonexty", fillcolor="rgba(74,222,128,0.12)",
            line=dict(color="rgba(74,222,128,0.2)", width=0),
            hovertemplate="P10 %{y:.2f} kW<extra></extra>",
        ))

    # Cloud cover shading
    fig.add_trace(go.Bar(
        x=df["label"], y=df["cloud"],
        name="Cloud cover (%)", yaxis="y3",
        marker_color="rgba(100,130,180,0.18)",
        hovertemplate="%{y}% cloud<extra></extra>",
    ))

    # POA irradiance line
    fig.add_trace(go.Scatter(
        x=df["label"], y=df["poa"],
        name="POA (W/m²)", yaxis="y2",
        line=dict(color="#60a5fa", width=1.5, dash="dot"),
        hovertemplate="POA %{y:.0f} W/m²<extra></extra>",
    ))

    # Load profile line
    fig.add_trace(go.Scatter(
        x=df["label"], y=df["load_kw"],
        name="Load (kW)",
        line=dict(color="rgba(255,255,255,0.5)", width=1.5, dash="dash"),
        hovertemplate="Load %{y:.2f} kW<extra></extra>",
    ))

    # Battery SOC
    if battery_on and battery_capacity > 0:
        fig.add_trace(go.Scatter(
            x=df["label"], y=df["soc"],
            name="Battery SOC (kWh)", yaxis="y2",
            fill="tozeroy", fillcolor="rgba(250,204,21,0.08)",
            line=dict(color="#facc15", width=1),
            hovertemplate="SOC %{y:.1f} kWh<extra></extra>",
        ))

    # Power bars
    fig.add_trace(go.Bar(
        x=df["label"], y=df["kw"],
        name="System power (kW)",
        marker=dict(
            color=df["kw"],
            colorscale=[[0, "#f97316"], [0.5, "#facc15"], [1, "#4ade80"]],
            showscale=False,
        ),
        hovertemplate="%{y:.2f} kW<extra></extra>",
    ))

    fig.update_layout(
        height=380,
        margin=dict(t=20, b=10, l=0, r=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        legend=dict(orientation="h", y=1.1, x=0),
        barmode="overlay",
        xaxis=dict(gridcolor="#333", title="Hour"),
        yaxis=dict(title="Power (kW)", gridcolor="#333"),
        yaxis2=dict(title="POA / SOC", overlaying="y", side="right",
                    showgrid=False, range=[0, 1200]),
        yaxis3=dict(overlaying="y", side="right", showgrid=False,
                    range=[0, 300], visible=False),
    )
    st.plotly_chart(fig, use_container_width=True)

with col_map:
    st.markdown('<div class="section-header">Location</div>', unsafe_allow_html=True)
    if CESIUM_ION_TOKEN:
        # Cesium 3D globe
        cesium_html = f"""
        <!DOCTYPE html><html><head>
        <script src="https://cesium.com/downloads/cesiumjs/releases/1.117/Build/Cesium/Cesium.js"></script>
        <link href="https://cesium.com/downloads/cesiumjs/releases/1.117/Build/Cesium/Widgets/widgets.css" rel="stylesheet">
        <style>html,body,#c{{margin:0;padding:0;width:100%;height:420px;background:#000}}</style>
        </head><body>
        <div id="c"></div>
        <script>
        Cesium.Ion.defaultAccessToken = '{CESIUM_ION_TOKEN}';
        const viewer = new Cesium.Viewer('c', {{
            terrainProvider: Cesium.createWorldTerrain(),
            timeline:false, animation:false, baseLayerPicker:false,
            geocoder:false, homeButton:false, sceneModePicker:false,
            navigationHelpButton:false, shadows:true
        }});
        viewer.scene.primitives.add(Cesium.createOsmBuildings());
        viewer.camera.flyTo({{
            destination: Cesium.Cartesian3.fromDegrees({lon}, {lat}, 600),
            orientation: {{heading:0, pitch:-0.6, roll:0}}
        }});
        viewer.entities.add({{
            position: Cesium.Cartesian3.fromDegrees({lon}, {lat}, 5),
            point: {{pixelSize:14, color:Cesium.Color.fromCssColorString('#f97316')}},
            label: {{text:'{loc_name}: {daily_kwh:.1f} kWh/day',
                     font:'12px sans-serif',
                     fillColor:Cesium.Color.WHITE,
                     pixelOffset:new Cesium.Cartesian2(0,-24)}}
        }});
        const d = new Date('{sel_date.year}-{sel_date.month:02d}-{sel_date.day:02d}T12:00:00Z');
        viewer.clock.currentTime = Cesium.JulianDate.fromDate(d);
        viewer.clock.shouldAnimate = false;
        </script></body></html>
        """
        st.components.v1.html(cesium_html, height=430, scrolling=False)
    else:
        m = folium.Map(location=[lat, lon], zoom_start=8, tiles="CartoDB dark_matter")
        folium.CircleMarker(
            [lat, lon], radius=10,
            color="#f97316", fill=True, fill_color="#f97316", fill_opacity=0.8,
            popup=f"{loc_name} — {daily_kwh:.1f} kWh/day",
        ).add_to(m)
        st_folium(m, width=None, height=380)
        if not CESIUM_ION_TOKEN:
            st.caption("Add CESIUM_ION_TOKEN to secrets for 3D globe view.")

# ── Row 3: ROI chart + System Sizing ──────────────────────────────────────────

col_roi, col_size = st.columns(2)

with col_roi:
    st.markdown('<div class="section-header">25-Year ROI</div>', unsafe_allow_html=True)

    years = list(range(26))
    fig2  = go.Figure()
    fig2.add_trace(go.Scatter(
        x=years, y=net_vals,
        name="Net value",
        fill="tozeroy",
        fillcolor="rgba(74,222,128,0.12)",
        line=dict(color="#4ade80", width=2),
        hovertemplate="Year %{x}: $%{y:,.0f}<extra></extra>",
    ))
    fig2.add_hline(y=0, line_color="#666", line_dash="dash")
    if payback_yr:
        fig2.add_vline(
            x=payback_yr, line_color="#facc15", line_dash="dot",
            annotation_text=f"Break-even yr {payback_yr}",
            annotation_font_color="#facc15",
        )
    fig2.update_layout(
        height=280,
        margin=dict(t=10, b=10, l=0, r=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        xaxis=dict(title="Year", gridcolor="#333"),
        yaxis=dict(title="Net value ($)", gridcolor="#333"),
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)

    r1, r2, r3 = st.columns(3)
    r1.metric("Payback", f"{payback_yr} yr" if payback_yr else ">25 yr")
    profit_25 = net_vals[-1]
    roi_pct   = profit_25 / net_system_cost * 100 if net_system_cost else 0
    r2.metric("25-yr net profit", f"${profit_25:,.0f}", delta=f"{roi_pct:.0f}% ROI")

    # PVWatts v8 cross-validation
    pvw = fetch_pvwatts_v8(lat, lon, capacity_kw, tilt, total_loss) if NREL_API_KEY else None
    if pvw and pvw.get("ac_annual"):
        r3.metric("PVWatts v8 yield", f"{pvw['ac_annual']:,.0f} kWh/yr",
                  delta=f"CF {pvw['capacity_factor']:.1f}%")
    else:
        r3.metric("PVWatts v8", "—", delta="Add NREL key")

with col_size:
    st.markdown('<div class="section-header">System Sizing</div>', unsafe_allow_html=True)

    panel_range = list(range(1, min(panels_needed * 2 + 5, 51)))
    offset_pct  = [min(p * kwh_per_panel / daily_needed * 100, 100) for p in panel_range]
    cost_range  = [p * cost_per_panel for p in panel_range]

    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=panel_range, y=offset_pct,
        name="Bill offset (%)",
        fill="tozeroy", fillcolor="rgba(250,204,21,0.12)",
        line=dict(color="#facc15", width=2),
        hovertemplate="%{x} panels → %{y:.0f}% offset<extra></extra>",
    ))
    fig3.add_trace(go.Scatter(
        x=panel_range, y=cost_range,
        name="System cost ($)", yaxis="y2",
        line=dict(color="#f97316", width=1.5, dash="dot"),
        hovertemplate="$%{y:,}<extra></extra>",
    ))
    if panels_needed and panels_needed <= max(panel_range):
        fig3.add_vline(x=panels_needed, line_color="#4ade80", line_dash="dot",
                       annotation_text=f"{panels_needed} panels",
                       annotation_font_color="#4ade80")
    fig3.update_layout(
        height=280,
        margin=dict(t=10, b=10, l=0, r=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        legend=dict(orientation="h", y=1.08),
        xaxis=dict(title="Number of panels", gridcolor="#333"),
        yaxis=dict(title="Bill offset (%)", range=[0, 105], gridcolor="#333"),
        yaxis2=dict(title="Cost ($)", overlaying="y", side="right", showgrid=False),
    )
    st.plotly_chart(fig3, use_container_width=True)
    st.markdown(
        f"**{panels_needed} panels** cover 100% of your "
        f"**${monthly_bill:.0f}/mo** bill &nbsp;·&nbsp; "
        f"Est. cost **${panels_needed * cost_per_panel:,}**"
    )

# ── Row 4: PVGIS Seasonal + Tilt Comparison ───────────────────────────────────

st.markdown('<div class="section-header">PVGIS — Seasonal & Tilt Analysis</div>',
            unsafe_allow_html=True)
col_pvgis, col_tilt = st.columns(2)

MONTH_LABELS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

with col_pvgis:
    if pvgis_monthly:
        figp = go.Figure(go.Bar(
            x=MONTH_LABELS, y=pvgis_monthly,
            marker=dict(
                color=pvgis_monthly,
                colorscale=[[0,"#1e3a5f"],[0.5,"#facc15"],[1,"#f97316"]],
                showscale=False,
            ),
            hovertemplate="%{x}: %{y:.0f} kWh<extra></extra>",
        ))

        if pvw and pvw.get("ac_monthly"):
            figp.add_trace(go.Scatter(
                x=MONTH_LABELS, y=pvw["ac_monthly"],
                name="PVWatts v8",
                line=dict(color="#60a5fa", width=1.5, dash="dot"),
                hovertemplate="PVWatts %{x}: %{y:.0f} kWh<extra></extra>",
            ))

        figp.update_layout(
            height=260, title="Monthly Energy — PVGIS TMY",
            margin=dict(t=30,b=10,l=0,r=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc"),
            xaxis=dict(gridcolor="#333"),
            yaxis=dict(title="kWh/month", gridcolor="#333"),
        )
        st.plotly_chart(figp, use_container_width=True)
    else:
        st.caption("PVGIS data unavailable for this location.")

with col_tilt:
    if show_tilt_cmp:
        tilt_data = fetch_pvgis_tilt_comparison(lat, lon, capacity_kw, azimuth)
        if tilt_data:
            TILT_COLORS = {0: "#60a5fa", 30: "#4ade80", 60: "#facc15", 90: "#f97316"}
            figt = go.Figure()
            for td, monthly in tilt_data.items():
                figt.add_trace(go.Bar(
                    name=f"{td}° tilt",
                    x=MONTH_LABELS,
                    y=monthly,
                    marker_color=TILT_COLORS.get(td, "#aaa"),
                ))
            if tilt not in tilt_data:
                figt.add_vline(x=tilt, line_color="#fff", line_dash="dot",
                               annotation_text=f"Your tilt {tilt}°",
                               annotation_font_color="#fff")
            figt.update_layout(
                height=260, title="Monthly Energy by Tilt Angle",
                barmode="group",
                margin=dict(t=30,b=10,l=0,r=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#ccc"),
                legend=dict(orientation="h", y=1.2),
                xaxis=dict(gridcolor="#333"),
                yaxis=dict(title="kWh/month", gridcolor="#333"),
            )
            st.plotly_chart(figt, use_container_width=True)
        else:
            st.caption("Tilt comparison data unavailable.")
    else:
        st.caption("Enable 'Show PVGIS tilt comparison' in the sidebar.")

# ── Row 5: Sun Path + Soiling ─────────────────────────────────────────────────

st.markdown('<div class="section-header">Sun Path & Soiling</div>',
            unsafe_allow_html=True)
col_sun, col_soil = st.columns(2)

with col_sun:
    horizon = fetch_pvgis_horizon(lat, lon)
    figs = go.Figure()

    # Three representative days
    day_configs = [
        (date(sel_date.year, 6, 21),  "#f97316", "Summer solstice"),
        (date(sel_date.year, 3, 20),  "#4ade80", "Spring equinox"),
        (date(sel_date.year, 12, 21), "#60a5fa", "Winter solstice"),
    ]
    for rep_date, color, label in day_configs:
        sun_az, sun_alt = [], []
        for minute in range(5*60, 21*60, 15):
            h, m = divmod(minute, 60)
            dt   = tz.localize(datetime(rep_date.year, rep_date.month, rep_date.day, h, m, 0))
            alt  = get_altitude(lat, lon, dt)
            if alt > 0:
                az_pysolar = get_azimuth(lat, lon, dt)
                az_plotly  = (180 - az_pysolar) % 360
                sun_az.append(az_plotly)
                sun_alt.append(round(alt, 1))
        if sun_az:
            figs.add_trace(go.Scatterpolar(
                r=sun_alt, theta=sun_az,
                mode="lines", name=label,
                line=dict(color=color, width=2),
            ))

    # Horizon obstruction
    if horizon:
        h_az  = [h[0] for h in horizon]
        h_alt = [h[1] for h in horizon]
        # close the polygon
        h_az.append(h_az[0])
        h_alt.append(h_alt[0])
        figs.add_trace(go.Scatterpolar(
            r=h_alt, theta=h_az,
            fill="toself", fillcolor="rgba(248,113,113,0.25)",
            line=dict(color="#f87171", width=1),
            name="Horizon (terrain)",
        ))

    figs.update_layout(
        height=300, title="Sun Path Diagram",
        polar=dict(
            radialaxis=dict(title="Altitude (°)", range=[0, 90], gridcolor="#444"),
            angularaxis=dict(direction="clockwise", rotation=90, gridcolor="#444"),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        margin=dict(t=40, b=10, l=10, r=10),
        legend=dict(orientation="h", y=-0.1),
    )
    st.plotly_chart(figs, use_container_width=True)

with col_soil:
    if monthly_soiling:
        soil_months = [MONTH_LABELS[min(k, 11)] for k in sorted(monthly_soiling.keys())]
        soil_vals   = [v * 100 for k, v in sorted(monthly_soiling.items())]
        figsoil = go.Figure(go.Bar(
            x=soil_months, y=soil_vals,
            marker=dict(
                color=soil_vals,
                colorscale=[[0,"#4ade80"],[0.5,"#facc15"],[1,"#f87171"]],
                showscale=False,
            ),
            hovertemplate="%{x}: %{y:.1f}% soiling<extra></extra>",
        ))
        figsoil.update_layout(
            height=300, title="Monthly Soiling Loss (Kimber model)",
            margin=dict(t=40,b=10,l=0,r=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc"),
            xaxis=dict(gridcolor="#333"),
            yaxis=dict(title="Soiling loss (%)", gridcolor="#333"),
        )
        figsoil.add_annotation(
            text="Based on 30-day precipitation history (Open-Meteo)",
            xref="paper", yref="paper", x=0.5, y=-0.12,
            showarrow=False, font=dict(size=10, color="#888"),
        )
        st.plotly_chart(figsoil, use_container_width=True)
    else:
        st.caption("Soiling data unavailable.")

# ── Row 6: TOU + Weather table ────────────────────────────────────────────────

col_tou, col_wx = st.columns([1, 1])

with col_tou:
    st.markdown('<div class="section-header">Net Metering & TOU Savings</div>',
                unsafe_allow_html=True)

    # Net metering breakdown
    flat_sav = daily_kwh * elec_rate
    nm_sav   = daily_sav
    nm_delta = nm_sav - flat_sav

    figtou = go.Figure()
    figtou.add_trace(go.Bar(
        x=df["label"], y=df["self_consumed"] * elec_rate,
        name="Self-consumed savings",
        marker_color="#4ade80",
        hovertemplate="%{x}: $%{y:.3f}<extra>Self-consumed</extra>",
    ))
    figtou.add_trace(go.Bar(
        x=df["label"], y=df["exported"] * net_meter_rate,
        name=f"Export credit ({net_meter_pct}%)",
        marker_color="#60a5fa",
        hovertemplate="%{x}: $%{y:.3f}<extra>Export credit</extra>",
    ))

    # TOU overlay if available and US
    tou_data = fetch_tou_schedule(lat, lon) if (country == "US" and OPENEI_API_KEY) else None
    if tou_data:
        tou_rates = tou_data["rates"]
        tou_sav_h = [df.loc[i, "self_consumed"] * tou_rates[h] for i, h in enumerate(hours)]
        figtou.add_trace(go.Scatter(
            x=df["label"], y=tou_sav_h,
            name=f"TOU savings ({tou_data['name'][:20]})",
            line=dict(color="#f97316", width=2),
            hovertemplate="%{x}: $%{y:.3f}<extra>TOU</extra>",
        ))

    figtou.update_layout(
        height=280, barmode="stack",
        margin=dict(t=10,b=10,l=0,r=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        legend=dict(orientation="h", y=1.12),
        xaxis=dict(gridcolor="#333"),
        yaxis=dict(title="Savings ($/hr)", gridcolor="#333"),
    )
    st.plotly_chart(figtou, use_container_width=True)
    col_a, col_b = st.columns(2)
    col_a.metric("Flat rate daily savings", f"${flat_sav:.2f}")
    col_b.metric("With net metering", f"${nm_sav:.2f}",
                 delta=f"{nm_delta:+.2f}" if abs(nm_delta) > 0.01 else None)
    if tou_data:
        tou_daily = sum(tou_sav_h)
        st.metric(f"TOU daily savings ({tou_data['name'][:25]})", f"${tou_daily:.2f}")

with col_wx:
    st.markdown('<div class="section-header">Hourly Weather (Open-Meteo)</div>',
                unsafe_allow_html=True)
    if forecast:
        wdf = pd.DataFrame([
            {"Hour": f"{h:02d}:00",
             "DNI (W/m²)": round(v["dni"], 0),
             "DHI (W/m²)": round(v["dhi"], 0),
             "GHI (W/m²)": round(v["ghi"], 0),
             "Cloud (%)": v["cloud"],
             "Temp (°C)": round(v["temp"], 1),
             "Wind (m/s)": round(v["wind"], 1)}
            for h, v in sorted(forecast.items())
        ])
        st.dataframe(wdf, hide_index=True, use_container_width=True, height=260)
    else:
        st.caption("No live forecast — using defaults.")

# ── Row 7: CO₂ + Site comparison + Export ─────────────────────────────────────

col_env, col_sites, col_dl = st.columns([1, 2, 1])

with col_env:
    st.markdown('<div class="section-header">Environmental Impact</div>',
                unsafe_allow_html=True)
    st.markdown(
        f'<div class="card">'
        f'<div class="card-title">CO₂ avoided / year</div>'
        f'<div class="card-value">{co2_kg:.0f} kg</div>'
        f'<div class="card-sub">≈ {trees:.0f} trees planted</div>'
        f'<div class="card-sub">≈ {cars:.2f} cars off road</div>'
        f'<div class="card-sub">Grid factor: {co2_factor} kg/kWh ({country})</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

with col_sites:
    st.markdown('<div class="section-header">Site Comparison</div>',
                unsafe_allow_html=True)
    sites_input = [s.strip() for s in compare_sites_raw.strip().splitlines() if s.strip()]
    if sites_input:
        site_rows = []
        for s in sites_input[:6]:  # cap at 6
            slat, slon, sname, scountry = search_location(s)
            if slat:
                spvgis = fetch_pvgis_monthly(slat, slon, capacity_kw, tilt)
                s_annual = sum(spvgis) if spvgis else None
                site_rows.append({
                    "Site": sname,
                    "Country": scountry,
                    "Annual kWh": f"{s_annual:,.0f}" if s_annual else "—",
                    "CO₂ offset (kg)": f"{s_annual * CO2_INTENSITY.get(scountry, 0.386):,.0f}" if s_annual else "—",
                })
        if site_rows:
            st.dataframe(pd.DataFrame(site_rows), hide_index=True, use_container_width=True)
    else:
        st.caption("Enter addresses in the 'Site Comparison' sidebar expander to compare locations.")

with col_dl:
    st.markdown('<div class="section-header">Export</div>', unsafe_allow_html=True)

    lines = [
        f"Solar Estimate — {loc_name}, {country} — {sel_date}",
        f"Panels: {n_panels} × {panel_area} m² @ {panel_eff*100:.0f}%",
        f"Tilt: {tilt}°  |  Azimuth: {azimuth}°",
        f"Bifacial: {'Yes' if bifacial_on else 'No'}  |  Degradation: {degradation}%/yr",
        f"Rate: ${elec_rate:.3f}/kWh  |  Net metering: {net_meter_pct}%",
        f"Gross cost: ${gross_system_cost:,}  |  Net cost after incentives: ${net_system_cost:,.0f}",
        f"Federal ITC: {federal_itc_pct}% (${federal_itc_value:,.0f})  |  State rebate: ${state_rebate:,.0f}",
        f"Total losses: {total_loss:.1f}%",
        "",
        f"Daily output:         {daily_kwh:.2f} kWh",
        f"Self-consumed:        {self_consumed_kwh:.2f} kWh ({self_consump_pct:.0f}%)",
        f"Exported:             {exported_kwh:.2f} kWh",
        f"Daily savings:        ${daily_sav:.2f}",
        f"Annual savings:       ${annual_sav:,.0f}",
        f"Payback:              {payback_yr} yr" if payback_yr else "Payback:              >25 yr",
        f"CO₂ offset:           {co2_kg:.0f} kg/yr ({trees:.0f} trees)",
        f"CO₂ factor:           {co2_factor} kg/kWh ({country})",
        f"Today soiling:        {today_soiling*100:.1f}%",
    ]
    txt = "\n".join(lines)
    st.download_button(
        "Download summary (.txt)", txt,
        file_name=f"solar_{loc_name}_{sel_date}.txt",
        mime="text/plain", use_container_width=True,
    )
    export_df = df.rename(columns={
        "hour":"Hour","label":"Time","poa":"POA_W_m2","ghi":"GHI_W_m2",
        "dni":"DNI_W_m2","dhi":"DHI_W_m2","kw":"Power_kW","load_kw":"Load_kW",
        "self_consumed":"SelfConsumed_kW","exported":"Exported_kW",
        "grid_import":"GridImport_kW","cloud":"Cloud_pct","temp":"Temp_C",
        "soc":"BattSOC_kWh",
    })
    st.download_button(
        "Download hourly data (.csv)", export_df.to_csv(index=False),
        file_name=f"solar_hourly_{loc_name}_{sel_date}.csv",
        mime="text/csv", use_container_width=True,
    )

# ── Row 8: Degradation + Financing + Sensitivity + String Sizing ─────────────

st.markdown('<div class="section-header">Planning Tools</div>', unsafe_allow_html=True)

col_deg, col_fin = st.columns(2)

with col_deg:
    fig_deg = go.Figure()
    fig_deg.add_trace(go.Scatter(
        x=degradation_years,
        y=annual_energy_curve,
        name="Annual energy",
        fill="tozeroy",
        fillcolor="rgba(96,165,250,0.12)",
        line=dict(color="#60a5fa", width=2),
        hovertemplate="Year %{x}: %{y:,.0f} kWh<extra></extra>",
    ))
    fig_deg.update_layout(
        height=270,
        title="Production Degradation Curve",
        margin=dict(t=30, b=10, l=0, r=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        xaxis=dict(title="Year", gridcolor="#333"),
        yaxis=dict(title="kWh/year", gridcolor="#333"),
        showlegend=False,
    )
    st.plotly_chart(fig_deg, use_container_width=True)

with col_fin:
    fig_fin = go.Figure()
    fig_fin.add_trace(go.Scatter(
        x=list(range(26)), y=fin["cash"]["net_vals"],
        name="Cash", line=dict(color="#4ade80", width=2),
    ))
    fig_fin.add_trace(go.Scatter(
        x=list(range(26)), y=fin["loan"]["net_vals"],
        name="Loan", line=dict(color="#facc15", width=2),
    ))
    fig_fin.add_trace(go.Scatter(
        x=list(range(26)), y=fin["lease"]["net_vals"],
        name="Lease/PPA", line=dict(color="#f97316", width=2),
    ))
    fig_fin.add_hline(y=0, line_color="#666", line_dash="dash")
    fig_fin.update_layout(
        height=270,
        title="Financing Comparison (25-year net value)",
        margin=dict(t=30, b=10, l=0, r=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#ccc"),
        xaxis=dict(title="Year", gridcolor="#333"),
        yaxis=dict(title="Net value ($)", gridcolor="#333"),
        legend=dict(orientation="h", y=1.12),
    )
    st.plotly_chart(fig_fin, use_container_width=True)

    fin_df = pd.DataFrame([
        {
            "Mode": "Cash",
            "Upfront ($)": round(fin["cash"]["upfront"], 0),
            "Monthly ($)": round(fin["cash"]["monthly_payment"], 2),
            "Payback (yr)": fin["cash"]["payback_yr"] if fin["cash"]["payback_yr"] is not None else ">25",
            "25-yr net ($)": round(fin["cash"]["profit_25"], 0),
        },
        {
            "Mode": "Loan",
            "Upfront ($)": round(fin["loan"]["upfront"], 0),
            "Monthly ($)": round(fin["loan"]["monthly_payment"], 2),
            "Payback (yr)": fin["loan"]["payback_yr"] if fin["loan"]["payback_yr"] is not None else ">25",
            "25-yr net ($)": round(fin["loan"]["profit_25"], 0),
        },
        {
            "Mode": "Lease/PPA",
            "Upfront ($)": round(fin["lease"]["upfront"], 0),
            "Monthly ($)": round(fin["lease"]["monthly_payment"], 2),
            "Payback (yr)": fin["lease"]["payback_yr"],
            "25-yr net ($)": round(fin["lease"]["profit_25"], 0),
        },
    ])
    st.dataframe(fin_df, hide_index=True, use_container_width=True, height=150)

if show_sensitivity:
    col_sens, col_str = st.columns(2)
else:
    col_str = st.container()

if show_sensitivity:
    with col_sens:
        sens_order = sorted(sensitivity_rows, key=lambda x: max(abs(x["low_delta"]), abs(x["high_delta"])))
        labels = [s["parameter"] for s in sens_order]
        lows = [s["low_delta"] for s in sens_order]
        highs = [s["high_delta"] for s in sens_order]

        fig_sens = go.Figure()
        fig_sens.add_trace(go.Bar(
            y=labels,
            x=lows,
            orientation="h",
            name="-20%",
            marker_color="#60a5fa",
            hovertemplate="%{y}: $%{x:,.0f}<extra>-20%</extra>",
        ))
        fig_sens.add_trace(go.Bar(
            y=labels,
            x=highs,
            orientation="h",
            name="+20%",
            marker_color="#f97316",
            hovertemplate="%{y}: $%{x:,.0f}<extra>+20%</extra>",
        ))
        fig_sens.add_vline(x=0, line_color="#666", line_dash="dash")
        fig_sens.update_layout(
            height=300,
            title="Sensitivity (impact on 25-year net value)",
            barmode="overlay",
            margin=dict(t=35, b=10, l=0, r=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc"),
            xaxis=dict(title="Change in net value ($)", gridcolor="#333"),
            yaxis=dict(gridcolor="#333"),
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig_sens, use_container_width=True)

with col_str:
    if show_string_wizard:
        st.markdown('<div class="section-header">String and Inverter Sizing Wizard</div>', unsafe_allow_html=True)
        if string_result["max_valid"] < string_result["min_valid"]:
            st.error(
                "No valid string length with the current voltage constraints. "
                "Check panel Voc/Vmp or inverter MPPT limits."
            )
        else:
            st.success(
                f"Valid modules per string: {string_result['min_valid']} to {string_result['max_valid']} "
                f"(cold Voc {string_result['voc_cold']:.1f} V/module)"
            )
            csa, csb, csc = st.columns(3)
            csa.metric("Cold Voc/module", f"{string_result['voc_cold']:.1f} V")
            csb.metric("Max total modules", f"{string_result['max_total_modules']}")
            csc.metric("DC:AC ratio", f"{dc_ac_ratio:.2f}")

            if dc_ac_ratio < 1.0:
                st.warning("DC:AC ratio is low. Inverter may be underutilized.")
            elif dc_ac_ratio > 1.5:
                st.warning("DC:AC ratio is high. Check clipping risk.")
            else:
                st.info("DC:AC ratio is in a typical design range.")
