#!/usr/bin/env bash
# Quick launch script for QGreenFleet Streamlit Platform
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "================================================================"
echo "🚢 Launching QGreenFleet Decision Support Platform (SIH #26138)"
echo "================================================================"
python3 -m streamlit run ui/app.py
