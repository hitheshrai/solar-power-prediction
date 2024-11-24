# Solar Power Prediction 🌞

This project predicts solar power output based on geolocation, weather data, and solar panel configurations. It allows users to estimate daily and annual savings from solar power production using various customizable parameters, including panel size, efficiency, and tilt. It also provides economic analysis, such as ROI and installation cost estimation.

---

### **Features**

- **Location Search**: Search for any location globally to get latitude and longitude using OpenWeather Geocoding API.
- **Weather Data Fetching**: Fetches real-time weather data including cloud cover, temperature, and humidity using the OpenWeather API.
- **Solar Power Calculation**: Calculates solar power output based on Global Horizontal Irradiance (GHI), cloud cover, temperature, and humidity.
- **Electricity Price Fetching**: Uses NREL API for U.S. locations to fetch electricity prices, with a fallback to manual input for non-U.S. locations.
- **Advanced Configuration**: Customize solar panel area, efficiency, tilt, and orientation for advanced users.
- **Economic Analysis**: Displays daily savings, annual savings, and ROI based on predicted power output and local electricity prices.
- **Interactive Visualization**: Generates hourly solar power output and savings visualizations using Plotly.
- **Interactive Map**: Visualize the selected location on an interactive map using Folium.

---

### **Tech Stack**
- **Streamlit**: Web framework for interactive dashboards.
- **Folium**: Interactive map for location selection.
- **Plotly**: Interactive graphs for data visualization.
- **OpenWeather API**: For real-time weather data (temperature, cloud cover, humidity, etc.).
- **NREL API**: For fetching electricity prices (U.S. only).
- **Pysolar**: For solar altitude and irradiance calculations.
- **Matplotlib**: For additional visualizations.

---

### **Installation**

1. Clone the repository:
   ```bash
   git clone https://github.com/hitheshrai/solar-power-prediction.git
   cd solar-power-prediction
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory and add your API keys:
   ```plaintext
   OPENWEATHER_API_KEY=your_openweather_api_key
   NREL_API_KEY=your_nrel_api_key
   TIMEZONE_API_KEY=your_timezone_api_key
   ```

4. Run the application:
   ```bash
   streamlit run app.py
   ```

---

### **Usage**

- Enter the location (e.g., "San Francisco") in the search bar.
- Adjust advanced panel configurations (optional).
- Select a time range for solar power predictions.
- View the **power output**, **savings**, and **ROI** based on solar panel configuration.
- Explore economic savings through a daily/annual cost estimator.
- Interactive map shows the location selected.

---

### **Demo**
Visit the demo of the project at [Hithesh's Website](https://hitheshrai.github.io/Hithesh/) or check out the [project's GitHub repository](https://github.com/hitheshrai/solar-power-prediction.git).

---

### **Connect with Me**

- [LinkedIn: Hithesh Rai](https://www.linkedin.com/in/hithesh-rai-p/)
- [Personal Website](https://hitheshrai.github.io/Hithesh/)

---

### **Contributing**

Feel free to open issues or submit pull requests to improve the project! Contributions are welcome.

---

### **License**

This project is licensed under the MIT License.

---

This README provides a comprehensive overview of the project, installation instructions, and usage guide. It also encourages contributions and provides contact links for you. Let me know if you'd like further customization! 🚀