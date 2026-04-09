#!/usr/bin/env bash
# Schedule Forensics Local Tool — launcher (Linux / macOS)
set -e

echo "Starting Schedule Forensics Local Tool..."
echo

echo "Checking dependencies..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: Python 3 not found. Install Python 3.12+ and re-run." >&2
  exit 1
fi
if ! command -v java >/dev/null 2>&1; then
  echo "ERROR: Java not found. Install OpenJDK 11+ and re-run." >&2
  exit 1
fi
echo

echo "Installing Python dependencies..."
python3 -m pip install -r requirements.txt --quiet
echo

echo "Starting web server on http://localhost:5000"
echo "Press Ctrl+C to stop"
echo
exec python3 -m app.main
