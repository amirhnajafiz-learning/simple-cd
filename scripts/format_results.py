"""Formats a Prometheus instant-query response as an aligned table.

Reads the JSON body on stdin; used by results.sh for each recorded rule.
"""

import json
import sys

result = json.load(sys.stdin).get("data", {}).get("result", [])
if not result:
    print("  (no data yet - give the run a minute to warm up)")
    sys.exit(0)

# sorted so a backend's direct and dapr rows always sit next to each other.
for series in sorted(
    result,
    key=lambda s: (
        s["metric"].get("backend", ""),
        s["metric"].get("op", ""),
        s["metric"].get("mode", ""),
    ),
):
    m = series["metric"]
    value = float(series["value"][1])
    print(
        f"  {m.get('backend', ''):<9} {m.get('op', ''):<8} "
        f"{m.get('mode', '-'):<7} {value:>10.4f}"
    )
