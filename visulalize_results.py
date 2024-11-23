import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import mean_absolute_error, mean_squared_error

# Load data and predictions
data = pd.read_csv("processed_weather_data.csv")
y_actual = data["power_output"][:50]
y_pred = data["power_output"][:50]  # Simulating predictions for visualization

# Plot actual vs predicted
plt.figure(figsize=(10, 6))
plt.plot(y_actual, label="Actual", marker="o")
plt.plot(y_pred, label="Predicted", marker="x")
plt.title("Actual vs. Predicted Solar Power Output")
plt.xlabel("Sample")
plt.ylabel("Power Output (W)")
plt.legend()
plt.grid()
plt.show()
