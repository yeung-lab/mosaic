#!/bin/bash

# Stop script for Surgical Video De-identification App

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$PROJECT_DIR/backend.pid"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill "$PID" &> /dev/null; then
    echo "Stopped backend process $PID"
  else
    echo "Backend process $PID not running"
  fi
  rm -f "$PID_FILE"
else
  echo "No backend PID file found"
fi

pkill -f "uvicorn" || true
pkill -f "python main.py" || true

echo "App stopped."