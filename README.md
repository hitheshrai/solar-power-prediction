# Solar Power Dashboard

A Streamlit dashboard that estimates rooftop solar production, savings, ROI, and environmental impact using live weather and industry reference APIs.

## Overview

This project combines:

- Live weather and irradiance data
- Solar transposition and temperature derating physics
- Net metering + financing scenarios
- ROI and uncertainty analysis
- Exportable summary and hourly data

The app is intended for homeowners, students, and practitioners who want transparent assumptions instead of black-box annual estimates.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://hitheshrai-solar-power-prediction.streamlit.app)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Features

Enter a location and system assumptions. The dashboard computes:

| Question | Answer |
|---|---|
| How much will my panels produce? | Hourly output from pvlib POA irradiance + weather |
| How much money will I save? | Daily + annual savings with configurable net metering |
| When do I break even? | Payback year on a 25-year ROI curve |
| How many panels do I need? | Sized to 100% offset your monthly bill |
| What's my CO₂ impact? | kg/yr, tree-equivalents, cars off the road |

---

## Main modules in the UI

- Location + weather lookup
- System design (tilt, azimuth, bifacial, losses)
- Financials (cash/loan/lease, incentives, net metering)
- Battery storage simulation
- Monte Carlo uncertainty bands
- String and inverter sizing wizard
- PVGIS and PVWatts cross-check views

---

## Local setup

### Option A (recommended, Windows PowerShell)

```powershell
git clone https://github.com/hitheshrai/solar-power-prediction.git
cd solar-power-prediction
python -m venv Sol-power
.\Sol-power\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Option B (macOS/Linux)

```bash
git clone https://github.com/hitheshrai/solar-power-prediction.git
cd solar-power-prediction
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy the secrets template and fill in your keys:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` with your API keys.

Run:

```bash
python -m streamlit run app.py
```

## Run tests

```bash
python -m pytest tests/test_functions.py -v
```

---

## Deploy to Streamlit Community Cloud (free)

1. Push this repo to GitHub (it's already there)
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
3. Click **New app** → select this repo → `app.py`
4. Open **Advanced settings → Secrets** and paste:

```toml
OPENWEATHER_API_KEY = "your_key"
NREL_API_KEY        = "your_key"
TIMEZONE_API_KEY    = "your_key"
```

5. Click **Deploy** — live in ~60 seconds at `yourname-solar-power-prediction.streamlit.app`

---

## API keys

The app can run with only geocoding configured, but some features degrade without optional keys.

| Key | Where to get it | Required? |
|---|---|---|
| `OPENWEATHER_API_KEY` | [openweathermap.org/api](https://openweathermap.org/api) | Yes (location geocoding) |
| `NREL_API_KEY` | [developer.nrel.gov](https://developer.nrel.gov/signup/) | No (PVWatts + utility rates) |
| `TIMEZONE_API_KEY` | [timezonedb.com/api](https://timezonedb.com/api) | No (timezone fallback) |
| `OPENEI_API_KEY` | [openei.org/services](https://openei.org/services/) | No (TOU rates) |
| `CESIUM_ION_TOKEN` | [cesium.com/ion](https://cesium.com/ion/) | No (3D globe) |

---

## Data and modeling notes

- Weather forecast: Open-Meteo hourly irradiance and weather fields
- Location search: OpenWeather geocoding
- POA irradiance: pvlib `get_total_irradiance` (Perez model)
- Soiling: precipitation-driven Kimber-style accumulation/reset
- Power model: panel efficiency + temperature derating + inverter efficiency + user losses
- Annual yield baseline: PVGIS monthly TMY (fallback to daily x 365)
- Optional benchmark: NREL PVWatts v8
- Environmental factors: country-level grid intensity map with fallback

---

## Tech stack

- [Streamlit](https://streamlit.io) — dashboard framework
- [Plotly](https://plotly.com/python/) — interactive charts
- [Folium](https://python-visualization.github.io/folium/) — map
- [Pysolar](https://pysolar.readthedocs.io/) — sun path / azimuth-altitude
- [pvlib](https://pvlib-python.readthedocs.io/) — irradiance transposition and cell temperature
- [Open-Meteo](https://open-meteo.com/en/docs) — hourly forecast and precipitation history
- [OpenWeather API](https://openweathermap.org/api) — geocoding
- [NREL APIs](https://developer.nrel.gov/docs/) — PVWatts + utility rates
- [PVGIS](https://joint-research-centre.ec.europa.eu/pvgis-photovoltaic-geographical-information-system_en) — TMY monthly reference

---

## Contributing

Issues and pull requests are welcome.

## Author

[Hithesh Rai](https://hitheshrai.github.io/Hithesh/) · [LinkedIn](https://www.linkedin.com/in/hithesh-rai-p/)

## License

MIT
