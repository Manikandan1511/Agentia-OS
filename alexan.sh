#!/bin/bash
# ============================================================
#  alexan.sh — GX10 Model Manager v3.0
#  Global JSON-driven model orchestration for Hermes
# ============================================================
#
#  CONFIG: ~/.gx10/models.json  (single source of truth)
#  SCRIPT: ~/.gx10/model-manager.py
#
#  USAGE:
#    alexan.sh status              — Show ALL running models
#    alexan.sh start-all           — Start all always-on models
#    alexan.sh stop-all            — Stop all running models
#    alexan.sh start <name>        — Start by name or port
#    alexan.sh stop <name>         — Stop by name or port
#    alexan.sh toggle <name>       — Toggle on/off
#    alexan.sh logs <name>         — Show last 20 log lines
#    alexan.sh watchdog            — Auto-restart any crashed always-on models
#    alexan.sh boot-setup          — Install systemd + crontab for auto-restart
#
#  EXAMPLES:
#    alexan.sh status              — shows running models only
#    alexan.sh start qwen3-35b     — start Qwen3-35B (by name)
#    alexan.sh start 45671         — start by port
#    alexan.sh stop 45671          — stop by port
#    alexan.sh toggle webui        — toggle Open WebUI on/off
#    alexan.sh logs qwen3-35b      — tail the Qwen3-35B log
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANAGER="${HOME}/.gx10/model-manager.py"
MODELS_CONFIG="${HOME}/.gx10/models.json"

# Create alias — call model-manager.py directly
if [ -f "$MANAGER" ]; then
    exec python3 "$MANAGER" "$@"
else
    echo "❌ model-manager.py not found at $MANAGER"
    exit 1
fi
