.PHONY: build test test-go test-python test-backend lint clean

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
