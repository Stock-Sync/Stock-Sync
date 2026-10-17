# Auth Service

Authentication and user management service for StockSync.

## Features

- User registration with email and password
- Secure password hashing (bcrypt)
- JWT-based authentication with access and refresh tokens
- HTTP-only, Secure, SameSite=Lax cookies
- Token refresh endpoint
- User profile endpoint

## Endpoints

- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login and set auth cookies
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - Clear auth cookies
- `GET /api/v1/auth/me` - Get current user info

## Development

### Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your settings
```

### Database Migrations

```bash
# Run migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"
```

### Run

```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
# Build
docker build -t auth-service .

# Run
docker run -p 8000:8000 --env-file .env auth-service
```

## Configuration

Environment variables (see `.env.example`):

- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET_KEY` - Secret key for JWT signing
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` - Access token TTL
- `JWT_REFRESH_TOKEN_EXPIRE_DAYS` - Refresh token TTL
- `COOKIE_SECURE` - Set to `true` for HTTPS
- `COOKIE_DOMAIN` - Cookie domain