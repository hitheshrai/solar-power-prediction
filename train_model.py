import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Load processed data
data = pd.read_csv("processed_weather_data.csv")

# Features and target
X = data[["temp", "humidity", "clouds", "wind_speed", "solar_irradiance"]]
y = data["power_output"]

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train model
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Evaluate model
y_pred = model.predict(X_test)
print("MAE:", mean_absolute_error(y_test, y_pred))
print("RMSE:", mean_squared_error(y_test, y_pred, squared=False))

# Save model for dashboard use
import joblib
joblib.dump(model, "solar_power_model.pkl")
