import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster
from datetime import datetime
import pytz
from pysolar.solar import get_altitude
import math
import matplotlib.pyplot as plt
import requests

# Predefined locations with latitude, longitude, and timezone
locations = {
    "Riyadh": {"lat": 24.7136, "lon": 46.6753, "timezone": "Asia/Riyadh"},
    "Phoenix": {"lat": 33.4484, "lon": -112.0740, "timezone": "America/Phoenix"},
    "London": {"lat": 51.5074, "lon": -0.1278, "timezone": "Europe/London"},
    "Berlin": {"lat": 52.5200, "lon": 13.4050, "timezone": "Europe/Berlin"},
    "Tokyo": {"lat": 35.6895, "lon": 139.6917, "timezone": "Asia/Tokyo"},
}

# Function to calculate zenith angle
def calculate_zenith_angle(lat, lon, time):
    altitude = get_altitude(lat, lon, time)
    zenith_angle = 90 - altitude
    return max(zenith_angle, 0)

# Function to calculate GHI
def calculate_ghi(lat, lon, time, cloud_cover, temperature=25, humidity=50, wind_speed=0):
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
def calculate_power_output(ghi, panel_area=1.6, efficiency=0.2):
    return ghi * panel_area * efficiency

# Function to fetch real-time weather data
def fetch_weather_data(lat, lon, api_key="2944aa74d63a7db9f72439884e6ee599"):
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
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching weather data: {e}")
        return 0, 25, 50, 0  # Defaults if API fails

# Streamlit interface
st.title("🌞 Real-Time Solar Power Prediction")
st.markdown("Select a location, date, and time range to predict solar power output.")

# Create an enhanced Folium map
m = folium.Map(location=[20.0, 0.0], zoom_start=2, tiles="CartoDB Positron")  # Use a cleaner basemap
marker_cluster = MarkerCluster().add_to(m)

# Add clustered markers for predefined locations
for city, coords in locations.items():
    folium.Marker(
        [coords["lat"], coords["lon"]],
        popup=f"{city} (Lat: {coords['lat']}, Lon: {coords['lon']})",
        tooltip=f"Click for details: {city}",
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(marker_cluster)

# Display map and get selected location
selected_location = st_folium(m, width=700, height=500)

# Default values for location
if selected_location and selected_location["last_clicked"]:
    lat, lon = selected_location["last_clicked"]["lat"], selected_location["last_clicked"]["lng"]
    st.write(f"**Selected Location:** Latitude {lat}, Longitude {lon}")
    timezone = pytz.timezone("UTC")  # Default to UTC
else:
    st.write("Select a location from the map.")
    default_city = st.selectbox("Or choose from the dropdown:", list(locations.keys()))
    lat, lon = locations[default_city]["lat"], locations[default_city]["lon"]
    timezone = pytz.timezone(locations[default_city]["timezone"])

# Date selection
selected_date = st.date_input("Select a date:", datetime.now().date())
selected_datetime = datetime.combine(selected_date, datetime.min.time())  # Combine date with default time

# Fetch real-time weather data
cloud_cover, temperature, humidity, wind_speed = fetch_weather_data(lat, lon)
st.write(f"**Real-Time Weather Data:**")
st.write(f"- Cloud Cover: {cloud_cover}%")
st.write(f"- Temperature: {temperature}°C")
st.write(f"- Humidity: {humidity}%")
st.write(f"- Wind Speed: {wind_speed} m/s")

# Time range selection
time_range = st.slider("Select a time range (hours):", 6, 18, (8, 16))

# Electricity cost input
electricity_cost = st.number_input("Electricity Cost ($/kWh):", min_value=0.0, value=0.12)

# Calculate GHI and Power Output for time range
hours = list(range(time_range[0], time_range[1] + 1))
ghi_values = []
power_outputs = []

for hour in hours:
    localized_time = timezone.localize(selected_datetime.replace(hour=hour, minute=0, second=0, microsecond=0))
    ghi = calculate_ghi(lat, lon, localized_time, cloud_cover, temperature, humidity, wind_speed)
    ghi_values.append(ghi)
    power_outputs.append(calculate_power_output(ghi))

# Total daily savings calculation
total_power_output = sum(power_outputs) / 1000  # Convert W to kWh
total_savings = total_power_output * electricity_cost

# Display interactive graph
st.subheader("Predicted Power Output Over Time")
plt.figure(figsize=(10, 5))
plt.plot(hours, power_outputs, marker="o", label="Predicted Power Output", color="orange")
plt.xlabel("Hour of the Day")
plt.ylabel("Power Output (W)")
plt.title(f"Solar Power Prediction for Latitude {lat:.2f}, Longitude {lon:.2f} on {selected_date}")
plt.legend()
st.pyplot(plt)

# Display midpoint results
mid_index = len(hours) // 2
st.write(f"**Midpoint Time:** {hours[mid_index]}:00")
st.write(f"**Estimated GHI:** {ghi_values[mid_index]:.2f} W/m²")
st.write(f"**Predicted Power Output:** {power_outputs[mid_index]:.2f} W")
st.write(f"**Total Savings for Selected Time Range:** ${total_savings:.2f}")

# Add carbon offset estimate
co2_offset = total_power_output * 0.85  # Average 0.85 kg CO2 offset per kWh of solar
st.write(f"**Estimated Carbon Offset:** {co2_offset:.2f} kg CO₂")
