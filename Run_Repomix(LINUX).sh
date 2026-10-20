#!/usr/bin/env bash

# Change to the directory where this script is located
cd "$(dirname "$0")"

echo "========================================================"
echo "  Running Repomix on Auger Codebase"
echo "========================================================"
echo ""

if command -v repomix &> /dev/null; then
    RUNNER="repomix"
elif command -v npx &> /dev/null; then
    RUNNER="npx --yes repomix"
else
    echo "[ERROR] Neither 'repomix' nor 'npx' (Node.js) was found on PATH."
    echo ""
    echo "To run Repomix, please install Node.js (v18+ recommended):"
    echo "  Debian/Ubuntu: sudo apt-get install -y nodejs npm"
    echo "  Fedora:        sudo dnf install -y nodejs npm"
    echo "  Arch Linux:    sudo pacman -S nodejs npm"
    echo "  Or visit:      https://nodejs.org/"
    echo ""
    exit 1
fi

echo "Executing: $RUNNER $*"
echo ""

$RUNNER "$@"
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "========================================================"
    echo "  Repomix completed successfully!"
    echo "========================================================"
else
    echo "========================================================"
    echo "  [ERROR] Repomix failed with exit code $EXIT_CODE."
    echo "========================================================"
fi

exit $EXIT_CODE
