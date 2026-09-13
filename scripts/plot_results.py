#!/usr/bin/env python3
"""Plots sampled `results.sh` output as SVG bar charts.

Usage:
    scripts/plot_results.py 20000.txt 200000.txt [-o plots/]

Each input is one captured run (the filename becomes the run's label, so name
them after whatever you varied -- the rate, the payload size). One chart is
written per metric, with a panel per run so the runs sit side by side on a
shared scale.

Pure standard library on purpose: the output is SVG, so the project stays
runnable with nothing but python3, exactly like format_results.py.
"""

import argparse
import os
import re
import sys
from collections import OrderedDict

# Two categorical slots, fixed order: direct is always blue, dapr always orange,
# in every chart. Colours follow the entity, never its rank or value, so a
# reader learns the mapping once. Verified colourblind-safe (worst-pair
# deltaE 24.7 under protanopia, well clear of the 8.0 floor).
RGB = {
    "direct": "rgb(42, 120, 214)",  # #2a78d6 blue
    "dapr": "rgb(235, 104, 52)",  # #eb6834 orange
}
SURFACE = "rgb(252, 252, 251)"  # chart surface, painted explicitly
INK = "rgb(11, 11, 11)"  # primary text
INK_MUTED = "rgb(82, 81, 78)"  # secondary text: values, axis labels
GRID = "rgb(223, 222, 218)"  # recessive hairline gridlines

# Sections of results.sh output we plot, in display order. Anything else in the
# file (the overhead ratios, which are derived from these) is skipped: they are
# the same numbers divided, so plotting them would just restate the bars.
METRICS = OrderedDict(
    [
        ("p50 latency", {"unit": "ms", "scale": 1000.0, "lower_better": True}),
        ("p95 latency", {"unit": "ms", "scale": 1000.0, "lower_better": True}),
        ("p99 latency", {"unit": "ms", "scale": 1000.0, "lower_better": True}),
        ("throughput", {"unit": "ops/s", "scale": 1.0, "lower_better": False}),
    ]
)

SECTION_RE = re.compile(r"^===\s*(.+?)\s*===$")
# e.g. "  postgres  read     dapr        0.1823"
ROW_RE = re.compile(r"^\s+(\w+)\s+(\w+)\s+(direct|dapr|-)\s+([\d.eE+-]+)\s*$")


def parse(path):
    """Reads one results.sh capture into {metric: {"backend op": {mode: value}}}."""
    data = {}
    metric = None
    with open(path) as fh:
        for line in fh:
            header = SECTION_RE.match(line.rstrip())
            if header:
                # Match on prefix so "p50 latency (seconds)" finds "p50 latency".
                metric = next(
                    (m for m in METRICS if header.group(1).startswith(m)), None
                )
                continue
            row = ROW_RE.match(line.rstrip("\n"))
            if not row or metric is None:
                continue
            backend, op, mode, value = row.groups()
            if mode == "-":  # a derived overhead row, not a measurement
                continue
            data.setdefault(metric, OrderedDict()).setdefault(f"{backend} {op}", {})[
                mode
            ] = float(value)
    return data


def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def nice_ticks(top, count=4):
    """Rounds the axis maximum up to a readable step, returning (max, ticks)."""
    if top <= 0:
        return 1.0, [0.0, 1.0]
    raw = top / count
    magnitude = 10 ** int(f"{raw:e}".split("e")[1])
    for factor in (1, 2, 2.5, 5, 10):
        step = magnitude * factor
        if step * count >= top:
            break
    axis_max = step * count
    return axis_max, [step * i for i in range(count + 1)]


def fmt(value, unit):
    if unit == "ops/s":
        return f"{value:,.0f}"
    return f"{value:.2f}" if value < 10 else f"{value:.1f}"


# --- Layout constants (px) --------------------------------------------------
PANEL_W, ROW_H, BAR_H = 340, 44, 15  # BAR_H <= 24: bars never fill their band
LABEL_W, PAD, GAP = 108, 28, 34  # GAP: horizontal space between panels


def render(metric, runs, out_path):
    """Writes one SVG: a panel per run, grouped horizontal bars within each."""
    spec = METRICS[metric]
    groups = list(
        OrderedDict((g, None) for run in runs.values() for g in run.get(metric, {}))
    )
    if not groups:
        return False

    # One shared scale across panels -- panels on different scales would make
    # the runs look identical when they are not.
    peak = max(
        v * spec["scale"]
        for run in runs.values()
        for row in run.get(metric, {}).values()
        for v in row.values()
    )
    axis_max, ticks = nice_ticks(peak)

    plot_w = PANEL_W - LABEL_W
    body_h = len(groups) * ROW_H
    width = PAD * 2 + len(runs) * PANEL_W + GAP * (len(runs) - 1)
    height = PAD + 58 + body_h + 52

    better = "lower is better" if spec["lower_better"] else "higher is better"
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="system-ui, -apple-system, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        f'<text x="{PAD}" y="{PAD}" font-size="15" font-weight="600" fill="{INK}">'
        f'{esc(metric)} <tspan font-weight="400" fill="{INK_MUTED}">({spec["unit"]}, {better})</tspan></text>',
    ]

    # Legend: always present for two series, so identity is never colour-alone.
    lx = PAD
    for mode in ("direct", "dapr"):
        svg.append(
            f'<rect x="{lx}" y="{PAD + 12}" width="9" height="9" rx="2" fill="{RGB[mode]}"/>'
        )
        svg.append(
            f'<text x="{lx + 14}" y="{PAD + 20}" font-size="11" fill="{INK_MUTED}">{mode}</text>'
        )
        lx += 64

    top = PAD + 58
    for panel, (run_name, run) in enumerate(runs.items()):
        ox = PAD + panel * (PANEL_W + GAP)
        rows = run.get(metric, {})
        svg.append(
            f'<text x="{ox}" y="{top - 10}" font-size="12" font-weight="600" fill="{INK}">{esc(run_name)}</text>'
        )

        # Gridlines first, so bars paint over them.
        for tick in ticks:
            gx = ox + LABEL_W + plot_w * (tick / axis_max)
            svg.append(
                f'<line x1="{gx:.1f}" y1="{top}" x2="{gx:.1f}" y2="{top + body_h}" stroke="{GRID}" stroke-width="1"/>'
            )
            svg.append(
                f'<text x="{gx:.1f}" y="{top + body_h + 16}" font-size="9" fill="{INK_MUTED}" '
                f'text-anchor="middle">{fmt(tick * 1.0, spec["unit"]) if spec["unit"] == "ops/s" else f"{tick:g}"}</text>'
            )

        for i, group in enumerate(groups):
            band = top + i * ROW_H
            svg.append(
                f'<text x="{ox + LABEL_W - 8}" y="{band + ROW_H / 2 + 4:.1f}" font-size="10.5" '
                f'fill="{INK_MUTED}" text-anchor="end">{esc(group)}</text>'
            )
            # 2px of surface between the paired bars keeps them from reading as
            # one block; the pair sits centred in its band.
            for j, mode in enumerate(("direct", "dapr")):
                value = rows.get(group, {}).get(mode)
                if value is None:
                    continue
                scaled = value * spec["scale"]
                bar_w = max(plot_w * (scaled / axis_max), 1.0)
                by = band + ROW_H / 2 - BAR_H - 1 + j * (BAR_H + 2)
                # rx rounds the data-end; the baseline end is squared off by a
                # small overlay so the bar still grows from a hard zero.
                svg.append(
                    f'<rect x="{ox + LABEL_W}" y="{by:.1f}" width="{bar_w:.1f}" height="{BAR_H}" '
                    f'rx="4" fill="{RGB[mode]}"/>'
                )
                svg.append(
                    f'<rect x="{ox + LABEL_W}" y="{by:.1f}" width="{min(4, bar_w):.1f}" height="{BAR_H}" '
                    f'fill="{RGB[mode]}"/>'
                )
                svg.append(
                    f'<text x="{ox + LABEL_W + bar_w + 5:.1f}" y="{by + BAR_H - 3:.1f}" font-size="9.5" '
                    f'fill="{INK_MUTED}">{fmt(scaled, spec["unit"])}</text>'
                )

        svg.append(
            f'<line x1="{ox + LABEL_W}" y1="{top}" x2="{ox + LABEL_W}" y2="{top + body_h}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )

    svg.append("</svg>")
    with open(out_path, "w") as fh:
        fh.write("\n".join(svg))
    return True


def insights(runs):
    """Prints the comparisons the charts are meant to provoke."""
    print("\n=== Insights ===")
    for metric in METRICS:
        present = {name: run[metric] for name, run in runs.items() if metric in run}
        if not present:
            continue
        print(f"\n{metric}:")
        for run_name, rows in present.items():
            ratios = []
            for group, modes in rows.items():
                if "direct" in modes and "dapr" in modes and modes["direct"]:
                    # For throughput the penalty is direct/dapr (Dapr does less);
                    # for latency it is dapr/direct (Dapr costs more).
                    ratio = (
                        modes["direct"] / modes["dapr"]
                        if metric == "throughput"
                        else modes["dapr"] / modes["direct"]
                    )
                    ratios.append((ratio, group))
            if not ratios:
                continue
            ratios.sort(reverse=True)
            worst, best = ratios[0], ratios[-1]
            word = "less throughput" if metric == "throughput" else "slower"
            print(
                f"  {run_name:<12} Dapr is {best[0]:.1f}x-{worst[0]:.1f}x {word} "
                f"(worst: {worst[1]}, best: {best[1]})"
            )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("files", nargs="+", help="results.sh captures to compare")
    ap.add_argument(
        "-o",
        "--out-dir",
        default="plots",
        help="directory for the SVGs (default: plots)",
    )
    args = ap.parse_args()

    runs = OrderedDict(
        (os.path.splitext(os.path.basename(p))[0], parse(p)) for p in args.files
    )
    empty = [name for name, run in runs.items() if not run]
    if empty:
        sys.exit(f"No recognisable results sections in: {', '.join(empty)}")

    os.makedirs(args.out_dir, exist_ok=True)
    written, missing = [], []
    for metric in METRICS:
        out = os.path.join(args.out_dir, metric.replace(" ", "_") + ".svg")
        if render(metric, runs, out):
            written.append(out)
        else:
            missing.append(metric)

    for path in written:
        print(f"wrote {path}")
    if missing:
        # Said plainly rather than silently skipped: a percentile absent from the
        # capture is absent from the charts.
        print(
            f"\nnot plotted (absent from these captures): {', '.join(missing)}",
            file=sys.stderr,
        )
    insights(runs)


if __name__ == "__main__":
    main()
