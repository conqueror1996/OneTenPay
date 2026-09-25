#!/bin/bash
# ============================================
# GHOST MODE DASHBOARD — 24/7 SUPERVISOR
# Auto-restarts dashboard + ngrok if they die
# ============================================

DIR="/Users/urbanclay/Desktop/7mojo_dual_hedge_final"
LOG="$DIR/supervisor.log"
DASH_PID=""
NGROK_PID=""

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

cleanup() {
    log "⛔ Shutting down..."
    [ -n "$DASH_PID" ] && kill $DASH_PID 2>/dev/null
    [ -n "$NGROK_PID" ] && kill $NGROK_PID 2>/dev/null
    pkill -f "oneten_dashboard.py" 2>/dev/null
    pkill -f "ngrok http 9090" 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

start_dashboard() {
    pkill -f "oneten_dashboard.py" 2>/dev/null
    sleep 1
    cd "$DIR" && python3 oneten_dashboard.py >> "$DIR/dashboard.log" 2>&1 &
    DASH_PID=$!
    log "✅ Dashboard started (PID: $DASH_PID)"
}

start_ngrok() {
    pkill -f "ngrok http 9090" 2>/dev/null
    sleep 1
    ngrok http 9090 --log=stdout > "$DIR/ngrok.log" 2>&1 &
    NGROK_PID=$!
    sleep 5
    
    # Get the public URL
    URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])" 2>/dev/null)
    if [ -n "$URL" ]; then
        log "🌐 Ngrok live: $URL"
        echo "$URL" > "$DIR/.ngrok_url"
    else
        log "⚠ Ngrok started but no URL yet"
    fi
}

get_ngrok_url() {
    curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'])" 2>/dev/null
}

# === INITIAL START ===
log "=========================================="
log "🚀 Starting 24/7 Supervisor"
log "=========================================="

start_dashboard
sleep 2
start_ngrok

# === WATCHDOG LOOP — checks every 30 seconds ===
while true; do
    sleep 30
    
    # Check dashboard
    if ! curl -s -o /dev/null -w '' http://localhost:9090 2>/dev/null; then
        log "💀 Dashboard is DOWN — restarting..."
        start_dashboard
        sleep 3
    fi
    
    # Check ngrok
    URL=$(get_ngrok_url)
    if [ -z "$URL" ]; then
        log "💀 Ngrok is DOWN — restarting..."
        start_ngrok
    fi
done
