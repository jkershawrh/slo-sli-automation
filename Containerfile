# Stage 1a: Build demo frontend
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 1b: Build dashboard frontend
FROM node:20-slim AS dashboard-build
WORKDIR /build
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

# Build the CLI with the version declared by go.mod; no Go compiler in runtime.
FROM golang:1.26.4 AS cli-build
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/ ./cmd/
COPY internal/ ./internal/
RUN CGO_ENABLED=0 go build -trimpath -o /sloscope ./cmd/sloscope

# Runtime: analysis, API and read-only UI previews.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
COPY backend/requirements.txt ./backend-requirements.txt
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY --from=cli-build /sloscope /usr/local/bin/sloscope

# Analysis modules
COPY analysis/ ./analysis/

# Backend
COPY backend/ ./backend/

# Test data and fixtures
COPY testdata/ ./testdata/

# Built frontends
COPY --from=frontend-build /build/dist ./frontend/dist/
COPY --from=dashboard-build /build/dist ./dashboard/dist/

# Verification scripts
COPY scripts/ ./scripts/
COPY Makefile ./

RUN chown -R 1001:0 /app && chmod -R g=u /app
USER 1001

EXPOSE 8080

ENV PYTHONPATH=/app/analysis

CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8080"]
