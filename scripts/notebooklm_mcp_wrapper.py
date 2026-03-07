"""
NotebookLM MCP Server Wrapper for Antigravity
Suppresses the ASCII art startup banner that breaks JSON-RPC communication.
"""
import sys
import subprocess
import os

def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "notebooklm_mcp"],
        stdin=sys.stdin,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        bufsize=0
    )
    
    banner_done = False
    for line in iter(proc.stdout.readline, b''):
        decoded = line.decode('utf-8', errors='replace')
        # Skip banner lines (non-JSON lines before first JSON-RPC message)
        if not banner_done:
            stripped = decoded.strip()
            if stripped.startswith('{'):
                banner_done = True
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
            # else: skip banner line
        else:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
    
    proc.wait()
    sys.exit(proc.returncode)

if __name__ == "__main__":
    main()
