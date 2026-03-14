SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help up down build seed eval test eval-ci logs shell

help:
	@echo "Usage: make <target>"
	@echo "Targets:"
	@echo "  up        - Start all services"
	@echo "  down      - Stop services"
	@echo "  build     - Build the agent image"
	@echo "  seed      - Seed intent index and golden set"
	@echo "  eval      - Run full evaluation"
	@echo "  test      - Run unit and integration tests"
	@echo "  eval-ci   - Run evaluation gate test"
	@echo "  logs      - Follow agent logs"
	@echo "  shell     - Open a shell in agent container"

up:
	docker-compose up -d
	@echo "Services starting..."
	@echo "Agent:      http://localhost:8000"
	@echo "Langfuse:   http://localhost:3000"
	@echo "RedisInsight: http://localhost:8001"
	@echo "Grafana:    http://localhost:3001"
	@echo "Prometheus: http://localhost:9090"

down:
	docker-compose down

build:
	docker-compose build agent

seed:
	python scripts/seed_intent_index.py
	python scripts/seed_golden_set.py

eval:
	python scripts/run_eval.py --all

test:
	pytest tests/unit/ -v
	pytest tests/integration/ -v

eval-ci:
	pytest tests/eval/test_golden_sets.py -v --tb=short
	@echo "Eval gates: tool>=0.90, param>=0.95, goal>=0.85, hallucination<=0.02"

logs:
	docker-compose logs -f agent

shell:
	docker-compose exec agent bash