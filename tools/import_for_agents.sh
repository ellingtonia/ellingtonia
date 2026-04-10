#!/bin/bash
set -ue -o pipefail
set -x

if [[ $# -ne 3 ]]; then
    echo "Usage: $0 YEAR BASE_JSON MODIFIED_JSON"
    echo "Example: $0 1926 /tmp/1926.orig.json /tmp/1926.edited.json"
    exit 1
fi

year=$1
base_json=$2
modified_json=$3

target_json="data/discog/${year}.json"

if [[ ! -f "$base_json" ]]; then
    echo "Base JSON file not found: $base_json"
    exit 1
fi

if [[ ! -f "$modified_json" ]]; then
    echo "Modified JSON file not found: $modified_json"
    exit 1
fi

if [[ ! -f "$target_json" ]]; then
    echo "Target repository JSON file not found: $target_json"
    exit 1
fi

{ diff -U5 "$base_json" "$modified_json" || true; } | patch "$target_json"

./tools/database.py normalise
