FROM python:3.11

# Установка cron
RUN apt-get update && apt-get install -y cron

# Создание рабочей директории
WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Копируем скрипт scan_fixtures из внешней папки
COPY backend/jobs/scan_fixtures.py /app/scan_fixtures.py

# Копируем bash-обёртку и cron-таблицу
COPY cron/run_scan.sh /app/run_scan.sh
RUN chmod +x /app/run_scan.sh

COPY cron/crontab /etc/cron.d/scan_fixtures
RUN chmod 0644 /etc/cron.d/scan_fixtures
RUN crontab /etc/cron.d/scan_fixtures

# Создание лог-файла
RUN touch /var/log/cron.log

# Команда при запуске
CMD cron && tail -f /var/log/cron.log