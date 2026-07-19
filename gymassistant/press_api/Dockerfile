FROM python:3.12-slim

WORKDIR /app

# Свой список зависимостей: раньше сюда копировался общий requirements.txt,
# а ставился захардкоженный набор пакетов — файл и установка расходились.
COPY ./press_api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./press_api/api.py ./api.py
COPY ./press_api/press_lstm.pt ./press_lstm.pt
COPY ./press_api/scaler_x.pkl ./scaler_x.pkl
COPY ./press_api/scaler_y.pkl ./scaler_y.pkl

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
