#!/bin/bash
# Proxy script for scripts/deploy.sh
cd "$(dirname "$0")"
./scripts/deploy.sh "$@"
