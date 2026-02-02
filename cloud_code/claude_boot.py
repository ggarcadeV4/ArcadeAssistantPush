import os
from datetime import datetime

STARTUP_FILES = [
    "docs/PROMETHEA_GUI_STYLE_GUIDE.md",
    "docs/UNIVERSAL_AGENT_RULES.md",  # Corrected path - moved from cloud_code/
    "agents/CLAUDE_CREW.md",
    "agents/AGENT_CALL_MATRIX.md",
    "docs/CLOUD_STARTUP.md"  # Corrected path - moved from cloud_code/
]

LOG_DIR = "logs/agent_boot"
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
LOG_FILE = os.path.join(LOG_DIR, f"claude_boot_{timestamp}.log")

def check_required_files():
    passed = True
    log_lines = [f"Claude Boot Log — {datetime.now().isoformat()}\n"]

    for file_path in STARTUP_FILES:
        if os.path.exists(file_path):
            log_lines.append(f"✔️ Found: {file_path}")
        else:
            log_lines.append(f"❌ MISSING: {file_path}")
            passed = False

    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "w") as log_file:
        log_file.write("\n".join(log_lines))

    if not passed:
        raise RuntimeError("🚨 Claude boot failed — one or more critical startup files missing.")

    print("✅ Claude environment initialized successfully.")

if __name__ == "__main__":
    check_required_files()