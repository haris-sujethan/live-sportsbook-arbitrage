#!/bin/bash
# launch_mac.sh — Launch the Arb Overlay on macOS.
#
# Run once to install dependencies, then launches the overlay.
# The overlay handles Chrome launching automatically.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Install dependencies if not already installed
pip3 install -q -r requirements.txt

# Run the overlay
python3 main.py
