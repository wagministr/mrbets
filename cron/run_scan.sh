#!/bin/sh

# run_scan.sh - Скрипт для запуска сканирования матчей через cron

# Переход в рабочую директорию
cd /app

# Установка переменных окружения
export PYTHONPATH=/app

# Логирование старта
echo "$(date): Starting fixtures scan..."

# Запуск сканирования через backend модуль
python -m jobs.scan_fixtures

# Логирование завершения  
echo "$(date): Fixtures scan completed"