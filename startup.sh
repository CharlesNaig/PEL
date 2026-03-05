#!/bin/bash
# ============================================================
# PEL Startup Script — Panic Button Emergency Locator
# ============================================================
# Launched by systemd (pel.service) on boot.
# Activates the Python virtual environment and runs main.py.
# ============================================================

# Project directory
PEL_DIR="/home/charles/PEL"
VENV_DIR="$PEL_DIR/.venv"
MAIN_SCRIPT="$PEL_DIR/main/main.py"

# Wait for USB devices to settle (A7670E needs a moment after boot)
sleep 5

# Activate virtual environment
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "[PEL] WARNING: Virtual environment not found at $VENV_DIR"
    echo "[PEL] Running with system Python3..."
fi

# Change to main/ directory (so logs.txt is written there)
cd "$PEL_DIR/main"

# Run main.py
echo "[PEL] Starting Panic Button Emergency Locator..."
exec python3 "$MAIN_SCRIPT"
