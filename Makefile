.PHONY: help setup up down logs logs-api logs-db status restart clean verify build

help:
	@echo "Arada Intelligence OS — Common Commands"
	@echo ""
	@echo "Setup & Deployment:"
	@echo "  make setup      — Initial setup (environment, migrations, services)"
	@echo "  make up         — Start all services"
	@echo "  make down       — Stop all services"
	@echo "  make restart    — Restart all services"
	@echo ""
	@echo "Monitoring & Debugging:"
	@echo "  make status     — Show service status"
	@echo "  make logs       — View all logs (streaming)"
	@echo "  make logs-api   — View API logs"
	@echo "  make logs-db    — View PostgreSQL logs"
	@echo "  make verify     — Run health checks"
	@echo ""
	@echo "Maintenance:"
	@echo "  make build      — Rebuild Docker images"
	@echo "  make clean      — Stop and remove all containers/volumes"
	@echo ""

setup:
	bash setup.sh

up:
	docker-compose up -d

down:
	docker-compose down

restart:
	docker-compose restart

status:
	docker-compose ps

logs:
	docker-compose logs -f

logs-api:
	docker-compose logs -f api

logs-db:
	docker-compose logs -f postgres

verify:
	bash api/verify.sh

build:
	docker-compose build

clean:
	docker-compose down -v
	@echo "All containers and volumes removed"

.DEFAULT_GOAL := help
