# SafeRoute — Intelligent Safe Route Navigation System

Production-grade async RESTful backend for safety-first navigation targeting women and vulnerable groups.

## Features

- **Safety-first routing** — Routes optimized for personal safety, not just distance
- **Community reports** — Crowd-sourced safety incident reporting
- **SOS alerts** — One-tap emergency alerts with location
- **Time-based risk** — Dynamic scoring based on time of day
- **JWT authentication** — Secure token-based auth with bcrypt

## Tech Stack

- **Python 3.11** + **FastAPI** (async-first)
- **PostgreSQL 15** + **PostGIS** (geospatial)
- **SQLAlchemy 2.0** (async ORM)
- **NetworkX** (graph routing)
- **Pydantic** (validation)

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ with PostGIS extension

### Installation

```bash
# 1. Clone and navigate
cd saferoute

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your PostgreSQL credentials

# 5. Enable PostGIS
psql -U postgres -c "CREATE DATABASE saferoute_db;"
psql -U postgres -d saferoute_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# 6. Seed database (creates tables + test data)
python scripts/seed.py

# 7. Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API Documentation

Once running:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health check**: http://localhost:8000/health

## Test Credentials

```
admin@saferoute.dev / Admin@1234
priya@saferoute.dev / Test@1234
test@saferoute.dev / Test@1234
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` — Create account
- `POST /api/v1/auth/login` — Get JWT tokens

### User
- `GET /api/v1/user/me` — Get profile (auth required)

### Routing
- `POST /api/v1/route/safest` — Compute safest route
- `POST /api/v1/route/shortest` — Compute shortest route

### Reports
- `POST /api/v1/report` — Submit safety report
- `GET /api/v1/report/nearby` — Get nearby reports

### SOS
- `POST /api/v1/sos/trigger` — Trigger emergency alert

## Example Usage

```bash
# 1. Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Test User","email":"user@test.com","password":"Test@1234"}'

# 2. Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@test.com","password":"Test@1234"}'

# 3. Get safest route (use token from login)
curl -X POST http://localhost:8000/api/v1/route/safest \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_lat":22.7196,"source_lng":75.8577,"dest_lat":22.7250,"dest_lng":75.8650}'
```

## Region

Currently configured for **Indore, India** (22.7196°N, 75.8577°E).

Seed data includes:
- 5 test users
- 50 safety reports (5 hotspots + 45 random)
- 20 location pings
- 10 sample routes

## Architecture

```
FastAPI App
├── Routes (auth, user, routing, report, sos)
├── Services (business logic)
├── Models (SQLAlchemy ORM)
├── Schemas (Pydantic validation)
└── Utils (geo, graph, risk, logger)
```

## Performance

- Route computation: <800ms (P95)
- Auth response: <200ms
- Async-first design with connection pooling
- Graph caching (LRU, 5min TTL)

## License

MIT
