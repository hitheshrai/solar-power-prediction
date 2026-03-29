# CLAUDE.md

## Project Overview

Solar Power Prediction is a **Streamlit web dashboard** that estimates rooftop solar energy production, financial ROI, and environmental impact using live weather data from external APIs. It has no local data files — all inputs come from user configuration and live API calls.

## Tech Stack

- **Framework**: Streamlit
- **Charts**: Plotly, Folium (maps)
- **Solar physics**: Pysolar (altitude/azimuth), pvlib (POA irradiance transposition)
- **Data**: Pandas, NumPy, SciPy
- **APIs**: Open-Meteo (free, no key), OpenWeather (geocoding), NREL PVWatts v8, PVGIS, TimezoneDB, OpenEI (TOU rates)
- **Config**: python-dotenv (local) / Streamlit secrets (cloud)

## Project Structure

```
app.py                    # Single-file Streamlit app (~1169 lines)
requirements.txt          # 11 core dependencies
tests/
  test_functions.py       # 61 unit tests for pure logic functions
.env.example              # API key template for local dev
.streamlit/
  secrets.toml.example    # Streamlit Cloud secrets template
```

## Running Locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Fill in API keys in secrets.toml
streamlit run app.py
```

## Running Tests

```bash
python -m pytest tests/test_functions.py -v
```

All 61 tests run against pure functions mirrored inline — no Streamlit import needed.

## API Keys

| Key | Source | Required |
|-----|--------|----------|
| `OPENWEATHER_API_KEY` | openweathermap.org | Yes (geocoding) |
| `NREL_API_KEY` | developer.nrel.gov | No (PVWatts v8 hourly output) |
| `TIMEZONE_API_KEY` | timezonedb.com | No (accurate local time) |
| `CESIUM_ION_TOKEN` | cesium.com | No (3-D globe, unused by default) |
| `OPENEI_API_KEY` | openei.org | No (TOU rate schedules) |

Keys are loaded via `python-dotenv` locally, or Streamlit secrets in production. Weather data comes from **Open-Meteo** (no key required).

## Core Physics

- **POA irradiance**: pvlib `get_total_irradiance()` with DNI/DHI from Open-Meteo, Hay-Davies transposition
- **System power**: `η_cell · A_panel · POA · (1 - temp_coeff·ΔT) · (1 - wind_derate)`
- **Soiling loss**: precipitation-driven daily accumulation, resets when rain ≥ 1 mm/day, capped at 25%
- **Bifacial gain**: `POA · albedo · bifaciality_factor · view_factor`
- **Tilt factor**: `cos(tilt_deg - |latitude|)`, clamped to `[0.70, 1.15]`
- **Panel degradation**: compound annual reduction (default 0.5%/yr)
- **CO₂ factor**: per-country lookup (20 countries); default 0.386 kg/kWh (US EPA)
- **Battery simulation**: SOC-tracked charge/discharge with efficiency and depth-of-discharge limits
- **Monte Carlo**: ±10% irradiance noise over 500 samples for uncertainty bands

## Key Constants

- `CO2_INTENSITY` — 20-country grid emission factors (kg CO₂/kWh)
- `LOAD_PROFILES` — three consumption archetypes: *Home all day*, *Away 9–5*, *EV night charging*
- `ALBEDO_OPTIONS` — six surface types: Concrete, Grass, White Gravel, Sand, Snow, Asphalt

## Deployment

Live at: https://hitheshrai-solar-power-prediction.streamlit.app

Deploy via Streamlit Community Cloud — push to GitHub, connect repo, add API keys in the Secrets panel.

## Development Notes

- All logic lives in `app.py` — no separate modules
- API responses are cached with `@st.cache_data` (TTLs: 300s–86400s)
- Weather source switched from OpenWeather forecast to **Open-Meteo** (free, hourly, no key)
- The virtual environment is in `Sol-power/` (excluded from git)
