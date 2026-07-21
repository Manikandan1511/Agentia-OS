#!/bin/bash
# ============================================================
#  agentia.sh — GX10 Model Manager v3.0
#  Global JSON-driven model orchestration for Hermes
# ============================================================
#
#  CONFIG: ~/.gx10/agentia.json  (single source of truth)
#  SCRIPT: ~/.gx10/agentia-model-manager.py
#
#  USAGE:
#    agentia.sh status              — Show ALL running models
#    agentia.sh start-all           — Start all always-on models
#    agentia.sh stop-all            — Stop all running models
#    agentia.sh start <name>        — Start by name or port
#    agentia.sh stop <name>         — Stop by name or port
#    agentia.sh toggle <name>       — Toggle on/off
#    agentia.sh logs <name>         — Show last 20 log lines
#    agentia.sh watchdog            — Auto-restart any crashed always-on models
#    agentia.sh boot-setup          — Install systemd + crontab for auto-restart
#
#  EXAMPLES:
#    agentia.sh status              — shows running models only
#    agentia.sh start qwen3-35b     — start Qwen3-35B (by name)
#    agentia.sh start 45671         — start by port
#    agentia.sh stop 45671          — stop by port
#    agentia.sh toggle webui        — toggle Open WebUI on/off
#    agentia.sh logs qwen3-35b      — tail the Qwen3-35B log
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANAGER="${HOME}/.gx10/agentia-model-manager.py"
MODELS_CONFIG="${HOME}/.gx10/agentia.json"

# Create alias — call agentia-model-manager.py directly
if [ -f "$MANAGER" ]; then
    exec python3 "$MANAGER" "$@"
else
    echo "❌ agentia-model-manager.py not found at $MANAGER"
    exit 1
fi
