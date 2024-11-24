import streamlit as st
from streamlit_folium import st_folium
import folium
from datetime import datetime
import pytz
from pysolar.solar import get_altitude
import math
import plotly.express as px
import pandas as pd
import requests
from dataclasses import dataclass
import matplotlib.pyplot as plt
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
NREL_API_KEY = os.getenv("NREL_API_KEY")
TIMEZONE_API_KEY = os.getenv("TIMEZONE_API_KEY")
DEFAULT_ELECTRICITY_PRICE = 0.12  # Default price for non-US locations

# Standard Solar Panel Assumptions
DEFAULT_PANEL_AREA = 1.68  # m² (standard panel size)
DEFAULT_PANEL_EFFICIENCY = 0.22  # 22% efficiency

# Validate API keys
if not OPENWEATHER_API_KEY:
    st.error("OpenWeather API key is missing. Add it to the .env file.")
    st.stop()

if not NREL_API_KEY:
    st.warning("NREL API key is missing. US electricity pricing will default to $0.12/kWh.")

# Function to search for location using OpenWeather Geocoding API
def search_location(query, api_key=OPENWEATHER_API_KEY):
    url = f"http://api.openweathermap.org/geo/1.0/direct?q={query}&limit=1&appid={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if len(data) > 0:
            return data[0]["lat"], data[0]["lon"], data[0]["name"]
        else:
            st.warning("Location not found. Please try a different search.")
            return None, None, None
    except requests.exceptions.RequestException:
        st.error("Error searching for location. Please check your network or API key.")
        return None, None, None

# Function to fetch location name using OpenWeather reverse geocoding
def fetch_location_name(lat, lon, api_key=OPENWEATHER_API_KEY):
    url = f"http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={lon}&limit=1&appid={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data and "name" in data[0]:
            return data[0]["name"]
        return f"Lat: {lat}, Lon: {lon}"  # Fallback if no name is found
    except requests.exceptions.RequestException:
        return f"Lat: {lat}, Lon: {lon}"  # Fallback if API fails

# Function to fetch real-time weather data from OpenWeather
def fetch_weather_data(lat, lon, api_key=OPENWEATHER_API_KEY):
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        cloud_cover = data["clouds"]["all"]
        temperature = data["main"]["temp"]
        humidity = data["main"]["humidity"]
        wind_speed = data["wind"]["speed"]
        return cloud_cover, temperature, humidity, wind_speed
    except requests.exceptions.RequestException:
        st.warning("Error fetching weather data. Using default values.")
        return 50, 25, 50, 0  # Default values if API fails

# Function to fetch electricity prices from NREL (US only)
def fetch_electricity_price(lat, lon, api_key=NREL_API_KEY):
    url = f"https://developer.nrel.gov/api/utility_rates/v3.json?api_key={api_key}&lat={lat}&lon={lon}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        residential_rate = data["outputs"].get("residential")
        if residential_rate is None or not isinstance(residential_rate, (int, float)):
            return None  # Return None if no valid data
        return residential_rate
    except requests.exceptions.RequestException:
        return None  # Return None if API fails

# Function to fetch timezone information using TimeZoneDB API
def fetch_timezone(lat: float, lon: float) -> pytz.timezone:
    """Fetch timezone information using TimeZoneDB API."""
    url = f"http://api.timezonedb.com/v2.1/get-time-zone?key={TIMEZONE_API_KEY}&format=json&by=position&lat={lat}&lng={lon}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if "zoneName" in data:
            return pytz.timezone(data["zoneName"])
        else:
            st.warning("Timezone data not available. Defaulting to UTC.")
            return pytz.UTC
    except Exception as e:
        st.warning(f"Could not fetch timezone: {e}. Defaulting to UTC.")
        return pytz.UTC

# Function to calculate zenith angle
def calculate_zenith_angle(lat, lon, time):
    altitude = get_altitude(lat, lon, time)
    zenith_angle = 90 - altitude
    return max(zenith_angle, 0)

# Function to calculate GHI
def calculate_ghi(lat, lon, time, cloud_cover, temperature=25, humidity=50):
    zenith_angle = calculate_zenith_angle(lat, lon, time)
    dni = 1000 * (1 - cloud_cover / 100)  # Simplified DNI
    dhi = 100 * (cloud_cover / 100)       # Simplified DHI

    # Adjust DNI for atmospheric scattering due to humidity
    dni = dni * (1 - humidity / 100)

    # Temperature correction factor (efficiency loss at high temperatures)
    temperature_factor = 1 - 0.004 * (temperature - 25)

    # Combine DNI and DHI for GHI
    ghi = (dni * math.cos(math.radians(zenith_angle)) + dhi) * temperature_factor
    return max(ghi, 0)

# Function to calculate power output
def calculate_power_output(ghi, panel_area, efficiency):
    return ghi * panel_area * efficiency

# Streamlit interface
st.title("☀️ Solar Power Prediction with Advanced Features")
st.markdown("Select a location, date, and time range to predict solar power output and analyze energy savings.")

# Location search box
search_query = st.text_input("Search for a location:")
if search_query:
    lat, lon, location_name = search_location(search_query)
else:
    lat, lon, location_name = None, None, None

# Show map if location search is successful
if lat and lon:
    st.write(f"**Selected Location:** {location_name} (Lat: {lat}, Lon: {lon})")
    m = folium.Map(location=[lat, lon], zoom_start=10)
    folium.Marker([lat, lon], popup=location_name).add_to(m)
    st_folium(m, width=700, height=500)
else:
    st.warning("Please search for a valid location.")

# Fetch weather data
if lat and lon:
    cloud_cover, temperature, humidity, wind_speed = fetch_weather_data(lat, lon)

    # Fetch electricity price or allow user input for non-US locations
    electricity_price = fetch_electricity_price(lat, lon)
    if electricity_price is None:
        st.warning("Electricity price data unavailable for this location.")
        monthly_electricity_cost = st.number_input("Enter your monthly electricity cost ($):", min_value=0.0, value=100.0, step=1.0)
        electricity_price = (monthly_electricity_cost / 30) / 30  # Approximate price per kWh
    else:
        st.write(f"**Electricity Price:** ${electricity_price:.2f}/kWh")

    # Time range selection
    time_range = st.slider("Time Range (hours):", 6, 18, (8, 16))
    hours = list(range(time_range[0], time_range[1] + 1))

    # Advanced options in expander
    with st.expander("Advanced Configuration"):
        panel_area = st.number_input("Solar Panel Area (m²):", min_value=1.0, value=DEFAULT_PANEL_AREA, step=0.1)
        panel_efficiency = st.slider("Solar Panel Efficiency (%):", min_value=10, max_value=30, value=int(DEFAULT_PANEL_EFFICIENCY * 100)) / 100

    # Calculate GHI and power output
    ghi_values = []
    power_outputs = []

    for hour in hours:
        time = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
        time = pytz.UTC.localize(time)  # Make timezone-aware

        ghi = calculate_ghi(lat, lon, time, cloud_cover, temperature, humidity)
        power_output = calculate_power_output(ghi, panel_area, panel_efficiency)
        power_outputs.append(power_output)

    # Calculate total power output and savings
    total_power_output = sum(power_outputs) / 1000  # Convert W to kWh
    daily_savings = total_power_output * electricity_price
    annual_savings = daily_savings * 365

    # Display results
    st.write(f"**Total Power Output (Daily):** {total_power_output:.2f} kWh")
    st.write(f"**Estimated Daily Savings:** ${daily_savings:.2f}")
    st.write(f"**Estimated Annual Savings:** ${annual_savings:.2f}")

    # Plot power output over time
    plt.figure(figsize=(10, 5))
    plt.plot(hours, power_outputs, marker="o", label="Power Output (W)", color="orange")
    plt.xlabel("Hour of the Day")
    plt.ylabel("Power Output (W)")
    plt.title("Hourly Power Output")
    plt.legend()
    st.pyplot(plt)
