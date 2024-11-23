import streamlit as st
import joblib

# Load the trained model
model = joblib.load("solar_power_model.pkl")

# Dashboard interface
st.title("Solar Power Prediction Dashboard")

# Input sliders
temp = st.slider("Temperature (°C)", min_value=-10, max_value=40, value=25)
humidity = st.slider("Humidity (%)", min_value=0, max_value=100, value=50)
clouds = st.slider("Cloud Cover (%)", min_value=0, max_value=100, value=50)
wind_speed = st.slider("Wind Speed (m/s)", min_value=0, max_value=15, value=5)

# Calculate solar irradiance
solar_irradiance = 1000 * (1 - clouds / 100)

# Predict power output
input_data = [[temp, humidity, clouds, wind_speed, solar_irradiance]]
predicted_power = model.predict(input_data)[0]

# Display results
st.write(f"Predicted Solar Power Output: {predicted_power:.2f} W")
