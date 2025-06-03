# 🐳 Docker Troubleshooting Guide

## Проблемы обнаруженные в логах

### 1. Worker: `ModuleNotFoundError: No module named 'feedparser'`

**Причина**: Отсутствует зависимость в requirements.txt
**Решение**: ✅ Исправлено - feedparser уже есть в requirements.txt

### 2. Cron: `cannot open app/run_scan.sh: No such file`

**Причина**: Неправильный путь в cron скрипте  
**Решение**: ✅ Исправлено - обновлен `cron/run_scan.sh`

### 3. Backend: `AttributeError: module 'app.routers.ai_predictions' has no attribute 'router'`

**Причина**: Отсутствует FastAPI router в ai_predictions модуле  
**Решение**: ✅ Исправлено - добавлен router с placeholder endpoints

## Тестирование исправлений

### Локальное тестирование (без Docker)

```bash
cd backend
python test_isolated_twitter.py
```

Этот скрипт:
- ✅ Проверяет TwitterAPI.io без Docker
- ✅ Использует mock Redis для тестирования
- ✅ Показывает работает ли API ключ

### Docker тестирование

1. **Пересборка образов**:
```bash
cd backend
docker build -t mrbets-backend .
```

2. **Полное тестирование**:
```bash
./test_docker_setup.sh all
```

3. **Только диагностика сети**:
```bash
./test_docker_setup.sh debug
```

## Исправления сетевых проблем

### DNS Configuration

Если есть проблемы с DNS в Docker:

```yaml
# В docker-compose.yml добавьте:
services:
  backend:
    dns:
      - 8.8.8.8
      - 8.8.4.4
      - 1.1.1.1
```

### Network Debugging Container

Используйте специальный debug контейнер:

```bash
docker-compose -f docker-compose.test.yml up -d network-debug
docker-compose -f docker-compose.test.yml exec network-debug ping google.com
docker-compose -f docker-compose.test.yml exec network-debug nslookup api.twitterapi.io
```

## Сетевые утилиты в контейнере

Новый Dockerfile включает утилиты:
- `ping` - для проверки connectivity
- `nslookup` - для DNS debugging  
- `curl` - для HTTP тестирования
- `wget` - альтернатива curl
- `telnet` - для проверки портов
- `netcat` - сетевая диагностика

## Проверка API ключей

```bash
# Убедитесь что переменные установлены
grep TWITTERAPI_IO_KEY .env

# Тест через curl (замените YOUR_KEY)
curl -H "X-API-Key: YOUR_KEY" "https://api.twitterapi.io/twitter/tweet/advanced_search?query=from:OptaJoe"
```

## Логи и мониторинг

### Просмотр логов конкретного сервиса:
```bash
docker-compose logs backend
docker-compose logs worker  
docker-compose logs redis
```

### Логи в реальном времени:
```bash
docker-compose logs -f backend
```

### Вход в контейнер для отладки:
```bash
docker-compose exec backend bash
```

## Пошаговое решение

1. **Остановите все контейнеры**:
   ```bash
   docker-compose down
   ```

2. **Пересоберите backend**:
   ```bash
   docker build -t mrbets-backend backend/
   ```

3. **Запустите тесты**:
   ```bash
   cd backend && ./test_docker_setup.sh
   ```

4. **Если тесты прошли, запустите полную систему**:
   ```bash
   docker-compose up
   ```

## Ожидаемые результаты

После исправлений должны работать:
- ✅ Backend FastAPI на порту 8000
- ✅ Frontend Next.js на порту 3000  
- ✅ Redis на порту 6379
- ✅ Worker процесс (без ошибок feedparser)
- ✅ Cron процесс (находит run_scan.sh)

## Полезные команды

```bash
# Проверка используемых портов
docker-compose ps

# Очистка всех Docker ресурсов
docker system prune -a

# Пересборка без кеша
docker-compose build --no-cache

# Запуск в detached режиме
docker-compose up -d

# Остановка и удаление volumes
docker-compose down -v
``` 