#!/usr/bin/env python3
"""Per-task pre/post counterexample-size figures for the Racket workloads.

Regenerates the paper's shrinking figure -- originally SystemF-only -- for all
four Racket workloads, driven by the artifact's store-<workload>-racket.jsonl
files and the size computation in shrink_analysis.py.

For each workload two figures are emitted in the paper style: ProplangBespoke
(deep shrinking, purple) and RackcheckBespoke (shallow shrinking, green). Each
plots, across the tasks (mutant x property) shared by both strategies in store
order, a solid line for the mean pre-shrink size and a
dashed line for the mean post-shrink size. Both figures of a workload share one
y-axis so the two strategies are directly comparable.
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shrink_analysis import (  # noqa: E402  (path set above)
    DEFAULT_WORKLOADS,
    counterexample_size,
    default_store_path,
    load_store,
    workload_key,
)

# Avoid matplotlib cache warnings in restricted environments (as in the paper script).
if "MPLCONFIGDIR" not in os.environ:
    _cache = Path.home() / ".matplotlib"
    if not _cache.exists() or not os.access(_cache, os.W_OK):
        os.environ["MPLCONFIGDIR"] = "/tmp/mplconfig-proplang-paper"

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

# Strategy -> line colour, matching the paper figure.
STRATEGY_COLORS = {
    "ProplangBespoke": "#470938",
    "RackcheckBespoke": "#436E4F",
}
STRATEGY_SLUG = {"ProplangBespoke": "proplang", "RackcheckBespoke": "rackcheck"}


def build_workload_series(
    store_path: Path,
) -> tuple[list[str], dict[str, dict[str, tuple[float, float]]]]:
    """Mean (pre, post) size per (mutant:property) task, per strategy."""
    grouped: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: {"pre": [], "post": []})
    )
    case_order: list[str] = []
    seen: set[str] = set()

    for row in load_store(store_path):
        strategy = row.get("strategy", "")
        if strategy not in STRATEGY_COLORS:
            continue
        key = workload_key(row)
        pre = counterexample_size(row.get("counterexample"), key)
        post = counterexample_size(row.get("shrinked-counterexample"), key)
        if pre is None or post is None:
            continue  # need both a bug and a shrunk result for this trial

        case_id = f"{','.join(row.get('mutations', []))}:{row.get('property', '')}"
        if case_id not in seen:
            seen.add(case_id)
            case_order.append(case_id)
        grouped[strategy][case_id]["pre"].append(float(pre))
        grouped[strategy][case_id]["post"].append(float(post))

    points: dict[str, dict[str, tuple[float, float]]] = {s: {} for s in STRATEGY_COLORS}
    for strategy, cases in grouped.items():
        for case_id, vals in cases.items():
            if vals["pre"] and vals["post"]:
                points[strategy][case_id] = (
                    statistics.fmean(vals["pre"]),
                    statistics.fmean(vals["post"]),
                )
    return case_order, points


def nice_axis(value_max: float) -> tuple[float, float, float]:
    """Pick (y_max, major_step, minor_step) giving ~6-8 major ticks."""
    if value_max <= 0:
        return 1.0, 1.0, 0.2
    target = value_max / 7.0
    magnitude = 10 ** math.floor(math.log10(target))
    for multiple in (1, 2, 2.5, 5, 10):
        step = multiple * magnitude
        if target <= step:
            break
    y_max = math.ceil(value_max / step) * step
    return y_max, step, step / 5.0


def frange(start: float, stop: float, step: float) -> list[float]:
    out, value = [], start
    while value < stop - 1e-9:
        out.append(value)
        value += step
    return out


def draw_plot(
    series: list[tuple[str, float, float]],
    color: str,
    output_file: Path,
    y_max: float,
    major: float,
    minor: float,
) -> None:
    fig, ax = plt.subplots(figsize=(12, 8), dpi=200)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    n = len(series)
    if n == 0:
        ax.set_axis_off()
        fig.savefig(output_file, format="png", dpi=200, facecolor="white")
        plt.close(fig)
        return

    xs = list(range(n))
    pre = [row[1] for row in series]
    post = [row[2] for row in series]

    ax.plot(xs, pre, color=color, linewidth=4.2, solid_capstyle="round", antialiased=True)
    ax.plot(
        xs,
        post,
        color=color,
        linewidth=3.8,
        linestyle=(0, (5, 3)),
        solid_capstyle="round",
        antialiased=True,
    )

    ax.set_ylim(0, y_max)
    ax.set_xlim(-0.5, 0.5) if n == 1 else ax.set_xlim(0, n - 1)
    ax.margins(x=0)
    ax.set_xticks([])  # no x tick labels, as in the original figure

    ticks = frange(major, y_max, major)
    ax.set_yticks(ticks)
    ax.set_yticklabels(
        [str(int(v)) if float(v).is_integer() else f"{v:g}" for v in ticks], fontsize=22
    )
    ax.yaxis.set_minor_locator(MultipleLocator(minor))

    ax.tick_params(axis="y", which="major", length=16, width=3.0, direction="out", pad=10)
    ax.tick_params(axis="y", which="minor", length=9, width=2.0, direction="out")
    ax.tick_params(axis="x", which="both", length=0)

    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_linewidth(4.0)
        ax.spines[side].set_color("black")

    plt.subplots_adjust(left=0.105, right=0.995, top=0.995, bottom=0.08)
    fig.savefig(output_file, format="png", dpi=200, facecolor="white")
    plt.close(fig)


def regenerate_workload(workload: str, store_path: Path, output_dir: Path) -> list[Path]:
    case_order, points = build_workload_series(store_path)
    proplang = points["ProplangBespoke"]
    rackcheck = points["RackcheckBespoke"]

    # Default task ordering: order of first appearance in the store.
    shared = [c for c in case_order if c in proplang and c in rackcheck]

    # One y-axis for both figures so the strategies are comparable.
    value_max = max(
        (v for c in shared for strat in (proplang, rackcheck) for v in strat[c]),
        default=0.0,
    )
    y_max, major, minor = nice_axis(value_max)

    written = []
    for strategy, pts in (("ProplangBespoke", proplang), ("RackcheckBespoke", rackcheck)):
        series = [(c, *pts[c]) for c in shared]
        out = output_dir / f"scatter_plot_{workload}_{STRATEGY_SLUG[strategy]}.png"
        draw_plot(series, STRATEGY_COLORS[strategy], out, y_max, major, minor)
        written.append(out)
        print(
            f"{workload}/{STRATEGY_SLUG[strategy]}: {len(series)} tasks, "
            f"y_max={y_max:g} -> {out}"
        )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workload",
        action="append",
        choices=DEFAULT_WORKLOADS,
        help="workload(s) to plot; repeatable. Defaults to all four.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "figures" / "shrinking",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for workload in args.workload or DEFAULT_WORKLOADS:
        store_path = default_store_path(workload)
        if not store_path.exists():
            print(f"warning: skipping {workload}, missing {store_path}", file=sys.stderr)
            continue
        regenerate_workload(workload, store_path, output_dir)


if __name__ == "__main__":
    main()
