#!/usr/bin/env bash
# Run the Racket experiments sequentially across workloads.
# Stops on first failure.
set -euo pipefail

# Run one experiment.
#   $1 = test name, matching tests/<name>.json
#
# Store filename: store-<workload-short>.jsonl
#   e.g. bst-racket          -> store-bst-racket.jsonl
#        rbt-proplang-racket -> store-rbt-proplang-racket.jsonl
run() {
  local test=$1
  local store="store-${test}.jsonl"

  echo "=== test=${test} -> ${store} ==="
  ETNA_LOG=debug etna experiment run \
    --tests "${test}" \
    --store "${store}" \
    --short-circuit

   ETNA_LOG=debug etna experiment visualize \
    --figure "${test}" \
    --tests "${test}" \
    --visualization-type bucket \
    --store "${store}"
}

run stlc-racket
run bst-racket
run rbt-racket
# run systemf-racket

echo "=== all runs complete ==="
