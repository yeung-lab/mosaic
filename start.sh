#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/venv"
LOG_FILE="$PROJECT_DIR/app-launch.log"
PID_FILE="$PROJECT_DIR/backend.pid"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

notify() {
  osascript -e "display notification \"$1\" with title \"Mosaic\" subtitle \"$2\"" 2>/dev/null || true
}

error_dialog() {
  osascript -e "display dialog \"$1\n\nSee app-launch.log for details.\" with title \"Mosaic — Launch Failed\" buttons {\"OK\"} default button \"OK\" with icon stop" 2>/dev/null || true
}

log() {
  echo "$1"
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

error_exit() {
  log "ERROR: $1"
  error_dialog "$1"
  exit 1
}

log "Starting Mosaic from $PROJECT_DIR"
notify "Starting up..." "Mosaic"

cd "$PROJECT_DIR" || error_exit "Cannot change to project directory."

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

# ── Node.js ──────────────────────────────────────────────────────────────────
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
    notify "Installing Node.js (first launch only)..." "Setting up"
    log "Installing Node.js via Homebrew"
    brew install node >> "$LOG_FILE" 2>&1 || error_exit "Failed to install Node.js via Homebrew."
    NODE_CMD="$(command -v node || true)"
    NPM_CMD="$(command -v npm || true)"
  fi
fi

if [[ -z "$NODE_CMD" || -z "$NPM_CMD" ]]; then
  error_exit "Node.js is required but could not be found.\n\nInstall it from https://nodejs.org and try again."
fi

# ── ffmpeg ───────────────────────────────────────────────────────────────────
if ! command -v ffmpeg &> /dev/null; then
  if command -v brew &> /dev/null; then
    notify "Installing ffmpeg (first launch only)..." "Setting up"
    log "Installing ffmpeg via Homebrew"
    brew install ffmpeg >> "$LOG_FILE" 2>&1 || error_exit "Failed to install ffmpeg via Homebrew."
  else
    error_exit "ffmpeg is required but could not be found.\n\nInstall Homebrew (https://brew.sh) then run: brew install ffmpeg"
  fi
fi

# ── Python backend ───────────────────────────────────────────────────────────
notify "Setting up Python environment..." "Setting up"
log "Setting up backend virtual environment"
cd "$BACKEND_DIR" || error_exit "Cannot find the backend folder."

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR" >> "$LOG_FILE" 2>&1 || error_exit "Failed to create Python virtual environment.\n\nMake sure Python 3.9+ is installed."
fi

source "$VENV_DIR/bin/activate" || error_exit "Failed to activate Python virtual environment."
pip install --upgrade pip setuptools wheel >> "$LOG_FILE" 2>&1 || error_exit "Failed to upgrade pip."
pip install -r requirements.txt >> "$LOG_FILE" 2>&1 || error_exit "Failed to install Python dependencies."

# ── Frontend build ───────────────────────────────────────────────────────────
notify "Building the app..." "Almost ready"
log "Building frontend"
cd "$FRONTEND_DIR" || error_exit "Cannot find the frontend folder."

if [ ! -d "node_modules" ]; then
  "$NPM_CMD" install >> "$LOG_FILE" 2>&1 || error_exit "Failed to install frontend dependencies (npm install)."
fi

"$NPM_CMD" run build >> "$LOG_FILE" 2>&1 || error_exit "Failed to build the frontend (npm run build)."

# ── Start server ─────────────────────────────────────────────────────────────
log "Starting backend server"
cd "$BACKEND_DIR" || error_exit "Cannot find the backend folder."
nohup "$VENV_DIR/bin/python" main.py >> "$LOG_FILE" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PID_FILE"

sleep 4

APP_URL="http://localhost:8000"
log "Opening browser at $APP_URL"
notify "Opening in your browser now." "Ready!"

if command -v open &> /dev/null; then
  open "$APP_URL"
elif command -v xdg-open &> /dev/null; then
  xdg-open "$APP_URL"
fi

log "Mosaic started successfully (PID $BACKEND_PID)"
exit 0
