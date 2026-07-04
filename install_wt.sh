#!/bin/bash
# Installation script for Wt4
# This script clones, builds, and installs Wt4 from source.

set -e

echo "--- Installing Wt4 ---"

# Dependencies for Wt (based on standard requirements for Debian)
# Note: This is an estimation of needed packages for building Wt
sudo apt-get install -y cmake g++ libboost-all-dev libssl-dev zlib1g-dev

# Clone Wt
if [ ! -d "../wt" ]; then
    git clone https://github.com/emweb/wt.git ../wt
fi

cd ../wt

# Create build directory for Wt
mkdir -p build
cd build

# Configure, build, and install Wt
# We install to /usr/local
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local
make -j$(nproc)
sudo make install

# Update linker cache
sudo ldconfig

echo "--- Wt4 installed successfully ---"
