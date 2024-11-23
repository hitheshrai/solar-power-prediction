### **README: Solar Power Prediction with Weather Data**

---

## **Solar Power Prediction**

This project predicts the daily solar power output of a solar panel based on weather data (e.g., temperature, humidity, cloud cover, and wind speed). The project demonstrates the use of machine learning to model solar power generation, with an optional interactive dashboard for predictions.

---

### **Features**
- **Data Collection**: Fetches real-time or historical weather data using the OpenWeatherMap API.
- **Data Preprocessing**: Cleans and processes weather data to include relevant features like solar irradiance.
- **Machine Learning**: Trains a Random Forest regression model to predict solar power output.
- **Visualization**: Provides plots comparing predicted vs. actual power outputs.
- **Interactive Dashboard**: Allows users to input weather parameters and get predicted solar power output (optional).

---

### **Installation**

1. Clone the repository:
   ```bash
   git clone https://github.com/hitheshrai/solar-power-prediction.git
   cd solar-power-prediction
   ```

2. Install required libraries:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up the OpenWeatherMap API:
   - Sign up at [OpenWeatherMap](https://openweathermap.org/) to get a free API key.
   - Replace `your_api_key_here` in `fetch_weather.py` with your API key.

---

### **Usage**

#### **1. Fetch Weather Data**
Run the script to fetch weather data:
```bash
python fetch_weather.py
```
This will save weather data in a CSV file (`weather_data.csv`).

#### **2. Preprocess Data**
Clean and process the weather data:
```bash
python preprocess_data.py
```
This will save a cleaned dataset as `processed_weather_data.csv`.

#### **3. Train the Model**
Train the Random Forest model to predict solar power output:
```bash
python train_model.py
```

#### **4. Visualize Results**
Plot actual vs. predicted solar power output:
```bash
python visualize_results.py
```

#### **5. Run the Interactive Dashboard (Optional)**
Launch the Streamlit app:
```bash
streamlit run app.py
```

---

### **Project Structure**
```plaintext
├── fetch_weather.py         # Script to fetch weather data
├── preprocess_data.py       # Script to preprocess weather data
├── train_model.py           # Script to train the ML model
├── visualize_results.py     # Script to visualize results
├── app.py                   # Streamlit dashboard
├── weather_data.csv         # Raw weather data (generated)
├── processed_weather_data.csv # Processed weather data (generated)
├── requirements.txt         # Required Python libraries
├── README.md                # Project documentation
```

---

### **Key Results**
- Trained a Random Forest model with:
  - **Mean Absolute Error (MAE)**: ~X W
  - **Root Mean Squared Error (RMSE)**: ~Y W
- Visualized actual vs. predicted solar power output.

---

### **Tools and Libraries**
- **Programming Language**: Python
- **APIs**: OpenWeatherMap API
- **Libraries**:
  - `Pandas` and `NumPy` for data preprocessing.
  - `Scikit-learn` for machine learning.
  - `Matplotlib` and `Plotly` for visualization.
  - `Streamlit` for the interactive dashboard.

---

### **Future Improvements**
1. Incorporate multi-location weather data for broader predictions.
2. Use a more complex model (e.g., LSTM) to capture temporal weather patterns.
3. Include additional features like solar panel orientation and tilt angle.
4. Deploy the dashboard online using services like Heroku.

---

### **Contributing**
Contributions are welcome! Feel free to submit issues or pull requests.

---

### **License**
This project is licensed under the MIT License.

---

### **Acknowledgments**
- OpenWeatherMap for providing weather data.
- Scikit-learn for its machine learning tools.
- Streamlit for creating an intuitive dashboard interface.

---

### **Contact**
For questions or suggestions, feel free to reach out:
- **Email**: hraipuru@asu.edu
- **LinkedIn**: [Your LinkedIn Profile](https://www.linkedin.com/in/hitheshraip/)
- **GitHub**: [Your GitHub Profile](https://github.com/hitheshrai)

--- 

Feel free to customize this README to suit your needs! Let me know if you want additional edits.