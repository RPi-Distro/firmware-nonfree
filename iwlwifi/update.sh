#!/bin/sh

version="$1"
url="$2"

mkdir update
curl -o update/ucode.tgz "$url"

tar -C update -xzf update/ucode.tgz
file="$(tar -tzf update/ucode.tgz | grep -e "\.ucode$")"
file_real="${file#*/}"
mv update/"$file" "$file_real"-"$version"

rm update -rf
