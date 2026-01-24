from fastapi import FastAPI
from pydantic import BaseModel
import torch
import torch.nn as nn
import numpy as np
import pickle
import os
import threading

# === 1. Конфигурация ===
SEQ_LEN = 5
FEATURES = 5  # [вес, повторы, объем, Δвес, Δповторы]
BAR_WEIGHT = 20.0
ALLOWED_PLATES = [25.0, 20.0, 15.0, 10.0, 5.0, 2.5, 1.25]

app = FastAPI(
    title="Gym Assistant LSTM API",
    description="Предсказание веса на следующий подход 💪 (v2, расширенная архитектура)"
)
lock = threading.Lock()


# === 2. Модель ===
class LSTMPressV2(nn.Module):
    def __init__(self, input_size=FEATURES, hidden_size=128):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.fc1 = nn.Linear(hidden_size, 64)
        self.fc2 = nn.Linear(64, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        out = torch.relu(self.fc1(out[:, -1, :]))
        out = self.fc2(out)
        return out


# === 3. Загрузка модели и скейлеров ===
def load_model_and_scalers():
    global model, scaler_x, scaler_y

    model_path = os.getenv("MODEL_PATH", "/app/models/press_lstm.pt")
    scaler_x_path = os.getenv("SCALER_X_PATH", "/app/models/scaler_x.pkl")
    scaler_y_path = os.getenv("SCALER_Y_PATH", "/app/models/scaler_y.pkl")

    with lock:
        print(f"🔄 Loading model from: {model_path}")
        model = LSTMPressV2(input_size=FEATURES)
        state = torch.load(model_path, map_location="cpu")
        model.load_state_dict(state)
        model.eval()

        print(f"🔄 Loading scalers: {scaler_x_path}, {scaler_y_path}")
        with open(scaler_x_path, "rb") as fx:
            scaler_x = pickle.load(fx)
        with open(scaler_y_path, "rb") as fy:
            scaler_y = pickle.load(fy)

        print("✅ Model and scalers loaded successfully")


# загружаем при старте
load_model_and_scalers()


# === 4. Вспомогательные функции ===
def round_to_available(weight):
    """Округляем до возможного набора блинов."""
    total = round(weight / 2.5) * 2.5
    total = max(BAR_WEIGHT, total)

    target_side = (total - BAR_WEIGHT) / 2.0
    used = []
    remain = target_side
    for p in ALLOWED_PLATES:
        cnt = int((remain + 1e-6) // p)
        if cnt > 0:
            used.extend([p] * cnt)
            remain -= cnt * p

    real_total = BAR_WEIGHT + 2 * sum(used)
    return round(real_total, 2), used


# === 5. FastAPI схемы ===
class SequenceInput(BaseModel):
    sequence: list[list[float]]  # [[вес, повторы, объем, Δвес, Δповторы], ...]


# === 6. Эндпоинты ===
@app.post("/predict")
def predict(data: SequenceInput):
    try:
        seq = np.array(data.sequence, dtype=np.float32)
        if seq.shape != (SEQ_LEN, FEATURES):
            return {"error": f"Ожидалась последовательность {SEQ_LEN}×{FEATURES}, получено {seq.shape}"}

        # масштабирование и предсказание
        seq_scaled = scaler_x.transform(seq).reshape(1, SEQ_LEN, FEATURES)
        tensor = torch.tensor(seq_scaled, dtype=torch.float32)

        with torch.no_grad():
            y_pred = model(tensor).numpy()

        raw_total = float(scaler_y.inverse_transform(y_pred)[0][0])
        raw_total = max(BAR_WEIGHT, raw_total)

        real_total, used = round_to_available(raw_total)

        return {
            "next_weight": real_total,
            "plates_each_side": used,
            "bar_weight": BAR_WEIGHT
        }

    except Exception as e:
        return {"error": str(e)}


@app.post("/reload_model")
def reload_model():
    """Перезагружает модель и скейлеры без перезапуска контейнера"""
    try:
        load_model_and_scalers()
        return {"status": "ok", "message": "Model reloaded successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/model_info")
def model_info():
    """Информация о текущей модели"""
    total_params = sum(p.numel() for p in model.parameters())
    return {
        "model_version": "v2.0-fatigue",
        "features": FEATURES,
        "total_params": total_params,
        "model_path": os.getenv("MODEL_PATH", "/app/models/press_lstm.pt")
    }


@app.get("/")
def root():
    return {"status": "ok", "message": "LSTM Gym API v2 🚀"}
