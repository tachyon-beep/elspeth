#!/usr/bin/env bash
#
# Restart Elspeth web servers (backend + frontend)
#
# Usage:
#   ./scripts/restart-web.sh           # Restart both
#   ./scripts/restart-web.sh backend   # Restart backend only
#   ./scripts/restart-web.sh frontend  # Restart frontend only
#   ./scripts/restart-web.sh --include-composer  # Also restart composer MCP servers
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/src/elspeth/web/frontend"

# Ports
BACKEND_PORT=8451
FRONTEND_PORT=5173

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

kill_by_port() {
    local port=$1
    local name=$2
    local pids
    pids=$(lsof -ti ":$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        log_info "Stopping $name (port $port, PIDs: $pids)"
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 1
    else
        log_info "No $name running on port $port"
    fi
}

kill_composer() {
    local pids
    pids=$(pgrep -f "elspeth-composer" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        log_warn "Stopping elspeth-composer (PIDs: $pids)"
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 1
    else
        log_info "No elspeth-composer processes running"
    fi
}

start_backend() {
    log_info "Starting backend on http://127.0.0.1:$BACKEND_PORT"
    cd "$PROJECT_ROOT"
    source .venv/bin/activate
    uvicorn elspeth.web.app:create_app \
        --factory \
        --host 127.0.0.1 \
        --port "$BACKEND_PORT" \
        --reload &
    disown
}

start_frontend() {
    log_info "Starting frontend on http://localhost:$FRONTEND_PORT"
    cd "$FRONTEND_DIR"
    npm run dev &
    disown
}

restart_backend() {
    kill_by_port "$BACKEND_PORT" "backend"
    start_backend
}

restart_frontend() {
    kill_by_port "$FRONTEND_PORT" "frontend"
    start_frontend
}

# Parse arguments
INCLUDE_COMPOSER=false
TARGET="all"

for arg in "$@"; do
    case $arg in
        --include-composer)
            INCLUDE_COMPOSER=true
            ;;
        backend|frontend)
            TARGET="$arg"
            ;;
        -h|--help)
            echo "Usage: $0 [backend|frontend] [--include-composer]"
            echo ""
            echo "Options:"
            echo "  backend           Restart only the backend (uvicorn)"
            echo "  frontend          Restart only the frontend (vite)"
            echo "  --include-composer  Also restart elspeth-composer MCP servers"
            echo ""
            echo "Without arguments, restarts both backend and frontend."
            exit 0
            ;;
        *)
            log_error "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

# Execute
case $TARGET in
    backend)
        restart_backend
        ;;
    frontend)
        restart_frontend
        ;;
    all)
        restart_backend
        restart_frontend
        ;;
esac

if [[ "$INCLUDE_COMPOSER" == "true" ]]; then
    kill_composer
    log_warn "Composer processes killed. They will restart automatically when Claude Code reconnects."
fi

log_info "Done. Servers starting in background."
echo ""
echo "  Backend:  http://127.0.0.1:$BACKEND_PORT"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
