# AGENT.md

## Purpose

This document describes the agentic context for the Solar Power Prediction project — what an AI agent needs to know to work effectively in this codebase.

## Codebase at a Glance

Single-file Streamlit app (`app.py`, ~1169 lines). No separate modules, no database, no ML model files. All solar calculations are physics-based formulas; all weather data comes from live API calls. Unit tests live in `tests/test_functions.py` (61 tests, all passing).

## Key Sections in app.py

| Approx. Lines | Section |
|---------------|---------|
| 1–20 | Imports |
| 22–60 | Secrets helper `_secret()`, constants (`CO2_INTENSITY`, `LOAD_PROFILES`, `ALBEDO_OPTIONS`) |
| 61–113 | Page config, CSS styling |
| 114–328 | API helpers: geocoding, Open-Meteo weather & precip, TimezoneDB, NREL, PVWatts v8, PVGIS, TOU |
| 329–452 | Physics: POA irradiance (pvlib), system power, soiling, battery sim, load profile |
| 453–533 | Sidebar controls |
| 534–735 | Main computation: rate lookup, weather fetch, hourly records, Monte Carlo, soiling, financials |
| 736–1169 | UI — KPI row, hourly chart, map, ROI, sizing, PVGIS seasonal, tilt comparison, sun path, soiling chart, TOU, weather table, CO₂, site comparison, CSV export |

## Data Flow

```
User input (location, panel config, battery, load profile)
  → OpenWeather geocoding (lat/lon + country code)
  → TimezoneDB (local timezone, optional)
  → Open-Meteo forecast (hourly DNI/DHI/temp/wind/precip, free, no key)
  → NREL PVWatts v8 (simulated hourly AC output, optional)
  → PVGIS (monthly yield + tilt optimization, optional)
  → OpenEI TOU schedule (time-of-use rates, optional)
  → pvlib POA irradiance (Hay-Davies transposition)
  → calc_system_power_kw() per hour
  → calc_soiling_losses() from historical precip
  → simulate_battery() SOC tracking
  → Monte Carlo ±10% uncertainty bands (500 samples)
  → Daily/annual energy → net metering savings → 25-yr ROI
  → Streamlit charts + CSV export
```

## API Helper Functions

All external calls use `requests`. Caching via `@st.cache_data`.

| Function | API | Key Required |
|----------|-----|--------------|
| `search_location(query)` | OpenWeather geocoding | Yes |
| `fetch_open_meteo(lat, lon)` | Open-Meteo forecast | No |
| `fetch_open_meteo_historical_precip(lat, lon)` | Open-Meteo archive | No |
| `fetch_timezone(lat, lon)` | TimezoneDB | Optional |
| `fetch_nrel_rate(lat, lon)` | NREL utility rates | Optional |
| `fetch_pvwatts_v8(lat, lon, capacity_kw, tilt, losses_pct)` | NREL PVWatts v8 | Optional |
| `fetch_pvgis_monthly(lat, lon, capacity_kw, tilt)` | PVGIS (EU) | No |
| `fetch_pvgis_tilt_comparison(lat, lon, capacity_kw)` | PVGIS | No |
| `fetch_pvgis_horizon(lat, lon)` | PVGIS | No |
| `fetch_tou_schedule(lat, lon)` | OpenEI | Optional |

## Physics / Calculation Functions

| Function | Purpose |
|----------|---------|
| `calc_poa_irradiance(...)` | pvlib Hay-Davies POA transposition from DNI/DHI |
| `calc_system_power_kw(...)` | Panel output with temp & wind derating |
| `calc_soiling_losses(precip_daily)` | Monthly soiling fractions from precipitation |
| `simulate_battery(records, ...)` | Hour-by-hour SOC, charge/discharge, grid import/export |
| `build_load_profile(archetype, scale)` | Normalised 16-value hourly consumption shape |
| `tilt_factor(tilt_deg, lat)` | Cosine tilt correction, clamped [0.70, 1.15] |
| `payback_curve(annual_sav, cost, degradation)` | 25-year cumulative net value list |

## Environment / Secrets

The app checks `st.secrets` first (Streamlit Cloud), then falls back to `os.environ` / `.env` file (local dev) via the `_secret(key)` helper. No secrets should ever be hardcoded.

```python
# Pattern used throughout app.py
value = _secret("OPENWEATHER_API_KEY")
```

## Tests

```bash
python -m pytest tests/test_functions.py -v   # 61 tests, ~0.3 s
```

Tests mirror pure functions inline — no Streamlit runtime needed. Covers: `tilt_factor`, `payback_curve`, CO₂ intensity, soiling model, battery simulation, load profiles, net metering, bifacial gain, system sizing, environmental impact.

## Common Tasks

**Add a new chart**: Use `st.plotly_chart()` — follow the existing Plotly figure pattern in the UI section (lines ~736–1169).

**Change a physics constant**: Search for the value or the formula comment under `# ── Physics` (lines ~329–452).

**Add a new sidebar input**: Add `st.sidebar.slider()` or `st.sidebar.number_input()` in the sidebar block (lines ~453–533), then thread the value into the relevant calculation.

**Add a new API**: Create a `@st.cache_data`-decorated helper following the pattern of `fetch_open_meteo()`, use `_secret()` for any key, and add the key to `.env.example` and `.streamlit/secrets.toml.example`.

**Add a new test**: Mirror the pure function in `tests/test_functions.py` and add a class following existing patterns.

## Constraints

- Keep all logic in `app.py` unless a refactor is explicitly requested
- Do not commit `.env` or `secrets.toml` — only commit `*.example` versions
- The `Sol-power/` venv directory must stay out of git
- Avoid adding heavy ML dependencies; the physics model is intentional
- Weather data is now sourced from Open-Meteo (free) — do not reintroduce OpenWeather for forecast data
