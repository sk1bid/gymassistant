FROM python:3.12-slim

WORKDIR /app

# Копируем зависимости (для API они такие же или меньше)
COPY ./requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn torch numpy scikit-learn

# Копируем код и файлы модели
COPY ./press_api/api.py ./api.py
COPY ./press_api/press_lstm.pt ./press_lstm.pt
COPY ./press_api/scaler_x.pkl ./scaler_x.pkl
COPY ./press_api/scaler_y.pkl ./scaler_y.pkl

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
