FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем и устанавливаем Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Создаем директорию для данных и устанавливаем права
RUN mkdir -p /app/data && \
    chmod 777 /app/data

# Открываем порт
EXPOSE 5000

# Запускаем от root (для простоты) или создаем пользователя с правильными правами
CMD ["python", "app.py"]