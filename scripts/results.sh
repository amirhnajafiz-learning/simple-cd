#!/usr/bin/env bash
# Prints a benchmark capture: the run's configuration, then all six results.
# Pass --json for the same data as JSON. Any other flags go to collect_results.py.
set -euo pipefail

PROM="${PROM:-http://localhost:9091}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# Fail with a readable message rather than a parser traceback when the stack is
# not up -- running `make results` before `make up` is an easy mistake.
if ! curl -sf "$PROM/-/ready" >/dev/null; then
  echo "Prometheus is not reachable at $PROM. Start the stack with 'make up' first." >&2
  exit 1
fi

exec python3 "$HERE/collect_results.py" --prometheus "$PROM" "$@"
