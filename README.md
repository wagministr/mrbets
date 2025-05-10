# MrBets.ai

> AI-powered football prediction platform that delivers pre-analyzed match insights based on comprehensive data collection, advanced AI reasoning, and betting value assessment.

## 🏗️ Architecture Overview

MrBets.ai uses a monorepo structure with:
- **Frontend**: Next.js 14 with App Router deployed on Vercel
- **Backend**: FastAPI with microservices architecture, Redis Streams for distributed processing
- **Data Processing**: Pinecone for vector search, OpenAI for embeddings and analysis
- **Storage**: Supabase (PostgreSQL + Storage)

## 🚀 Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js 20.x
- Python 3.11+
- Supabase account and project
- API keys for: API-Football, OpenAI, Pinecone, DeepL

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/yourusername/mrbets.git
cd mrbets
```

2. Copy the environment example and add your API keys:
```bash
cp env.example .env
# Edit .env with your API keys
```

3. Start the Docker environment:
```bash
docker compose up
```

4. Access:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

## 📁 Project Structure

```
MrBets/
├── frontend/           # Next.js 14 с App Router
├── backend/            # FastAPI бэкенд
├── docker-compose.yml  # Конфигурация для локальной разработки
├── .github/            # GitHub Actions для CI/CD
├── README.md           # Описание проекта
├── CONTEXT.md          # Контекст и архитектура проекта
└── BACKEND.md          # Документация по бэкенду
```

## 🧩 Key Components

- **Fixtures Scanner**: Collects upcoming match data
- **Data Fetchers**: Gathers information from multiple sources
- **Processor Pipeline**: Translates, chunks, vectorizes content
- **Retriever Builder**: Creates contextual match information
- **LLM Reasoner**: Generates predictions using GPT-4o
- **Frontend Dashboard**: Displays predictions with value bets

For detailed technical documentation, see:
- [BACKEND.md](./BACKEND.md) - Technical details of the backend system
- [CONTEXT.md](./CONTEXT.md) - Project context and architecture overview

## 📅 Development Timeline

Project is scheduled for completion by August 9, 2025, with incremental delivery of components. See CONTEXT.md for detailed timeline.

## 📝 License

Proprietary. All rights reserved. 