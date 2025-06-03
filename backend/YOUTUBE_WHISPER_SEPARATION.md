# 🎥 YouTube + Whisper Separation Strategy

## Проблема

YouTube Fetcher с Whisper требует тяжелые ML зависимости:
- `yt-dlp` для загрузки видео
- `openai-whisper` для транскрипции аудио
- CUDA/cuDNN для ускорения на GPU
- Большой объем дискового пространства для временных файлов

Это делает Docker образ backend очень тяжелым и медленным для развертывания.

## Решение

YouTube + Whisper обработка вынесена на **отдельное железо** с GPU поддержкой.

## Архитектура

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Backend       │    │   YouTube Worker │    │   Main Backend  │
│   (основной)    │───▶│   (отдельный)    │───▶│   (Redis)       │
│                 │    │                  │    │                 │
│ • Twitter API   │    │ • yt-dlp         │    │ • Обработка     │
│ • Football API  │    │ • Whisper        │    │   результатов   │
│ • News Scraping │    │ • GPU/CUDA       │    │ • Векторизация  │
│ • RSS Feeds     │    │ • Локальное      │    │ • Хранение      │
│                 │    │   хранение       │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Удаленные компоненты

### 1. Файлы
- ❌ `backend/fetchers/youtube_fetcher.py` - удален
- ❌ YouTube зависимости из `requirements.txt`

### 2. Зависимости
```bash
# Удалено из requirements.txt:
# yt-dlp>=2024.1.19
# openai-whisper>=20231117
```

### 3. Environment Variables
```bash
# Удалено из .env:
# YOUTUBE_API_KEY
# WHISPER_MODEL
# TEMP_AUDIO_DIR
```

## Интеграция с отдельным YouTube Worker

### Через Redis Streams

**YouTube Worker** (отдельное железо) будет:
1. Мониторить YouTube каналы
2. Скачивать новые видео с yt-dlp
3. Транскрибировать аудио с Whisper
4. Отправлять результаты в Redis Stream

**Main Backend** будет:
1. Читать транскрипции из Redis Stream
2. Обрабатывать текст через LLM Content Analyzer
3. Создавать векторные embeddings
4. Сохранять в Pinecone/Supabase

### Пример сообщения в Redis

```json
{
  "event_type": "youtube_transcript",
  "source": "youtube",
  "match_id": "12345", 
  "timestamp": 1701234567,
  "payload": {
    "video_id": "abc123",
    "channel_name": "Sky Sports",
    "title": "Manchester United vs Liverpool Preview",
    "transcript": "В сегодняшнем матче...",
    "duration": 1200,
    "url": "https://youtube.com/watch?v=abc123",
    "published_at": "2024-01-15T10:00:00Z"
  },
  "meta": {
    "whisper_model": "medium",
    "confidence": 0.89,
    "language": "en",
    "processed_at": "2024-01-15T10:05:00Z"
  }
}
```

## Deployment Strategy

### Backend (основной)
- 🚀 Быстрый deployment без ML зависимостей
- 🐳 Легкий Docker образ (~500MB вместо ~5GB)
- ⚡ Быстрая установка dependencies (2-3 минуты вместо 30-60)

### YouTube Worker (отдельно)
- 🖥️ Запуск на железе с GPU (RTX/Tesla)
- 🔄 Периодический запуск (каждые 6-12 часов)
- 💾 Локальное временное хранение видеофайлов
- 🧠 Whisper model loading в память для ускорения

## Мониторинг

### Backend Logs
```bash
docker-compose logs backend | grep youtube
# Должно показывать: "YouTube processing delegated to separate worker"
```

### YouTube Worker Logs (отдельно)
```bash
tail -f youtube_worker.log
# 2024-01-15 10:00:00 - Processing Sky Sports channel
# 2024-01-15 10:02:30 - Downloaded video abc123 (1.2GB)
# 2024-01-15 10:05:45 - Whisper transcription completed (confidence: 0.89)
# 2024-01-15 10:06:00 - Sent to Redis stream: stream:raw_events
```

## Будущая интеграция

Когда YouTube Worker будет готов:

1. **Создать отдельный репозиторий**: `mrbets-youtube-worker`
2. **Настроить cron задачу**: на GPU сервере
3. **Подключить Redis**: тот же REDIS_URL что и main backend
4. **Мониторинг**: через тот же Redis Stream

## Преимущества

✅ **Быстрый deployment** основного backend  
✅ **Изолированные зависимости** ML от веб-сервиса  
✅ **Масштабируемость** - можно добавить больше GPU workers  
✅ **Надежность** - сбой YouTube не ломает основной сервис  
✅ **Экономия ресурсов** - GPU только когда нужно  

## Недостатки

⚠️ **Дополнительная сложность** управления двумя системами  
⚠️ **Задержка** между публикацией видео и обработкой  
⚠️ **Дополнительное железо** требуется для GPU  

---

**Итог**: Эта стратегия позволяет держать основной backend легким и быстрым, 
при этом не теряя возможности обрабатывать YouTube контент на мощном железе. 