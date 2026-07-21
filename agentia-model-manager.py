#!/usr/bin/env python3
"""
agentia.sh — GX10 Model Manager v3.0

Reads configuration from ~/.gx10/agentia.json
Manages ALL models and services on the GX10 system.

Usage:
    agentia.sh status           — Show ALL running models (compact layout)
    agentia.sh help             — Show all commands and model shortcuts
    agentia.sh start-all        — Start all always-on models
    agentia.sh stop-all         — Stop all running models
    agentia.sh start <name>     — Start by name or port
    agentia.sh stop <name>      — Stop by name or port
    agentia.sh restart <name>   — Stop then start by name or port
    agentia.sh toggle <name>    — Toggle on/off
    agentia.sh logs <name>      — Show logs (follow if running, 50 lines if not)
    agentia.sh logs <name> --lines 100  — Show N lines
    agentia.sh watchdog         — Auto-restart any crashed always-on models
    agentia.sh boot-setup       — Install systemd + crontab for auto-restart
"""

import json
import os
import subprocess
import sys
import time
import signal
from datetime import datetime, timezone

CONFIG_PATH = os.path.expanduser("~/.gx10/agentia.json")
PID_DIR = os.path.expanduser("~/.gx10/pids")
STATE_DIR = os.path.expanduser("~/.gx10/state")
os.makedirs(STATE_DIR, exist_ok=True)


def mark_manual_stop(name):
    """Create a flag file so boot-orchestrator and watchdog know this model was stopped by the user."""
    p = os.path.join(STATE_DIR, f"manual_stop_{name}")
    with open(p, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())


def clear_manual_stop(name):
    """Remove the manual-stop flag so the model is back under auto-management."""
    p = os.path.join(STATE_DIR, f"manual_stop_{name}")
    if os.path.exists(p):
        os.remove(p)


def is_manually_stopped(name):
    """Return True if the user explicitly stopped this model (flag file exists)."""
    return os.path.exists(os.path.join(STATE_DIR, f"manual_stop_{name}"))


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_model_by_name(config, name):
    all_models = config.get("always_on", {}).get("models", []) + config.get("optional", {}).get("models", [])
    for m in all_models:
        if m["name"] == name or str(m["port"]) == str(name):
            return m
    return None



def is_port_open(port):
    """Return True if a process is actively LISTENING on the given TCP port."""
    try:
        result = subprocess.run(
            ["ss", "-ltnp"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        port = str(port)

        for line in result.stdout.splitlines():
            if f":{port} " in line or f":{port}\t" in line:
                return True

    except Exception:
        pass

    try:
        result = subprocess.run(
            ["fuser", f"{port}/tcp"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())

    except Exception:
        return False


def get_pid(port):
    """Return PID listening on the given TCP port."""
    import re

    try:
        result = subprocess.run(
            ["ss","-ltnp"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        port=str(port)

        for line in result.stdout.splitlines():

            if f":{port} " not in line and f":{port}\t" not in line:
                continue

            m=re.search(r"pid=(\d+)",line)

            if m:
                return int(m.group(1))

    except Exception:
        pass

    try:
        result=subprocess.run(
            ["fuser",f"{port}/tcp"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        pids=result.stdout.split()

        if pids:
            return int(pids[0])

    except Exception:
        pass

    return None

def short_desc(desc, max_words=3):
    if not desc:
        return ""
    words = desc.split()[:max_words]
    return " ".join(words).ljust(20)

def space_unit(s):
    """Insert a space between number and unit, e.g. '91Gi' -> '91 Gi'."""
    import re
    if not s:
        return s
    return re.sub(r'(\d+(?:\.\d+)?)\s*([A-Za-z]+)', r'\1 \2', s.strip())

def show_status(config):
    all_models = config.get("always_on", {}).get("models", []) + config.get("optional", {}).get("models", [])

    print("")
    print("=" * 120)
    print("  agentia Model Manager — ALL SERVICES")
    print("=" * 120)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"  Timestamp: {now}")
    print("=" * 120)
    print("")

    # Build all model entries — single flat table, no collapsing
    entries = []
    running_count = 0
    stopped_count = 0

    for m in all_models:
        port = m["port"]
        pid = get_pid(port)
        is_running = pid is not None
        name = m.get("display_name", m["name"])
        auto_star = "★" if m.get("always_on", False) or m.get("auto_start", False) else "☆"
        state = "RUNNING" if is_running else "STOPPED"
        desc_short = m.get("description", "")
        pid_info = f"PID {pid}" if is_running else "-"
        model_type = m.get("type", "model")
        entries.append({
            "star": auto_star,
            "name": name,
            "port": str(port),
            "state": state,
            "pid": pid_info,
            "desc": desc_short,
            "model_type": model_type,
            "model": m,
            "is_running": is_running,
        })
        if is_running:
            running_count += 1
        else:
            stopped_count += 1

    # Column header
    print(f"  {'STATUS':<10} {'★':<3} {'NAME':<22} {'PORT':>6}  {'PID':<10} {'TYPE':<10}  DESCRIPTION")
    print(f"  {'─' * 10}  {'─' * 3}  {'─' * 22}  {'─' * 6}  {'─' * 10}  {'─' * 10}  {'─' * 60}")

    # ALL models in one flat table — stopped first, then running
    stopped_entries = [e for e in entries if not e["is_running"]]
    running_entries = [e for e in entries if e["is_running"]]

    for e in stopped_entries:
        icon = "●" if e["is_running"] else "○"
        print(f"  {icon} STOPPED  {e['star']}  {e['name']:<22} {e['port']:>6}  {e['pid']:<10}  {e['model_type']:<10}  {e['desc']}")

    if stopped_entries and running_entries:
        print()

    for e in running_entries:
        icon = "●"
        print(f"  {icon} RUNNING  {e['star']}  {e['name']:<22} {e['port']:>6}  {e['pid']:<10}  {e['model_type']:<10}  {e['desc']}")

    print("")
    print("=" * 120)
    print(f"  Summary: {running_count} running | {stopped_count} stopped | {len(entries)} total")
    print("=" * 120)
    print("")

    # System memory — show raw free -h output with spaced units
    print("SYSTEM MEMORY")
    print("-" * 90)
    try:
        result = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if line.strip():
                print(space_unit(line))
            else:
                print()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,memory.free,utilization.gpu,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]:
                vals = line.split(", ")
                if len(vals) >= 5:
                    mem_used = vals[0].strip("[]")
                    mem_total = vals[1].strip("[]")
                    if mem_used != "N/A" and mem_total != "N/A":
                        print(f"  GPU  -> {vals[4]}: {space_unit(mem_used)}/{space_unit(mem_total)} MB used ({vals[3]}% util)")
                    else:
                        print(f"  GPU  -> {vals[4]}: ({vals[3]}% util)")
    except Exception:
        pass

    print("")
    return running_count, stopped_count


def find_and_kill_orphaned_processes(model):
    """Find and kill all orphaned processes related to this model, including multiple launches"""
    orphaned_pids = []
    
    try:
        # Look for all vllm processes that might be related to this model
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split("\n"):
            if "vllm serve" in line and model["name"] in line.lower():
                pid = int(line.split()[1])
                # Check if this PID is using the model path
                try:
                    proc_result = subprocess.run(
                        ["cat", f"/proc/{pid}/cmdline"], 
                        capture_output=True, text=True, timeout=2
                    )
                    if model["name"] in proc_result.stdout.lower():
                        orphaned_pids.append(pid)
                except Exception:
                    # If we can't read cmdline, assume it's related
                    orphaned_pids.append(pid)
        
        if orphaned_pids:
            print(f"🔍 Found {len(orphaned_pids)} potential orphaned process(es) for {model['display_name']}")
            for pid in orphaned_pids:
                print(f"   → PID {pid}")
            
            # Kill all orphaned processes
            for pid in orphaned_pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                    print(f"   ✅ Killed orphaned process PID {pid}")
                except Exception as e:
                    print(f"   ⚠️  Could not kill PID {pid}: {e}")
            
            print(f"   ⏳ Waiting 60 seconds for resources to be released...")
            time.sleep(60)
            
            # Verify they're actually gone
            remaining_pids = []
            for pid in orphaned_pids:
                try:
                    os.kill(pid, 0)  # Check if process exists
                    remaining_pids.append(pid)
                except OSError:
                    pass  # Process is gone, which is what we want
            
            if remaining_pids:
                print(f"   ⚠️  {len(remaining_pids)} process(es) still running: {remaining_pids}")
                print(f"   💡 Try running with admin privileges or manually kill these processes")
            else:
                print(f"   ✅ All orphaned processes successfully terminated")
            
            return len(orphaned_pids)
        
        return 0
    except Exception as e:
        print(f"   ⚠️  Error checking for orphaned processes: {e}")
        return 0


def confirm_kill_previous_instance(pid, model_name):
    """Ask user if they want to kill a previous instance"""
    print(f"⚠️  Found a previous instance of {model_name} (PID {pid}) still running")
    print(f"   This may be from a previous session that didn't clean up properly.")
    print(f"   Do you want to kill it to free up resources? [Y/n] ")
    
    try:
        # Use select with timeout
        import sys
        import select
        import tty
        import termios
        
        # Set up terminal for single character input
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            
            # Wait for input with 5 second timeout
            rlist, _, _ = select.select([sys.stdin], [], [], 5.0)
            
            if rlist:
                # Read single character
                char = sys.stdin.read(1).lower()
                if char in ['y', '\n', '\r']:
                    return True
                elif char == 'n':
                    return False
                else:
                    # Any other key means no
                    return False
            else:
                # Timeout - use default (yes)
                print("\n   Timeout reached. Using default: YES")
                return True
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        # If we can't get user input, default to killing
        print("   Cannot read input. Defaulting to YES to kill previous instance.")
        return True


def build_start_command(model):
    """Build start command dynamically from parameters if available"""
    if "parameters" in model:
        params = model["parameters"]
        
        # Handle llama-server models
        if "llama-server" in model.get("start_command", ""):
            cmd = f"nohup $HOME/llama.cpp/build/bin/llama-server \\"
            cmd += f"--model {model['start_command'].split('--model')[1].split(' --')[0]} \\"
            cmd += f"--host 0.0.0.0 \\"
            cmd += f"--port {model['port']} \\"
            cmd += f"--n-gpu-layers {params.get('n_gpu_layers', 99)} \\"
            cmd += f"--ctx-size {params.get('ctx_size', 32768)} \\"
            cmd += f"--threads {params.get('threads', 8)} \\"
            if params.get('enable_jinja', True):
                cmd += "--jinja \\"
            cmd += f"> {model.get('log_file', '/tmp/model.log')} 2>&1 &"
            return cmd
        
        # Handle vllm models
        if "vllm serve" in model.get("start_command", ""):
            cmd = f"export VLLM_USE_V1=0 && nohup vllm serve \\"
            cmd += f"{model['start_command'].split('vllm serve')[1].split(' --')[0]} \\"
            cmd += f"--max-model-len {params.get('ctx_size', 32768)} \\"
            cmd += f"--gpu-memory-utilization {params.get('gpu_memory_utilization', 0.8)} \\"
            cmd += f"--port {model['port']} \\"
            if params.get('enable_chunked_prefill', True):
                cmd += "--enable-chunked-prefill \\"
            cmd += f"--max-num-seqs {params.get('max_num_seqs', 32)} \\"
            if params.get('enable_auto_tool_choice', True):
                cmd += "--enable-auto-tool-choice \\"
            if params.get('tool_call_parser'):
                cmd += f"--tool-call-parser {params.get('tool_call_parser')} \\"
            cmd += f"> {model.get('log_file', '/tmp/model.log')} 2>&1 &"
            return cmd
    
    # Fallback to original command
    return model.get("start_command", "")

def start_model(config, model):
    clear_manual_stop(model["name"])       # clear manual-stop flag — back under auto-management
    pid = get_pid(model["port"])

    if pid is not None:
        print(f"✅ {model['display_name']} already running (PID {pid})")
        return True

    orphaned_count = find_and_kill_orphaned_processes(model)
    if orphaned_count > 0:
        print(f"   🔄 Cleanup done, continuing startup...")
        time.sleep(3)

    timeout = model.get("startup_wait_seconds", 10)
    print(f"⏳ Starting {model['display_name']}...")

    try:
        log_file = model.get("log_file", "/dev/null")
        log_fh = open(log_file, "a")

        start_command = build_start_command(model) or model["start_command"]

        subprocess.Popen(
            ["bash", "-c", start_command],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )

        start_time = time.time()
        port_seen_at = None
        pid_grace_seconds = 15  # extra time to resolve PID after port is confirmed open

        while True:
            elapsed = time.time() - start_time

            if is_port_open(model["port"]):
                if port_seen_at is None:
                    port_seen_at = time.time()

                pid = get_pid(model["port"])

                if pid:
                    os.makedirs(PID_DIR, exist_ok=True)
                    with open(os.path.join(PID_DIR, str(model["port"])), "w") as f:
                        f.write(str(pid))
                    print(f"✅ {model['display_name']} READY (PID {pid})")
                    return True

                if time.time() - port_seen_at > pid_grace_seconds:
                    print(f"⚠️  {model['display_name']} port is open but PID could not be resolved "
                          f"after {pid_grace_seconds}s — reporting READY without PID tracking.")
                    return True

            elif elapsed >= timeout:
                print(f"❌ FAILED: {model['display_name']} did NOT start")
                print(f"👉 Check logs: {model.get('log_file')}")
                return False

            time.sleep(2)

    except Exception as e:
        print(f"❌ ERROR starting {model['display_name']}: {e}")
        return False


def stop_model(config, model):
    if not is_port_open(model["port"]):
        print(f"⚠️  {model['display_name']} is not running")
        return True

    port = model["port"]
    name = model["display_name"]
    print(f"Stopping {name} (port {port})...")

    try:
        subprocess.run(model["stop_command"], shell=True, capture_output=True)
        time.sleep(2)

        if is_port_open(model["port"]):
            pid = get_pid(port)
            if pid:
                os.kill(pid, signal.SIGKILL)
                print(f"  Force-killed {name} (PID {pid})")
        else:
            print(f"  ✅ {name} stopped")

        mark_manual_stop(model["name"])    # mark as manually stopped

        pid_file = os.path.join(PID_DIR, str(port))
        if os.path.exists(pid_file):
            os.remove(pid_file)
        return True

    except Exception as e:
        print(f"  ❌ Failed to stop {name}: {e}")
        return False


def restart_model(config, model):
    """Stop a model (if running), wait for port to free, then start it fresh."""
    name = model["display_name"]
    port = model["port"]
    print(f"🔄 Restarting {name} (port {port})...")

    # Stop if running
    if is_port_open(port):
        print(f"  ⏹ Stopping {name}...")
        try:
            subprocess.run(model.get("stop_command", ""), shell=True, capture_output=True)
            time.sleep(2)
            if is_port_open(port):
                pid = get_pid(port)
                if pid:
                    os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

        # Wait for port to be freed (up to 30s)
        waited = 0
        while is_port_open(port) and waited < 30:
            time.sleep(1)
            waited += 1

        if is_port_open(port):
            print(f"  ⚠️  Port {port} still in use after {waited}s — forcing kill...")
            pid = get_pid(port)
            if pid:
                os.kill(pid, signal.SIGKILL)
                time.sleep(2)
        else:
            print(f"  ✅ Port {port} freed")

        # Clean up PID file
        pid_file = os.path.join(PID_DIR, str(port))
        if os.path.exists(pid_file):
            os.remove(pid_file)
    else:
        print(f"  ℹ️  {name} was not running, proceeding to start...")

    # Clear manual stop flag so watchdog doesn't skip it
    clear_manual_stop(model["name"])

    # Start fresh
    print(f"  ▶ Starting {name}...")
    return start_model(config, model)


def show_logs(config, model, lines=20, follow=False):
    log_file = model.get("log_file", "")
    if not log_file or not os.path.exists(log_file):
        print(f"⚠️  Log file not found: {log_file}")
        return

    is_running = is_port_open(model["port"])

    if follow and is_running:
        # Follow mode: tail -f the log
        print(f"📋 Following logs for {model['display_name']} ({log_file}) — press Ctrl+C to stop")
        print("-" * 70)
        subprocess.run(["tail", "-f", log_file])
    else:
        # Show last N lines
        print(f"📋 Last {lines} lines for {model['display_name']} ({log_file}):")
        print("-" * 70)
        try:
            with open(log_file) as f:
                all_lines = f.readlines()
            for line in all_lines[-lines:]:
                print(f"  {line.rstrip()}")
        except Exception as e:
            print(f"❌ Error reading log: {e}")


def show_help(config):
    print("")
    print("=" * 90)
    print("  GX10 Model Manager v3.1 — COMMAND REFERENCE")
    print("=" * 90)
    print("")

    # System commands
    print("SYSTEM COMMANDS")
    print("-" * 90)
    print(f"  agentia.sh status            — Show all models (compact layout)")
    print(f"  agentia.sh help              — Show this help page")
    print(f"  agentia.sh start-all         — Start all always-on models")
    print(f"  agentia.sh stop-all          — Stop all running models")
    print(f"  agentia.sh watchdog          — Auto-restart crashed always-on models")
    print(f"  agentia.sh boot-setup        — Install systemd + crontab auto-restart")
    print("")

    # Always-on models
    all_models = config.get("always_on", {}).get("models", []) + config.get("optional", {}).get("models", [])
    always_on_models = config.get("always_on", {}).get("models", [])
    optional_models = config.get("optional", {}).get("models", [])

    print("ALWAYS-ON MODELS")
    print("-" * 90)
    for m in always_on_models:
        name = m["name"]
        port = m["port"]
        desc = short_desc(m.get("description", ""), 40)
        print(f"  {name:<20} port {port}  [{desc}]")
        print(f"    ./agentia.sh start {name}     — Start")
        print(f"    ./agentia.sh stop {name}      — Stop")
        print(f"    ./agentia.sh toggle {name}    — Toggle on/off")
        print(f"    ./agentia.sh logs {name}       — Follow logs (or --lines N)")
        print("")

    print("OPTIONAL MODELS")
    print("-" * 90)
    if optional_models:
        for m in optional_models:
            name = m["name"]
            port = m["port"]
            desc = short_desc(m.get("description", ""), 40)
            print(f"  {name:<20} port {port}  [{desc}]")
            print(f"    ./agentia.sh start {name}     — Start")
            print(f"    ./agentia.sh stop {name}      — Stop")
            print(f"    ./agentia.sh toggle {name}    — Toggle on/off")
            print(f"    ./agentia.sh logs {name}       — Follow logs (or --lines N)")
            print("")
    else:
        print("  (no optional models)")
        print("")

    print("LOG COMMANDS")
    print("-" * 90)
    print("  ./agentia.sh logs qwen35                — Follow mode (tail -f) if running")
    print("  ./agentia.sh logs qwen35 --lines 100    — Show last 100 lines")
    print("  ./agentia.sh logs qwen35 --lines 1000   — Show last 1000 lines")
    print("")
    print("=" * 90)
    print("")


def do_watchdog(config):
    print("Watchdog running...")
    all_models = config.get("always_on", {}).get("models", []) + config.get("optional", {}).get("models", [])
    restarted = 0

    for m in all_models:
        if not m.get("always_on"):
            continue

        if is_manually_stopped(m["name"]):
            print(f"  ⏸️  {m['display_name']} — skipped (manually stopped, waiting for your command)")
            continue

        if not is_port_open(m["port"]):
            port = m["port"]
            name = m["display_name"]
            print(f"  ⚠️  {name} (port {port}) is DOWN — attempting restart...")
            if start_model(config, m):
                restarted += 1
            else:
                print(f"  ❌ Failed to restart {name}. Check logs: {m.get('log_file', 'N/A')}")

    if restarted == 0:
        print("  ✅ All always-on models are healthy")
    else:
        print(f"  🔧 Watchdog restarted {restarted} model(s)")

    return restarted


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    config = load_config()
    action = sys.argv[1]

    if action == "status":
        show_status(config)

    elif action == "help":
        show_help(config)

    elif action == "start-all":
        print("Starting all always-on models...")
        all_models = config.get("always_on", {}).get("models", []) + config.get("optional", {}).get("models", [])
        for m in all_models:
            if m.get("auto_start"):
                start_model(config, m)

    elif action == "stop-all":
        print("Stopping all running models...")
        all_models = config.get("always_on", {}).get("models", []) + config.get("optional", {}).get("models", [])
        for m in all_models:
            if is_port_open(m["port"]):
                stop_model(config, m)

    elif action == "start":
        if len(sys.argv) < 3:
            print("Usage: agentia.sh start <name|port>")
            sys.exit(1)
        arg = sys.argv[2]
        model = get_model_by_name(config, arg)
        if not model:
            print(f"❌ Model '{arg}' not found")
            sys.exit(1)
        start_model(config, model)

    elif action == "stop":
        if len(sys.argv) < 3:
            print("Usage: agentia.sh stop <name|port>")
            sys.exit(1)
        arg = sys.argv[2]
        model = get_model_by_name(config, arg)
        if not model:
            print(f"❌ Model '{arg}' not found")
            sys.exit(1)
        stop_model(config, model)

    elif action == "restart":
        if len(sys.argv) < 3:
            print("Usage: agentia.sh restart <name|port>")
            sys.exit(1)
        arg = sys.argv[2]
        model = get_model_by_name(config, arg)
        if not model:
            print(f"❌ Model '{arg}' not found")
            sys.exit(1)
        restart_model(config, model)

    elif action == "toggle":
        if len(sys.argv) < 3:
            print("Usage: agentia.sh toggle <name|port>")
            sys.exit(1)
        arg = sys.argv[2]
        model = get_model_by_name(config, arg)
        if not model:
            print(f"❌ Model '{arg}' not found")
            sys.exit(1)
        if is_port_open(model["port"]):
            stop_model(config, model)
        else:
            start_model(config, model)

    elif action == "logs":
        if len(sys.argv) < 3:
            print("Usage: agentia.sh logs <name|port> [--lines N]")
            sys.exit(1)
        arg = sys.argv[2]
        model = get_model_by_name(config, arg)
        if not model:
            print(f"❌ Model '{arg}' not found")
            sys.exit(1)

        # Parse --lines flag
        n_lines = 20
        follow = True  # default: follow mode when running
        for i in range(3, len(sys.argv)):
            if sys.argv[i] == "--lines" and i + 1 < len(sys.argv):
                try:
                    n_lines = int(sys.argv[i + 1])
                    follow = False
                except ValueError:
                    print(f"❌ Invalid line count: {sys.argv[i+1]}")
                    sys.exit(1)

        show_logs(config, model, lines=n_lines, follow=follow)

    elif action == "watchdog":
        do_watchdog(config)

    elif action == "boot-setup":
        print("Installing systemd service + crontab for auto-restart...")
        setup_boot(config)

    elif action in ("--help", "-h", "*"):
        show_help(config)

    else:
        print(f"❌ Unknown action: {action}")
        print(__doc__)


def setup_boot(config):
    import subprocess
    import os

    unit_dir = "/etc/systemd/system"
    start_unit = f"""[Unit]
Description=GX10 Model Manager - Start All on Boot
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {os.path.expanduser('~')}/.gx10/model-manager.py start-all
RemainAfterExit=no
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

    with open(os.path.join(unit_dir, "gx10-start-all.service"), "w") as f:
        f.write(start_unit)

    subprocess.run(["sudo", "systemctl", "daemon-reload"], capture_output=True)
    subprocess.run(["sudo", "systemctl", "enable", "gx10-start-all"], capture_output=True)
    print("  ✅ Installed /etc/systemd/system/gx10-start-all.service")

    cron_line = f"*/5 * * * * /usr/bin/python3 {os.path.expanduser('~')}/.gx10/model-manager.py watchdog 2>/dev/null"

    try:
        current_cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = current_cron.stdout if current_cron.returncode == 0 else ""
        if cron_line.strip() not in existing.strip().split("\n"):
            new_cron = existing.rstrip("\n") + "\n" + cron_line + "\n"
            subprocess.run(["crontab", "-"], input=new_cron, text=True, capture_output=True)
            print("  ✅ Added watchdog to crontab (every 5 min)")
        else:
            print("  ✅ Watchdog crontab entry already present")
    except Exception:
        print("  ⚠️  Could not update crontab. Do manually:")
        print(f"     crontab -e")
        print(f"     add: {cron_line}")

    print("\n  Boot auto-start is now configured!")
    print("  → On reboot: gx10-start-all.service runs start-all")
    print("  → Every 5 min: watchdog checks all always-on models")
    print("  → Qwen3-35B is NEVER stopped by the watchdog")


if __name__ == "__main__":
    main()