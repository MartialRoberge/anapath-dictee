# -- Build frontend --
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# -- Production --
FROM python:3.12-slim
WORKDIR /app

# Traçabilité ISO 15189 : version exacte du code embarquée (docker build --build-arg MARC_GIT_COMMIT=$(git rev-parse --short HEAD))
ARG MARC_GIT_COMMIT=""
ENV MARC_GIT_COMMIT=${MARC_GIT_COMMIT}

# Install system dependencies for asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY backend/ ./

# Copy frontend build
COPY --from=frontend-build /app/frontend/dist ../frontend/dist

# Copy alembic config
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
