#!/bin/bash

# Start script for Surgical Video De-identification App

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/venv"
LOG_FILE="$PROJECT_DIR/app-launch.log"
PID_FILE="$PROJECT_DIR/backend.pid"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

log() {
  echo "$1"
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

error_exit() {
  echo "ERROR: $1"
  echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1" >> "$LOG_FILE"
  exit 1
}

log "Starting Surgical Video De-identification App from $PROJECT_DIR"

cd "$PROJECT_DIR" || error_exit "Cannot change to project directory"

cleanup_existing_backend() {
  if [ -f "$PID_FILE" ]; then
    EXISTING_PID="$(cat "$PID_FILE")"
    if kill -0 "$EXISTING_PID" >/dev/null 2>&1; then
      log "Stopping existing backend process $EXISTING_PID"
      kill "$EXISTING_PID" >/dev/null 2>&1 || true
      sleep 1
    fi
    rm -f "$PID_FILE"
  fi

  if command -v lsof >/dev/null 2>&1; then
    for PORT_PID in $(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true); do
      if [ -n "$PORT_PID" ]; then
        if ps -p "$PORT_PID" -o comm= 2>/dev/null | grep -E 'Python|uvicorn' >/dev/null 2>&1; then
          log "Stopping existing process $PORT_PID listening on port 8000"
          kill "$PORT_PID" >/dev/null 2>&1 || true
          sleep 1
        fi
      fi
    done
  fi
}

cleanup_existing_backend

NODE_CMD="$(command -v node || true)"
NPM_CMD="$(command -v npm || true)"
if [[ -z "$NODE_CMD" || -z "$NPM_CMD" ]]; then
  if [[ -x "/opt/homebrew/bin/node" && -x "/opt/homebrew/bin/npm" ]]; then
    export PATH="/opt/homebrew/bin:$PATH"
    NODE_CMD="/opt/homebrew/bin/node"
    NPM_CMD="/opt/homebrew/bin/npm"
  elif [[ -x "/usr/local/bin/node" && -x "/usr/local/bin/npm" ]]; then
    export PATH="/usr/local/bin:$PATH"
    NODE_CMD="/usr/local/bin/node"
    NPM_CMD="/usr/local/bin/npm"
  elif command -v brew &> /dev/null; then
    log "Installing Node.js via Homebrew"
    brew install node >> "$LOG_FILE" 2>&1 || error_exit "Homebrew install node failed"
    NODE_CMD="$(command -v node || true)"
    NPM_CMD="$(command -v npm || true)"
  fi
fi

if [[ -z "$NODE_CMD" || -z "$NPM_CMD" ]]; then
  error_exit "Node.js and npm are required but not available. Please install Homebrew and Node.js."
fi

if ! command -v ffmpeg &> /dev/null; then
  if command -v brew &> /dev/null; then
    log "Installing ffmpeg via Homebrew"
    brew install ffmpeg >> "$LOG_FILE" 2>&1 || error_exit "Homebrew install ffmpeg failed"
  else
    error_exit "ffmpeg is required but not available. Please install Homebrew and ffmpeg."
  fi
fi

log "Setting up backend virtual environment"
cd "$BACKEND_DIR" || error_exit "Cannot change to backend directory"
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR" >> "$LOG_FILE" 2>&1 || error_exit "Failed to create Python venv"
fi

source "$VENV_DIR/bin/activate" || error_exit "Failed to activate Python venv"
pip install --upgrade pip setuptools wheel >> "$LOG_FILE" 2>&1 || error_exit "Failed to upgrade pip/setuptools/wheel"
pip install -r requirements.txt >> "$LOG_FILE" 2>&1 || error_exit "Failed to install Python dependencies"

log "Building frontend"
cd "$FRONTEND_DIR" || error_exit "Cannot change to frontend directory"
if [ ! -d "node_modules" ]; then
  "$NPM_CMD" install >> "$LOG_FILE" 2>&1 || error_exit "npm install failed"
fi

"$NPM_CMD" run build >> "$LOG_FILE" 2>&1 || error_exit "npm run build failed"

log "Starting backend server"
cd "$BACKEND_DIR" || error_exit "Cannot change to backend directory"
nohup "$VENV_DIR/bin/python" main.py >> "$LOG_FILE" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PID_FILE"

sleep 4

APP_URL="http://localhost:8000"
log "Opening browser at $APP_URL"
if command -v open &> /dev/null; then
  open "$APP_URL"
elif command -v xdg-open &> /dev/null; then
  xdg-open "$APP_URL"
fi

log "Application started successfully"
echo "Application started. Open $APP_URL in your browser if it did not open automatically."
exit 0