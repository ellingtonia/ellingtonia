#!/bin/bash
set -ue -o pipefail

build_dir=build_tmp
rm -rf $build_dir
# Trailing slash is important
hugo -d $build_dir -b http://ellingtonia.com/
pushd $build_dir

lftp -c "open -u ellingtonia ellingtonia.com; mirror --reverse --delete"
