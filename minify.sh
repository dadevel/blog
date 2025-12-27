#!/usr/bin/env bash
set -eu
shopt -s globstar

GOPATH="${GOPATH:-$HOME/go}"
if [[ ! -f "$GOPATH/bin/minify" ]]; then
    go install github.com/tdewolff/minify/v2/cmd/minify@latest
fi
for path in ./public/**/*.{css,html,svg}; do
    if [[ -f "$path" ]]; then
        "$GOPATH/bin/minify" --html-keep-document-tags --html-keep-end-tags --html-keep-whitespace --output "$path" "$path"
    fi
done
