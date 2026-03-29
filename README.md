# Solar Power Dashboard

A solar energy estimator that tells you exactly what a rooftop system will produce, save, and cost — for any location on Earth.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://hitheshrai-solar-power-prediction.streamlit.app)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What it does

Enter a location and your electricity bill. The dashboard computes:

| Question | Answer |
|---|---|
| How much will my panels produce? | Hourly kWh output with live cloud/temp forecast |
| How much money will I save? | Daily + annual savings at your local electricity rate |
| When do I break even? | Payback year on a 25-year ROI curve |
| How many panels do I need? | Sized to 100% offset your monthly bill |
| What's my CO₂ impact? | kg/yr, tree-equivalents, cars off the road |

---

## Dashboard

```
┌─ Sidebar ─────────────────────────────────────────────────────────────┐
│  Location · Date · Panels · Efficiency · Tilt · Cost · Rate           │
└───────────────────────────────────────────────────────────────────────┘

  Daily kWh │ Daily $ │ Annual $ │ Payback │ CO₂ kg │ Panels needed

┌─ Hourly power output ──────────────────┐  ┌─ Map ─────────────────────┐
│  Power bars + GHI line + cloud shading │  │  Dark map, location pin   │
└────────────────────────────────────────┘  └───────────────────────────┘

┌─ 25-Year ROI ──────────────────────────┐  ┌─ System Sizing ───────────┐
│  Net value curve · break-even marker   │  │  Panels vs bill offset %  │
└────────────────────────────────────────┘  └───────────────────────────┘

┌─ Live weather table ──┐  ┌─ CO₂ card ──┐  ┌─ Download (.txt / .csv) ─┐
└───────────────────────┘  └─────────────┘  └──────────────────────────┘
```

---

## Local setup

```bash
git clone https://github.com/hitheshrai/solar-power-prediction.git
cd solar-power-prediction
pip install -r requirements.txt
```

Copy the secrets template and fill in your keys:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml with your API keys
```

Run:

```bash
streamlit run app.py
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

All three are free:

| Key | Where to get it | Required? |
|---|---|---|
| `OPENWEATHER_API_KEY` | [openweathermap.org/api](https://openweathermap.org/api) | Yes |
| `NREL_API_KEY` | [developer.nrel.gov](https://developer.nrel.gov/signup/) | No (US rate lookup) |
| `TIMEZONE_API_KEY` | [timezonedb.com/api](https://timezonedb.com/api) | No (accurate local time) |

---

## Physics notes

- **GHI model**: clear-sky baseline `900·cos(zenith) + 100 W/m²`, attenuated by cloud transmittance `1 − 0.75·cloud^3.4`, panel temperature derating `0.4%/°C above 25°C`, and humidity haze factor
- **Tilt factor**: `cos(tilt − |latitude|)`, clamped to [0.70, 1.15]
- **CO₂ factor**: 0.386 kg/kWh (US EPA average)
- **Panel degradation**: compound annual reduction applied to 25-year savings curve

---

## Tech stack

- [Streamlit](https://streamlit.io) — dashboard framework
- [Plotly](https://plotly.com/python/) — interactive charts
- [Folium](https://python-visualization.github.io/folium/) — map
- [Pysolar](https://pysolar.readthedocs.io/) — solar altitude calculation
- [OpenWeather API](https://openweathermap.org/api) — geocoding + hourly forecast
- [NREL Utility Rates API](https://developer.nrel.gov/docs/electricity/utility-rates-v3/) — US electricity pricing

---

## Contributing

Issues and pull requests are welcome.

## Author

[Hithesh Rai](https://hitheshrai.github.io/Hithesh/) · [LinkedIn](https://www.linkedin.com/in/hithesh-rai-p/)

## License

MIT
