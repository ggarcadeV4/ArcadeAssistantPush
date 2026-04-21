"""
Arcade Launcher Agent
=====================
Lightweight TCP server that runs in the user's clean interactive session.
Receives JSON launch commands from the uvicorn backend (which has poisoned
console handles due to run-backend.bat stdout redirection) and executes
emulator processes with pristine WinSta0\\Default + GPU access.

Protocol (newline-delimited JSON over TCP on localhost:9123):
  Request:  {"exe": "...", "args": ["..."], "cwd": "...", "env_override": {}}
  Response: {"ok": true, "pid": 12345}
            {"ok": false, "error": "..."}

Usage:
  python scripts/arcade_launcher_agent.py          # foreground
  pythonw scripts/arcade_launcher_agent.py         # silent / startup folder
"""

import json
import logging
import os
import socket
import subprocess
import sys
import threading

AGENT_PORT = int(os.getenv("AA_LAUNCHER_AGENT_PORT", "9123"))
AGENT_HOST = "127.0.0.1"
AGENT_PROTOCOL_VERSION = "detached-v2"
LOG_FMT = "%(asctime)s [LauncherAgent] %(levelname)s  %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FMT)
log = logging.getLogger("launcher_agent")


def handle_client(conn: socket.socket, addr):
    """Handle a single launch request."""
    try:
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            # Newline-delimited: one request per connection
            if b"\n" in data:
                break

        if not data.strip():
            return

        payload = json.loads(data.decode("utf-8").strip())
        op = payload.get("op")
        if op == "ping":
            response = {
                "ok": True,
                "agent": "arcade_launcher_agent",
                "protocol_version": AGENT_PROTOCOL_VERSION,
            }
        else:
            exe = payload["exe"]
            args = payload.get("args", [])
            cwd = payload.get("cwd", None)
            env_override = payload.get("env_override", {})

            command = [exe] + args
            env = os.environ.copy()
            env.update(env_override)

            log.info("Launching: %s  cwd=%s", " ".join(command)[:120], cwd)

            create_new_process_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            detached_process = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)

            proc = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                creationflags=create_new_process_group | detached_process,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            response = {"ok": True, "pid": proc.pid}
            log.info("Launched PID %d", proc.pid)

    except Exception as e:
        log.error("Launch failed: %s", e)
        response = {"ok": False, "error": str(e)}

    try:
        conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
    except Exception:
        pass
    finally:
        conn.close()


def main():
    log.info("Arcade Launcher Agent starting on %s:%d", AGENT_HOST, AGENT_PORT)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((AGENT_HOST, AGENT_PORT))
    except OSError as e:
        log.error("Cannot bind to %s:%d — is another instance running?  %s",
                  AGENT_HOST, AGENT_PORT, e)
        sys.exit(1)

    srv.listen(5)
    log.info("Listening for launch commands...")

    try:
        while True:
            conn, addr = srv.accept()
            threading.Thread(
                target=handle_client, args=(conn, addr), daemon=True
            ).start()
    except KeyboardInterrupt:
        log.info("Agent shutting down.")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
