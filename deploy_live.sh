#!/bin/bash
set -ue -o pipefail

rm -rf build
# Trailing slash is important
hugo -d build -b http://ellingtonia.com/
pushd build

lftp -c "open -u ellingtonia ellingtonia.com; mirror --reverse --delete"
