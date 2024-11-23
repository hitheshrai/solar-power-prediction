import pandas as pd

# Load raw data
weather_df = pd.read_csv("weather_data.csv")

# Extract relevant features
weather_df = weather_df[["dt", "temp", "humidity", "clouds", "wind_speed"]]

# Estimate solar irradiance and power output
weather_df["solar_irradiance"] = 1000 * (1 - weather_df["clouds"] / 100)  # Simplified estimate
weather_df["power_output"] = (
    1.6 * weather_df["solar_irradiance"] * 0.2  # Panel area: 1.6m², Efficiency: 20%
)

# Save preprocessed data
weather_df.to_csv("processed_weather_data.csv", index=False)
print(weather_df.head())
