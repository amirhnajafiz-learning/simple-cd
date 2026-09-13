#!/usr/bin/env bash

set -euo pipefail

PROM="${PROM:-http://localhost:9091}"
HERE="$(cd "$(dirname "$0")" && pwd)"

if ! curl -sf "$PROM/-/ready" >/dev/null; then
  echo "Prometheus is not reachable at $PROM. Start the stack with 'make up' first." >&2
  exit 1
fi

show() {
  echo "=== $1 ==="
  curl -sG "$PROM/api/v1/query" --data-urlencode "query=$2" | python3 "$HERE/format_results.py"
  echo
}

show "p50 latency (seconds)"                     'bench:latency_p50'
show "p99 latency (seconds)"                     'bench:latency_p99'
show "throughput (ops/sec)"                      'bench:throughput'
show "Dapr overhead p50 (x the direct path)"     'bench:dapr_overhead_ratio_p50'
show "Dapr overhead p50 (added seconds)"         'bench:dapr_overhead_seconds_p50'
