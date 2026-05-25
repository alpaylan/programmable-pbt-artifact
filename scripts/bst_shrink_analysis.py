#!/usr/bin/env python3
"""Compute BST counterexample sizes from an ETNA JSONL store.

This is the BST-specific version of the old shrinking analysis: it measures a
counterexample by summing the node counts of tree-valued arguments. It expects
the current sexp tree printer, e.g. `(E)` and `(T (E) 1 2 (E))`.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


TREE_ARG_RE = re.compile(r"(?:^|,\s*)(t[0-9]*):\s*")


def default_store_path() -> Path:
    return Path(__file__).resolve().parents[1] / "store-bst-racket.jsonl"


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    token = []
    for char in text:
        if char in "()":
            if token:
                tokens.append("".join(token))
                token = []
            tokens.append(char)
        elif char.isspace():
            if token:
                tokens.append("".join(token))
                token = []
        else:
            token.append(char)
    if token:
        tokens.append("".join(token))
    return tokens


def parse_one(tokens: list[str], index: int = 0) -> tuple[Any, int]:
    if tokens[index] != "(":
        return tokens[index], index + 1

    index += 1
    result = []
    while index < len(tokens) and tokens[index] != ")":
        value, index = parse_one(tokens, index)
        result.append(value)
    if index >= len(tokens):
        raise ValueError("unterminated sexp")
    return result, index + 1


def parse_sexp(text: str) -> Any:
    tokens = tokenize(text)
    if not tokens:
        return None
    value, index = parse_one(tokens)
    if index != len(tokens):
        raise ValueError(f"trailing tokens: {tokens[index:]}")
    return value


def tree_size(value: Any) -> int:
    if value in ("E", "(E)"):
        return 0
    if not isinstance(value, list):
        return 0
    if len(value) == 1:
        return tree_size(value[0])
    if value and value[0] == "E":
        return 0
    if len(value) >= 5 and value[0] == "T":
        return 1 + tree_size(value[1]) + tree_size(value[4])
    return 0


def find_balanced(text: str, start: int) -> tuple[str, int]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "(":
        end = text.find(",", start)
        if end == -1:
            end = len(text)
        return text[start:end].strip(), end

    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1], index + 1
    raise ValueError("unterminated counterexample value")


def labelled_tree_values(counterexample: str) -> Iterable[str]:
    for match in TREE_ARG_RE.finditer(counterexample):
        value, _ = find_balanced(counterexample, match.end())
        yield value


def hash_tree_values(counterexample: str) -> Iterable[str]:
    for name in ("t", "t1", "t2", "t3"):
        marker = f"({name} . "
        start = counterexample.find(marker)
        if start == -1:
            continue
        value, _ = find_balanced(counterexample, start + len(marker))
        yield value


def counterexample_size(counterexample: Any) -> int | None:
    if not counterexample or counterexample in ("-", "#f"):
        return None

    text = str(counterexample)
    values = (
        hash_tree_values(text)
        if text.startswith("#hash")
        else labelled_tree_values(text)
    )

    total = 0
    found_tree = False
    for value in values:
        parsed = parse_sexp(value)
        total += tree_size(parsed)
        found_tree = True
    return total if found_tree else None


def load_store(path: Path) -> Iterable[dict[str, Any]]:
    with path.open() as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            yield row.get("data", row)


def enrich_record(row: dict[str, Any]) -> dict[str, Any]:
    size = counterexample_size(row.get("counterexample"))
    shrinked_size = counterexample_size(row.get("shrinked-counterexample"))
    return {
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
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[record["strategy"]].append(record)

    print("strategy,records,with-size,mean-size,with-shrink,mean-shrinked-size")
    for strategy, group in sorted(groups.items()):
        sizes = [record["size"] for record in group if record["size"] != ""]
        shrinked = [
            record["shrinked-size"] for record in group if record["shrinked-size"] != ""
        ]
        print(
            f"{strategy},{len(group)},{len(sizes)},{mean(sizes)},"
            f"{len(shrinked)},{mean(shrinked)}"
        )


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, default=default_store_path())
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()

    records = [enrich_record(row) for row in load_store(args.store)]
    print_summary(records)
    if args.csv:
        write_csv(args.csv, records)


if __name__ == "__main__":
    main()
