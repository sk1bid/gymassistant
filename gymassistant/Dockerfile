FROM python:3.12-slim

WORKDIR /app

# Только зависимости бота: PyTorch сюда больше не приезжает.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "./app.py"]
