.PHONY: build test test-go test-python test-backend lint clean \
       dev dev-backend dev-frontend \
       container-build container-push container-test \
       verify preflight \
       frontend-build frontend-test \
       test-all

build:
	go build -o bin/sloscope ./cmd/sloscope

test: test-go test-python test-backend

test-go:
	go test ./... -v

test-python:
	cd analysis && python3 -m pytest tests/ -v

test-backend:
	python3 -m pytest backend/ -v

lint:
	go vet ./...

clean:
	rm -rf bin/ out/

# Development
dev-backend:
	cd backend && python3 server.py

dev-frontend:
	cd frontend && npm run dev

dev:
	@echo "Starting backend and frontend..."
	@make dev-backend &
	@sleep 2
	@make dev-frontend

# Container
container-build:
	podman build -t sloscope:latest -t quay.io/redhat-gpte/sloscope:latest -f Containerfile .

container-push:
	podman push quay.io/redhat-gpte/sloscope:latest

container-test:
	podman run --rm -d --name sloscope-ci -p 8090:8080 sloscope:latest && \
	sleep 3 && \
	curl -sf http://localhost:8090/health && \
	podman stop sloscope-ci

# Verification
verify:
	bash scripts/verify.sh

preflight:
	bash scripts/preflight.sh

# Frontend
frontend-build:
	cd frontend && npm run build

frontend-test:
	cd frontend && npx vitest run

# Full
test-all: test test-backend frontend-test
