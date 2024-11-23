import requests
import pandas as pd

# API setup
API_KEY = "3f61de899aecbd2dfa4595afed969f80"  # Replace with your OpenWeatherMap API Key
BASE_URL = "http://api.openweathermap.org/data/2.5/onecall"
LAT, LON = 35.6895, 139.6917  # Latitude and Longitude for Tokyo (example)

def fetch_weather_data(lat, lon, api_key):
    params = {
        "lat": lat,
        "lon": lon,
        "exclude": "minutely,daily,alerts",
        "appid": api_key,
        "units": "metric",
    }
    response = requests.get(BASE_URL, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to fetch data:", response.status_code, response.text)
        return None

# Fetch data
data = fetch_weather_data(LAT, LON, API_KEY)

# Process hourly data
if data:
    hourly_data = data["hourly"]
    df = pd.DataFrame(hourly_data)
    df["dt"] = pd.to_datetime(df["dt"], unit="s")
    print(df.head())

    # Save to CSV for further analysis
    df.to_csv("weather_data.csv", index=False)
