# LESSON.md

## What This Project Teaches

A hands-on walkthrough of building a real-time solar energy estimator — from physics formulas to a deployed web dashboard.

---

## Lesson 1: Solar Irradiance Physics

**Concept**: How much sunlight hits a surface depends on the sun's angle in the sky.

**Key formula** (clear-sky Global Horizontal Irradiance):
```
GHI = 900 · sin(solar_altitude_degrees) + 100   [W/m²]
```

- `sin(altitude)` approaches 1 at solar noon (sun directly overhead)
- The `+100` term accounts for diffuse sky radiation even at low angles
- GHI is zero when the sun is below the horizon

**Tool used**: `pysolar.solar.get_altitude(lat, lon, datetime)` returns altitude in degrees.

---

## Lesson 2: Real-World Adjustments to Irradiance

Clear-sky GHI is an ideal. Real conditions reduce it:

```python
cloud_factor    = 1 - 0.75 * (cloud_cover / 100) ** 3.4
temp_factor     = 1 - 0.004 * max(0, temperature_c - 25)
humidity_factor = 1 - 0.05 * (humidity / 100)

effective_GHI = GHI * cloud_factor * temp_factor * humidity_factor
```

**Insight**: Cloud cover has the largest impact. The `^3.4` exponent means partial cloud cover has a disproportionately small effect — it only becomes severe at high coverage.

---

## Lesson 3: Panel Tilt Optimization

Panels tilted toward the equator capture more annual energy. The tilt factor approximates this:

```python
tilt_factor = cos(radians(tilt_angle - abs(latitude)))
tilt_factor = max(0.70, min(1.15, tilt_factor))  # clamp to realistic range
```

- Optimal tilt ≈ local latitude (e.g., 35° tilt at 35°N)
- Flat panels (0°) still work but lose ~10–15% annual yield
- The 1.15 upper bound prevents overcounting at very favored angles

---

## Lesson 4: System Power Output

Converting irradiance to actual electricity:

```python
panel_power_kW = (effective_GHI * tilt_factor * panel_area_m2 * efficiency) / 1000
system_power_kW = panel_power_kW * num_panels
```

- `efficiency` is panel efficiency (e.g., 0.20 = 20%)
- Divide by 1000 to convert W → kW
- Sum hourly values to get daily kWh

---

## Lesson 5: Financial Modeling

**Daily savings**:
```python
daily_savings = daily_kwh * electricity_rate_per_kwh
annual_savings = daily_savings * 365
```

**25-year ROI with panel degradation**:
```python
cumulative_savings = 0
for year in range(1, 26):
    degraded_output = annual_kwh * (1 - degradation_rate) ** year
    cumulative_savings += degraded_output * electricity_rate
```

**Payback year**: First year where `cumulative_savings >= system_cost`

**System cost**: `num_panels * cost_per_panel`

---

## Lesson 6: Environmental Impact

Converting energy to real-world equivalents makes data meaningful:

```python
co2_kg_avoided  = annual_kwh * 0.386          # US EPA grid average
trees_equivalent = co2_kg_avoided / 21        # avg tree absorbs 21 kg CO₂/yr
cars_equivalent  = co2_kg_avoided / 4600      # avg car emits 4,600 kg CO₂/yr
```

---

## Lesson 7: Working with External APIs

This project integrates three APIs. The pattern for each:

1. Check for API key (secrets or env var)
2. Make HTTP GET with `requests`
3. Parse JSON response
4. Cache with `@st.cache_data(ttl=seconds)`

```python
@st.cache_data(ttl=300)
def get_forecast(lat, lon, api_key):
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()
```

**Rate limiting**: Cache aggressively. Location data can be cached for 24h; forecasts for 5 minutes.

---

## Lesson 8: Building Interactive Dashboards with Streamlit

**Sidebar for inputs**:
```python
num_panels = st.sidebar.slider("Number of Panels", 1, 500, 20)
efficiency = st.sidebar.slider("Panel Efficiency (%)", 15, 24, 20) / 100
```

**KPI metrics**:
```python
col1, col2, col3 = st.columns(3)
col1.metric("Daily Output", f"{daily_kwh:.1f} kWh")
```

**Charts**: Use `plotly.graph_objects` for full control, `st.plotly_chart(fig, use_container_width=True)` to render.

**Maps**: Use `folium.Map()` + `streamlit_folium.st_folium()`.

---

## Lesson 9: Deployment

**Local**:
```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Add your API keys
streamlit run app.py
```

**Cloud (Streamlit Community — free tier)**:
1. Push code to GitHub (never commit `.env` or `secrets.toml`)
2. Connect repo at share.streamlit.io
3. Paste API keys in the app's Secrets panel (Settings → Secrets)
4. Deploy

**Secret management rule**: Only commit `*.example` files. Real secrets live in `.gitignore`d files locally, and in the platform's secret manager in production.

---

## Key Takeaways

| Topic | Lesson |
|-------|--------|
| Solar physics | Irradiance is a function of sun angle, clouds, temp, humidity |
| Panel design | Tilt toward equator by roughly your latitude |
| Financial modeling | Degradation and payback period are the key numbers |
| APIs | Cache responses; handle missing keys gracefully |
| Streamlit | Sidebar inputs + column layout + Plotly = a complete dashboard |
| Deployment | Separate code from secrets from day one |
