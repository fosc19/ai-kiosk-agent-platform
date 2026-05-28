#!/bin/bash
# AI Kiosk - Run All Services Locally (no Docker)
#
# Usage: ./scripts/run_all_local.sh
#        ./scripts/run_all_local.sh --stop
#        ./scripts/run_all_local.sh --status
#
# Services:
#   - MCP Tools (9002) - Database/tools
#   - Orchestrator (8765) - Main agent
#   - Speech (9001) - VAD/ASR/TTS
#   - Vision (9003) - Face detection
#
# Logs: data/logs/*.log

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/data/logs"
PID_DIR="$PROJECT_DIR/data/pids"

# Create directories
mkdir -p "$LOG_DIR" "$PID_DIR" "$PROJECT_DIR/data"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check service health
check_health() {
    local port=$1
    curl -sf "http://localhost:$port/healthz" >/dev/null 2>&1
}

# Function to show status of all services
show_status() {
    echo ""
    echo -e "${BLUE}=== Estado de Servicios ===${NC}"
    echo ""

    local services=("MCP-Tools:9002" "Orchestrator:8765" "Speech:9001" "Vision:9003")

    for service_info in "${services[@]}"; do
        local name="${service_info%%:*}"
        local port="${service_info##*:}"

        if check_health "$port"; then
            echo -e "  ${GREEN}✓${NC} $name (puerto $port)"
        else
            echo -e "  ${RED}✗${NC} $name (puerto $port)"
        fi
    done
    echo ""
    exit 0
}

# Function to stop all services
stop_services() {
    log_info "Stopping all services..."

    # Stop by PID files
    for pid_file in "$PID_DIR"/*.pid; do
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            service_name=$(basename "$pid_file" .pid)
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                log_info "Stopped $service_name (PID: $pid)"
            fi
            rm -f "$pid_file"
        fi
    done

    # Also kill by port (in case PIDs are stale)
    for port in 9001 9002 9003 8765; do
        local pid=$(lsof -t -i :"$port" 2>/dev/null || true)
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null || true
        fi
    done

    log_info "All services stopped"
    exit 0
}

# Function to check if a port is in use
port_in_use() {
    lsof -i :"$1" >/dev/null 2>&1
}

# Function to wait for service to be ready
wait_for_service() {
    local name=$1
    local port=$2
    local max_wait=${3:-30}

    echo -n "  Waiting for $name (port $port)..."
    for i in $(seq 1 $max_wait); do
        if check_health "$port"; then
            echo -e " ${GREEN}OK${NC}"
            return 0
        fi
        sleep 1
        echo -n "."
    done
    echo -e " ${RED}TIMEOUT${NC}"
    return 1
}

# Function to ensure venv exists
ensure_venv() {
    local dir=$1
    local venv_path="$PROJECT_DIR/$dir/.venv"

    if [ ! -f "$venv_path/bin/python" ]; then
        log_info "Creating venv for $dir..."
        python3 -m venv "$venv_path"

        # Install dependencies
        log_info "Installing dependencies for $dir..."
        "$venv_path/bin/pip" install --quiet -e "$PROJECT_DIR/$dir" 2>/dev/null || \
        "$venv_path/bin/pip" install --quiet -r "$PROJECT_DIR/$dir/requirements.txt" 2>/dev/null || \
        log_warn "Could not auto-install deps for $dir"
    fi
}

# Function to start a service using venv
start_service() {
    local name=$1
    local dir=$2
    local module=$3
    local port=$4

    log_info "Starting $name..."

    if port_in_use "$port"; then
        if check_health "$port"; then
            log_warn "$name: Already running on port $port"
            return 0
        else
            log_warn "$name: Port $port in use, killing..."
            kill $(lsof -t -i :"$port") 2>/dev/null || true
            sleep 1
        fi
    fi

    local venv_python="$PROJECT_DIR/$dir/.venv/bin/python"

    if [ ! -f "$venv_python" ]; then
        log_error "$name: venv not found at $dir/.venv"
        log_error "  Run: cd $PROJECT_DIR/$dir && python3 -m venv .venv && .venv/bin/pip install -e ."
        return 1
    fi

    cd "$PROJECT_DIR/$dir"

    # Run in background, redirect output to log file
    nohup "$venv_python" $module > "$LOG_DIR/$name.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_DIR/$name.pid"

    log_info "$name started (PID: $pid, Port: $port)"
    log_info "  Log: $LOG_DIR/$name.log"

    cd "$PROJECT_DIR"
}

# Handle flags
case "$1" in
    --stop)
        stop_services
        ;;
    --status)
        show_status
        ;;
esac

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   AI Kiosk - Local Development Services   ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ============================================
# Start Services (order matters)
# ============================================

# 1. MCP Tools (required) - HTTP mode for REST API
export MCP_TRANSPORT=http
start_service "mcp-tools" "services/mcp-tools" "-m mcp_tools.main" 9002
sleep 3

# 2. Vision (face detection)
start_service "vision" "services/vision" "main.py" 9003
sleep 2

# 3. Speech (VAD/ASR/TTS)
start_service "speech" "services/speech" "main.py" 9001
sleep 3

# 4. Orchestrator (main agent - last because it connects to others)
start_service "orchestrator" "services/orchestrator" "main.py" 8765
sleep 2

echo ""
log_info "Waiting for services to be ready..."
echo ""

# Wait for all services
wait_for_service "mcp-tools" 9002 30
wait_for_service "vision" 9003 30
wait_for_service "speech" 9001 60  # Speech takes longer (downloads models)
wait_for_service "orchestrator" 8765 30

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   All services running!                ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Services:"
echo "  - MCP Tools:     http://localhost:9002"
echo "  - Vision:        http://localhost:9003"
echo "  - Speech:        http://localhost:9001"
echo "  - Orchestrator:  http://localhost:8765"
echo ""
echo "Logs:"
echo "  tail -f $LOG_DIR/*.log"
echo ""
echo "Commands:"
echo "  ./scripts/run_all_local.sh --status  # Check status"
echo "  ./scripts/run_all_local.sh --stop    # Stop all"
echo ""
echo "To start the UI:"
echo "  task dev:ui"
echo ""
