from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend" / "data" / "ev_energy_consumption.csv"
OUTPUT = ROOT / "backend" / "model" / "ev_best_model_compatible.pkl"
VERCEL_OUTPUT = ROOT / "backend" / "model" / "ev_best_model_compatible.ubj"
JSON_OUTPUT = ROOT / "backend" / "model" / "ev_best_model_compatible.json"

COLUMN_MAP = {
    "speed_kmh": "평균 주행 속도", "payload_kg": "적재/탑승 중량", "ambient_temp_C": "외기 온도",
    "hvac_power_kw": "냉난방 소비 전력", "road_grade_pct": "도로 경사도", "battery_temp_C": "배터리 온도",
    "driving_style_index": "운전 성향 지수", "tire_pressure_bar": "타이어 공기압", "trip_distance_km": "주행 거리",
    "energy_consumption_kwhper100km": "100km 당 에너지소비량",
}
FEATURES = list(COLUMN_MAP.values())[:-1]
TARGET = "100km 당 에너지소비량"

df = pd.read_csv(DATA).rename(columns=COLUMN_MAP)
X_train, X_test, y_train, y_test = train_test_split(df[FEATURES], df[TARGET], test_size=.20, random_state=42)
model = XGBRegressor(
    objective="reg:squarederror", random_state=42, n_jobs=1, subsample=.8, reg_lambda=5,
    n_estimators=700, max_depth=2, learning_rate=.08, colsample_bytree=.8,
)
model.fit(X_train, y_train)
pred = model.predict(X_test)
metrics = {
    "r2": round(r2_score(y_test, pred), 4), "mae": round(mean_absolute_error(y_test, pred), 4),
    "rmse": round(root_mean_squared_error(y_test, pred), 4),
}
joblib.dump(model, OUTPUT)
model.get_booster().save_model(VERCEL_OUTPUT)
model.get_booster().save_model(JSON_OUTPUT)
print(metrics)
