#!/usr/bin/env bash
# Run the Rocq experiments sequentially across workloads.
# Stops on first failure.
set -euo pipefail

# Run one experiment.
#   $1 = test name, matching tests/<name>.json
#
# Store filename: store-<workload-short>.jsonl
#   e.g. bst-rocq          -> store-bst.jsonl
#        rbt-proplang-rocq -> store-rbt-proplang.jsonl
run() {
  local test=$1
  local workload="${test%-rocq}"
  local store="store-${workload}.jsonl"

  echo "=== test=${test} -> ${store} ==="
  ETNA_LOG=debug etna experiment run \
    --tests "${test}" \
    --store "${store}" \
    --short-circuit
}


run bst-rocq
run bst-proplang-rocq

run rbt-rocq
run rbt-proplang-rocq

run stlc-rocq
run stlc-proplang-rocq

echo "=== all runs complete ==="
