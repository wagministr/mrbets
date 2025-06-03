# MrBets Backend Dockerfile
FROM python:3.11-slim

# Установка системных зависимостей включая сетевые утилиты
RUN apt-get update && apt-get install -y \
    # Сетевые утилиты для диагностики
    iputils-ping \
    dnsutils \
    curl \
    wget \
    telnet \
    netcat-openbsd \
    # Системные зависимости для Python пакетов
    gcc \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование requirements.txt и установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Создание директорий для логов и данных
RUN mkdir -p /app/logs /app/data

# Настройка переменных окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Установка правильных DNS серверов по умолчанию
# (будет перезаписано docker-compose если нужно)
ENV RESOLV_CONF="nameserver 8.8.8.8\nnameserver 8.8.4.4"

# Expose порты
EXPOSE 8000

# Healthcheck для проверки работоспособности
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Команда по умолчанию
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 