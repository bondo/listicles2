#!/usr/bin/env bash
# Points git at the committed hooks. Safe to run repeatedly.
cd "$(dirname "$0")/.." || exit 1
git config core.hooksPath .githooks
chmod +x .githooks/* scripts/*.sh
echo "git hooks installed (core.hooksPath=.githooks)"
