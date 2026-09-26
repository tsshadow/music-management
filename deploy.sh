#!/bin/bash
# Proxy script for scripts/deploy.sh
cd "$(dirname "$0")" || exit 1
./scripts/deploy.sh "$@"
