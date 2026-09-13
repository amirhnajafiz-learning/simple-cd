COMPOSE := docker compose -f deploy/docker-compose.yml

.PHONY: up down logs build test results results-json plots clean

## up: build and start the whole stack (backends, bench + sidecar, Prometheus)
up:
	$(COMPOSE) up --build -d
	# The sidecar shares the app container's network namespace, which is fixed at
	# creation time. Rebuilding the app replaces that container, so the sidecar
	# has to be recreated or it is left pointing at a namespace that is gone.
	$(COMPOSE) up -d --force-recreate --no-deps dapr
	@echo "bench metrics : http://localhost:9100/metrics"
	@echo "dapr metrics  : http://localhost:9090/metrics"
	@echo "prometheus    : http://localhost:9091"

## down: stop everything and remove volumes
down:
	$(COMPOSE) down -v

## logs: follow the benchmark app's output
logs:
	$(COMPOSE) logs -f bench dapr

## build: compile and vet locally, no containers involved
build:
	go vet ./...
	go build ./...

## results: print the six results and the Dapr overhead ratio from Prometheus
results:
	@./scripts/results.sh

## results-json: same capture as JSON, e.g. make results-json > traces/run.json
results-json:
	@./scripts/results.sh --json

## plots: chart sampled captures, e.g. make plots FILES="20000.txt 200000.txt"
plots:
	@./scripts/plot_results.py $(FILES) -o plots
