#!/bin/bash
set -e

cd "$(dirname "$0")"

./build.sh
./publish.sh
./deploy.sh

echo "Build, publish and deploy completed successfully!"
