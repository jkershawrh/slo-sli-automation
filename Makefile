.PHONY: build test test-go test-python lint clean

build:
	go build -o bin/sloscope ./cmd/sloscope

test: test-go test-python

test-go:
	go test ./... -v

test-python:
	cd analysis && python3 -m pytest tests/ -v

lint:
	go vet ./...

clean:
	rm -rf bin/ out/
