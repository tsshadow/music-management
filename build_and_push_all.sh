#!/bin/bash
set -e

./build.sh
./publish.sh
./deploy.sh

echo "Build, publish and deploy completed successfully!"
