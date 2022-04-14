#!/bin/bash
set -ue -o pipefail

rm -rf build
hugo -d build -b https://ellingtonia.github.io/ellingtonia/
pushd build

# echo "charliedyson.net" > CNAME

git init .
git remote add origin git@github.com:ellingtonia/ellingtonia.git
git add .
git commit -a -m "Update"
git push --force origin HEAD:gh-pages
