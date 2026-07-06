# Stage 1: Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --legacy-peer-deps 2>/dev/null || npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + built frontend + Go CLI
FROM python:3.11-slim
WORKDIR /app

# Install Go for the CLI binary
RUN apt-get update && apt-get install -y --no-install-recommends golang-go git && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt ./
COPY backend/requirements.txt ./backend-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r backend-requirements.txt

# Go build
COPY go.mod go.sum* ./
COPY cmd/ ./cmd/
COPY internal/ ./internal/
COPY analysis/schemas/ ./analysis/schemas/
RUN go build -o /usr/local/bin/sloscope ./cmd/sloscope

# Analysis modules
COPY analysis/ ./analysis/

# Backend
COPY backend/ ./backend/

# Test data and fixtures
COPY testdata/ ./testdata/

# Built frontend
COPY --from=frontend-build /build/dist ./frontend/dist/

# Verification scripts
COPY scripts/ ./scripts/
COPY Makefile ./

RUN chown -R 1001:0 /app && chmod -R g=u /app
USER 1001

EXPOSE 8080

ENV PYTHONPATH=/app/analysis

CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8080"]
