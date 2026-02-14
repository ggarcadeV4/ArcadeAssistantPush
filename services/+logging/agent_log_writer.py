# @service: agent_log_writer
# @role: Appends structured log lines to agent_calls log file

import os
from datetime import datetime

LOG_DIR = "logs/agent_calls"
os.makedirs(LOG_DIR, exist_ok=True)

def log_agent_event(message: str):
    """Log an agent event with timestamp to daily log file"""
    timestamp = datetime.now().strftime("%Y-%m-%d")
    time = datetime.now().strftime("%H:%M")
    log_file = os.path.join(LOG_DIR, f"{timestamp}_agent_calls.log")

    entry = f"[{time}] {message}\n"
    with open(log_file, "a") as f:
        f.write(entry)

# Example usage:
# log_agent_event("ClaudeCode called: Hera → panels/A1_GameTipsPanel")