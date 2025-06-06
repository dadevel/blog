#!/usr/bin/env bash
set -eu
shopt -s globstar

which minify &> /dev/null || go install github.com/tdewolff/minify/v2/cmd/minify@latest

for path in ./public/**/*.{css,html,svg}; do
    if [[ -f "$path" ]]; then
        ~/go/bin/minify --html-keep-document-tags --html-keep-end-tags --html-keep-whitespace --output "$path" "$path"
    fi
done
