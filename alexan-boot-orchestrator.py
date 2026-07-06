#!/usr/bin/env python3
"""
alexan-boot-orchestrator.py — GX10 Auto Boot Orchestrator v1.0

Reads the staged startup plan from ~/.gx10/alexan-auto-boot.json and drives
~/alexan.sh (which reads ~/.gx10/alexan.json) to bring up the 7 core services
in the correct order after a reboot or crash.

It does NOT duplicate any start_command — every step just shells out to
"./alexan.sh start <name>", same as you'd type by hand.

Usage:
    alexan-boot-orchestrator.py boot       — Full staged startup (run at system boot)
    alexan-boot-orchestrator.py watchdog   — Check the 7 services, restart any that are down
    alexan-boot-orchestrator.py install    — Install systemd unit + cron watchdog entry
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
BOOT_CONFIG = os.path.join(HOME, ".gx10", "alexan-auto-boot.json")
LOG_FILE = "/tmp/alexan-boot-orchestrator.log"


def log(msg):
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_plan():
    with open(BOOT_CONFIG) as f:
        return json.load(f)


def is_port_open(port):
    try:
        r = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True, timeout=5)
        port = str(port)
        for line in r.stdout.splitlines():
            if f":{port} " in line or f":{port}\t" in line:
                return True
    except Exception:
        pass
    return False


def start_service(entry):
    name = entry["name"]
    display = entry.get("display_name", name)
    port = entry["port"]

    if is_port_open(port):
        log(f"✅ {display} already running on port {port} — skipping")
        return True

    log(f"⏳ Starting {display} (step {entry['step']}) via: {entry['start_via']}")
    subprocess.run(entry["start_via"], shell=True, cwd=HOME)

    timeout = entry.get("max_startup_wait_seconds", 60)
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(port):
            log(f"✅ {display} READY on port {port} ({int(time.time() - start)}s)")
            return True
        time.sleep(3)

    log(f"❌ {display} did NOT come up on port {port} within {timeout}s")
    if entry.get("critical"):
        log(f"⚠️  {display} is CRITICAL — later steps depend on it. Check its log manually.")
    return False


def run_boot(plan):
    log("========== GX10 AUTO BOOT SEQUENCE STARTING ==========")
    for entry in plan["boot_sequence"]:
        start_service(entry)
        wait = entry.get("wait_after_ready_seconds", 0)
        if wait > 0:
            log(f"⏸  Waiting {wait}s before next step...")
            time.sleep(wait)
    log("========== GX10 AUTO BOOT SEQUENCE COMPLETE ==========")


def run_watchdog(plan):
    log("Watchdog check starting...")
    restarted = 0
    for entry in plan["boot_sequence"]:
        port = entry["port"]
        display = entry.get("display_name", entry["name"])
        if is_port_open(port):
            continue
        log(f"⚠️  {display} (port {port}) is DOWN — restarting individually (not the full sequence)...")
        if start_service(entry):
            restarted += 1
    if restarted == 0:
        log("✅ All 7 core services healthy")
    else:
        log(f"🔧 Watchdog restarted {restarted} service(s)")


def install():
    unit = f"""[Unit]
Description=GX10 Auto Boot Orchestrator - Staged Startup
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {HOME}/.gx10/alexan-boot-orchestrator.py boot
RemainAfterExit=no
StandardOutput=journal
StandardError=journal
TimeoutStartSec=1200

[Install]
WantedBy=multi-user.target
"""
    tmp_unit = "/tmp/gx10-auto-boot.service"
    with open(tmp_unit, "w") as f:
        f.write(unit)

    unit_path = "/etc/systemd/system/gx10-auto-boot.service"
    subprocess.run(["sudo", "cp", tmp_unit, unit_path])
    subprocess.run(["sudo", "systemctl", "daemon-reload"])
    subprocess.run(["sudo", "systemctl", "enable", "gx10-auto-boot"])
    print(f"✅ Installed {unit_path} and enabled it (runs the full staged boot on every reboot)")

    cron_line = (
        f"*/5 * * * * /usr/bin/python3 {HOME}/.gx10/alexan-boot-orchestrator.py watchdog "
        f">> {LOG_FILE} 2>&1"
    )
    current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = current.stdout if current.returncode == 0 else ""
    if cron_line.strip() not in existing.strip().split("\n"):
        new_cron = existing.rstrip("\n") + "\n" + cron_line + "\n"
        subprocess.run(["crontab", "-"], input=new_cron, text=True)
        print("✅ Added watchdog cron entry (every 5 min, checks the 7 core services)")
    else:
        print("✅ Watchdog cron entry already present")

    print("\nInstalled!")
    print("  → On reboot: gx10-auto-boot.service runs the full staged sequence (Qwen3.6 -> Hermes -> rest)")
    print("  → Every 5 min: watchdog checks all 7 services and restarts ONLY whichever one crashed")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    action = sys.argv[1]

    if action == "install":
        install()
        return

    plan = load_plan()
    if action == "boot":
        run_boot(plan)
    elif action == "watchdog":
        run_watchdog(plan)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
