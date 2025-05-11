#!/bin/bash

# Активация виртуального окружения
source .venv/bin/activate

# Проверка наличия зависимостей для форматирования
if ! command -v black &> /dev/null || ! command -v isort &> /dev/null || ! command -v autoflake &> /dev/null || ! command -v flake8 &> /dev/null; then
    echo "Установка инструментов форматирования..."
    pip install black isort autoflake flake8
fi

# Директории для форматирования (относительно корня backend)
DIRS="app fetchers jobs processors tests"

# Переход в корневую директорию backend
cd "$(dirname "$0")/.." || exit

# Использование isort для сортировки импортов
echo "Сортировка импортов с помощью isort..."
isort $DIRS

# Использование black для форматирования кода
echo "Форматирование кода с помощью black..."
black $DIRS

# Удаление неиспользуемых импортов и переменных с помощью autoflake
echo "Удаление неиспользуемых импортов и переменных..."
autoflake --remove-all-unused-imports --remove-unused-variables --recursive --in-place $DIRS

# Запуск flake8 для просмотра оставшихся проблем
echo "Проверка оставшихся проблем с помощью flake8..."
flake8 $DIRS

echo "Форматирование завершено!" 