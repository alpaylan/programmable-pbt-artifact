#!/usr/bin/env python3
"""Compute counterexample sizes from ETNA JSONL stores for the Racket workloads.

Handles all four Racket workloads (bst, rbt, stlc, systemf). They print
counterexamples in different styles -- labelled `t: (...)` versus
`#hash((t . ...))`, s-expression trees versus Racket struct terms like
`#(struct:just #<App: ...>)`. Rather than parse each style, we measure size by
counting the structural constructors that each workload's own `size` function
counts. Those constructor names never collide with type constructors or scalar
arguments, so the count equals the canonical size exactly (verified against the
workloads' `size-STLC` / `size` definitions):

  bst, rbt : number of `T` tree nodes
  stlc     : Abs + App + leaves (Var/Bool)     -- cf. stlc-racket    size-STLC
  systemf  : App + Abs + TAbs + TApp + Var     -- cf. systemf-racket size

With no --store the four default stores (store-<workload>-racket.jsonl) are read.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_WORKLOADS = ("bst", "rbt", "stlc", "systemf")

# Term/tree constructors counted per workload. Type constructors (TBool, TFun,
# Top, Arr, All, TVar) and scalar arguments (k, v, ...) are intentionally
# excluded, mirroring each workload's `size` function.
SEXP_CONSTRUCTORS = {
    "bst": ("T",),
    "rbt": ("T",),
    "stlc": ("Abs", "App", "Var", "Bool"),
}
STRUCT_CONSTRUCTORS = {
    "systemf": ("App", "Abs", "TAbs", "TApp", "Var"),
}


def _sexp_counter(names: Iterable[str]) -> list[re.Pattern]:
    # An s-expression node head: `(NAME` followed by a space or close paren.
    return [re.compile(r"\(" + name + r"(?=[\s)])") for name in names]


def _struct_counter(names: Iterable[str]) -> list[re.Pattern]:
    # Racket struct printing: `#<NAME: ...>`. The `<` before NAME keeps `#<App:`
    # from matching inside `#<TApp:` (and likewise `#<Abs:`/`#<Var:`).
    return [re.compile(r"#<" + name + r":") for name in names]


COUNTERS: dict[str, list[re.Pattern]] = {
    **{wl: _sexp_counter(names) for wl, names in SEXP_CONSTRUCTORS.items()},
    **{wl: _struct_counter(names) for wl, names in STRUCT_CONSTRUCTORS.items()},
}


def workload_key(record: dict[str, Any]) -> str:
    # The `workload` field looks like "bst-racket"; key on the leading name.
    return str(record.get("workload", "")).split("-")[0]


def default_store_path(workload: str) -> Path:
    return Path(__file__).resolve().parents[1] / f"store-{workload}-racket.jsonl"


def counterexample_size(counterexample: Any, key: str) -> int | None:
    if not counterexample or counterexample in ("-", "#f"):
        return None
    patterns = COUNTERS.get(key)
    if patterns is None:
        return None
    text = str(counterexample)
    return sum(len(pattern.findall(text)) for pattern in patterns)


def load_store(path: Path) -> Iterable[dict[str, Any]]:
    with path.open() as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            yield row.get("data", row)


def enrich_record(row: dict[str, Any]) -> dict[str, Any]:
    key = workload_key(row)
    size = counterexample_size(row.get("counterexample"), key)
    shrinked_size = counterexample_size(row.get("shrinked-counterexample"), key)
    return {
        "workload": row.get("workload", ""),
        "strategy": row.get("strategy", ""),
        "property": row.get("property", ""),
        "mutations": ",".join(row.get("mutations", [])),
        "trial": row.get("trial", ""),
        "foundbug": row.get("foundbug", False),
        "passed": row.get("passed", ""),
        "search-time": row.get("search-time", ""),
        "size": "" if size is None else size,
        "shrinked-size": "" if shrinked_size is None else shrinked_size,
        "counterexample": row.get("counterexample", ""),
        "shrinked-counterexample": row.get("shrinked-counterexample", ""),
    }


def mean(values: list[int]) -> str:
    return f"{statistics.mean(values):.2f}" if values else "-"


def print_summary(records: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(record["workload"], record["strategy"])].append(record)

    print("workload,strategy,records,with-size,mean-size,with-shrink,mean-shrinked-size")
    for (workload, strategy), group in sorted(groups.items()):
        sizes = [record["size"] for record in group if record["size"] != ""]
        shrinked = [
            record["shrinked-size"] for record in group if record["shrinked-size"] != ""
        ]
        print(
            f"{workload},{strategy},{len(group)},{len(sizes)},{mean(sizes)},"
            f"{len(shrinked)},{mean(shrinked)}"
        )


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "workload",
        "strategy",
        "property",
        "mutations",
        "trial",
        "foundbug",
        "passed",
        "search-time",
        "size",
        "shrinked-size",
        "counterexample",
        "shrinked-counterexample",
    ]
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def resolve_stores(explicit: list[Path] | None) -> list[Path]:
    if explicit:
        for path in explicit:
            if not path.exists():
                raise SystemExit(f"store not found: {path}")
        return explicit
    stores = []
    for workload in DEFAULT_WORKLOADS:
        path = default_store_path(workload)
        if path.exists():
            stores.append(path)
        else:
            print(f"warning: skipping missing default store {path}", file=sys.stderr)
    return stores


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        action="append",
        help="store JSONL to read; repeatable. Defaults to all four "
        "store-<workload>-racket.jsonl files next to the repo root.",
    )
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()

    records: list[dict[str, Any]] = []
    for path in resolve_stores(args.store):
        records.extend(enrich_record(row) for row in load_store(path))
    print_summary(records)
    if args.csv:
        write_csv(args.csv, records)


if __name__ == "__main__":
    main()
