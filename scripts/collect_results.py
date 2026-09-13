#!/usr/bin/env python3
"""Collects a benchmark run from Prometheus as text or JSON.

    scripts/collect_results.py              # text capture, run info at the top
    scripts/collect_results.py --json       # same data as JSON

Both formats start from the same query set, so a text capture and a JSON export
of the same run always agree. The run's configuration is read from the
`bench_config_info` metric published by the app itself rather than from the
compose file, so a capture describes the run that actually happened.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import datetime, timezone

# Recorded rules to collect, in display order: section title -> rule name.
# These are defined in deploy/prometheus/rules.yml.
SECTIONS = OrderedDict(
    [
        ("p50 latency (seconds)", "bench:latency_p50"),
        ("p95 latency (seconds)", "bench:latency_p95"),
        ("p99 latency (seconds)", "bench:latency_p99"),
        ("throughput (ops/sec)", "bench:throughput"),
        ("Dapr overhead p50 (x the direct path)", "bench:dapr_overhead_ratio_p50"),
        ("Dapr overhead p50 (added seconds)", "bench:dapr_overhead_seconds_p50"),
    ]
)

# JSON keys for the same rules, kept machine-friendly.
JSON_KEYS = {
    "bench:latency_p50": "latency_p50",
    "bench:latency_p95": "latency_p95",
    "bench:latency_p99": "latency_p99",
    "bench:throughput": "throughput",
    "bench:dapr_overhead_ratio_p50": "overhead_ratio_p50",
    "bench:dapr_overhead_seconds_p50": "overhead_seconds_p50",
}

CONFIG_FIELDS = [
    "payload_bytes",
    "keyspace",
    "concurrency",
    "rate",
    "warmup",
    "duration",
]


def query(prom, expr):
    """Runs one instant query, returning the raw series list (empty on no data)."""
    url = f"{prom}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            body = json.load(resp)
    except (urllib.error.URLError, TimeoutError) as err:
        sys.exit(
            f"Cannot reach Prometheus at {prom}: {err}\n"
            f"Start the stack with 'make up' first."
        )
    except json.JSONDecodeError:
        sys.exit(f"Prometheus at {prom} returned a non-JSON response.")
    if body.get("status") != "success":
        sys.exit(
            f"Prometheus rejected the query {expr!r}: {body.get('error', 'unknown error')}"
        )
    return body["data"]["result"]


def collect_config(prom):
    """Reads the run's settings from the gauge the app publishes."""
    series = query(prom, "bench_config_info")
    if not series:
        return None
    metric = series[0]["metric"]
    config = OrderedDict()
    for field in CONFIG_FIELDS:
        value = metric.get(field)
        # Numeric fields come back as label strings; keep them numeric in JSON.
        if value is not None and field not in ("warmup", "duration"):
            try:
                value = int(value)
            except ValueError:
                pass
        config[field] = value
    return config


def collect_connectors(prom):
    """Reads which connectors came up, as {"redis-dapr": True, ...}."""
    out = OrderedDict()
    for s in sorted(
        query(prom, "bench_connector_up"),
        key=lambda s: (s["metric"].get("backend", ""), s["metric"].get("mode", "")),
    ):
        m = s["metric"]
        out[f"{m.get('backend', '?')}-{m.get('mode', '?')}"] = (
            float(s["value"][1]) == 1.0
        )
    return out


def collect_section(prom, rule):
    """Reads one rule into {"backend op": {mode: value}}.

    Overhead rules carry no `mode` label (they are already a ratio of the two),
    so those land under the key "value".
    """
    grouped = OrderedDict()
    for s in sorted(
        query(prom, rule),
        key=lambda s: (
            s["metric"].get("backend", ""),
            s["metric"].get("op", ""),
            s["metric"].get("mode", ""),
        ),
    ):
        m = s["metric"]
        key = f"{m.get('backend', '?')} {m.get('op', '?')}"
        grouped.setdefault(key, OrderedDict())[m.get("mode", "value")] = float(
            s["value"][1]
        )
    return grouped


def collect(prom):
    """Gathers a whole run: when, what settings, and every recorded rule."""
    return OrderedDict(
        [
            ("captured_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
            ("prometheus", prom),
            ("config", collect_config(prom)),
            ("connectors_up", collect_connectors(prom)),
            (
                "results",
                OrderedDict(
                    (JSON_KEYS[rule], collect_section(prom, rule))
                    for rule in SECTIONS.values()
                ),
            ),
        ]
    )


def render_text(run):
    """The human-readable capture: run info first, then a block per rule."""
    lines = ["=== run info ==="]
    lines.append(f"  captured        {run['captured_at']}")
    lines.append(f"  prometheus      {run['prometheus']}")
    if run["config"]:
        for field in CONFIG_FIELDS:
            lines.append(f"  {field:<15} {run['config'].get(field, '?')}")
    else:
        # Explicit, because a capture with no settings recorded is a capture you
        # cannot reproduce later.
        lines.append(
            "  config          (unavailable - bench_config_info not scraped yet)"
        )
    up = run["connectors_up"]
    lines.append(
        f"  connectors up   {sum(up.values())}/{len(up)}"
        if up
        else "  connectors up   (none reported)"
    )
    down = [name for name, ok in up.items() if not ok]
    if down:
        lines.append(f"  DOWN            {', '.join(down)}")
    lines.append("")

    for title, rule in SECTIONS.items():
        lines.append(f"=== {title} ===")
        rows = run["results"][JSON_KEYS[rule]]
        if not rows:
            lines.append("  (no data yet - give the run a minute to warm up)")
        for group, modes in rows.items():
            backend, _, op = group.partition(" ")
            for mode, value in modes.items():
                label = "-" if mode == "value" else mode
                # 6 significant figures, not fixed decimals: a fixed %.4f
                # collapses sub-millisecond latencies (0.00016 and 0.00024 both
                # print as 0.0002) and quietly distorts the ratios derived from
                # the capture. %g keeps precision at any magnitude.
                lines.append(f"  {backend:<9} {op:<8} {label:<7} {value:>14.6g}")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--prometheus", default="http://localhost:9091", help="Prometheus base URL"
    )
    ap.add_argument(
        "--json", action="store_true", help="emit JSON instead of the text capture"
    )
    args = ap.parse_args()

    run = collect(args.prometheus.rstrip("/"))
    print(json.dumps(run, indent=2) if args.json else render_text(run))


if __name__ == "__main__":
    main()
