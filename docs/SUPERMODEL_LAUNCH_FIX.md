# Supermodel Launch Fix — Launcher Agent Architecture

## Quick Reference for Tomorrow

> **TL;DR:** OpenGL/SDL2 emulators (Supermodel, potentially others) cannot be launched
> directly by `subprocess.Popen` from the uvicorn backend because `run-backend.bat`
> redirects stdout/stderr to a log file, poisoning the entire process tree's console
> handles. The fix is the **Launcher Agent** — a separate Python process running in a
> clean interactive session that receives launch commands via TCP socket.

---

## The Problem

### Root Cause: Poisoned Console Handles

```
run-backend.bat → "start_backend.ps1 > backend.log 2>&1"
  → powershell.exe
    → python.exe (uvicorn)
      → subprocess.Popen(Supermodel.exe)  ❌ OpenGL fails
```

The `> backend.log 2>&1` redirection at the **root** of the process tree permanently
taints every child process's console handle inheritance. SDL2 (used by Supermodel)
aggressively probes the execution environment during OpenGL context creation. When it
detects the root console handles are piped/redirected, the GPU's Installable Client
Driver (ICD) assumes a headless/restricted context and **refuses to bind hardware-
accelerated OpenGL**.

### Error Message
```
Unable to create an OpenGL display: OpenGL not available
Program terminated due to an error.
```

### What We Tried (All Failed)

| Approach | Why It Failed |
|---|---|
| Bare `subprocess.Popen` | Inherits poisoned handles |
| `+ CREATE_NEW_CONSOLE` | New console, but still inherits poisoned desktop context |
| `+ env=os.environ.copy()` | Environment is fine, handles are the problem |
| `+ stdin/stdout/stderr=DEVNULL` | Severs inherited handles but desktop context still poisoned |
| `+ startupinfo.lpDesktop="WinSta0\\Default"` | Forces interactive desktop but handles still poisoned at the process tree root |
| `cmd.exe /c start` (shell=True) | Full detach, but cmd.exe itself inherits poisoned context from backend |
| All combinations of above | The poison is at the process tree root — no child-level fix works |

### What DID Work
Running the **exact same subprocess.Popen command** from a regular PowerShell terminal
(clean process tree, no redirected stdout) launched Supermodel perfectly every time.

---

## The Solution: Launcher Agent

### Architecture

```
┌──────────────────────────────┐   TCP localhost:9123   ┌────────────────────────┐
│  uvicorn backend             │  ───────────────────►  │  arcade_launcher_agent │
│  (poisoned process tree)     │   JSON: {exe,args,cwd} │  (clean session)       │
│  Session 2, redirected IO    │  ◄───────────────────  │  Session 2, WinSta0    │
│                              │   JSON: {ok, pid}      │  Real console handles  │
└──────────────────────────────┘                        └────────────────────────┘
                                                               │
                                                               ▼
                                                        subprocess.Popen()
                                                        Supermodel.exe ✅
```

### Files

| File | Purpose |
|---|---|
| `scripts/arcade_launcher_agent.py` | TCP server on `localhost:9123`, receives JSON launch commands, executes `subprocess.Popen` in clean context |
| `scripts/start_launcher_agent.bat` | Starter script (can go in Windows Startup folder) |
| `backend/services/launcher.py` | `_launch_via_agent()` client function sends commands to the agent |

### How It Works

1. **Agent starts independently** — NOT from `run-backend.bat`. Can be started manually,
   from Windows Startup folder, or via `start_launcher_agent.bat`.
2. **Backend detects Supermodel** — `needs_detach` flag triggers when emulator title
   contains "supermodel".
3. **Backend sends JSON** to `localhost:9123`:
   ```json
   {"exe": "Supermodel.exe", "args": ["game.zip"], "cwd": "A:\\Emulators\\Super Model"}
   ```
4. **Agent executes** `subprocess.Popen` in its clean process tree → OpenGL initializes.
5. **Agent returns** `{"ok": true, "pid": 12345}` to the backend.

---

## Rules for Tomorrow: Adding Other Emulators

### Which Emulators Need the Agent?

Any emulator that uses **OpenGL or DirectX for rendering** AND crashes when launched
from a redirected-stdout process tree:

| Emulator | Renderer | Likely Needs Agent? |
|---|---|---|
| **Supermodel** (Sega Model 3) | SDL2 + OpenGL | ✅ Yes (confirmed) |
| **Flycast** (Dreamcast/Naomi) | OpenGL/Vulkan | ⚠️ Test first |
| **PCSX2** (PS2) | OpenGL/Vulkan | ⚠️ Test first |
| **Dolphin** (GameCube/Wii) | OpenGL/Vulkan | ⚠️ Test first |
| **RetroArch** | Various | ❌ Usually handles this gracefully |
| **MAME** | SDL/bgfx | ❌ Works fine from backend |
| **Redream** (Dreamcast) | Vulkan | ⚠️ Test first |

### How to Add an Emulator to the Agent

1. In `launcher.py` → `_execute_emulator()`, add to the `needs_detach` check:
   ```python
   needs_detach = (
       'supermodel' in emu_title.lower()
       or 'supermodel' in str(command[0]).lower()
       or 'new_emulator' in emu_title.lower()  # ← add here
   )
   ```

2. If the emulator has an adapter with `no_pipe: True`, it will automatically
   route through the agent via the `no_pipe` branch in `_run_adapter_process`.

### What NOT to Do

1. ❌ **Don't try `CREATE_NEW_CONSOLE` + `DEVNULL` + `lpDesktop`** — we tried every
   combination. The poison is at the process tree root.
2. ❌ **Don't use `CreateProcessAsUser` / `WTSQueryUserToken`** — requires
   `SeTcbPrivilege` (NT AUTHORITY\SYSTEM), massive security risk, brittle ctypes.
3. ❌ **Don't launch LED software concurrently** with Supermodel — SDL2 requires
   absolute foreground focus during OpenGL init. Any focus-stealing process will
   cause the GPU driver to reject the OpenGL context request.
4. ❌ **Don't `taskkill` Supermodel** — causes input locks and timing state corruption.
   Let the user exit via ESC or mapped arcade button.

### Additional Notes from the Supermodel Gem

- **Exclusive Focus**: Supermodel requires absolute foreground focus to capture raw
  arcade IO (steering, pedals, lightguns). Any focus loss breaks inputs.
- **Static Configuration**: All config must be static in `Supermodel.ini` or per-game
  overrides. Don't pass dynamic settings at runtime.
- **Clean Exit**: Track PID but allow clean exit. Never force-kill.
- **LED Serialization**: If LED profiles are needed, fire them BEFORE the game launch
  and wait for completion. Never concurrently.

---

## Startup Checklist

1. Start Launcher Agent: `python scripts\arcade_launcher_agent.py` (separate terminal)
2. Verify: `Test-NetConnection 127.0.0.1 -Port 9123` → `TcpTestSucceeded: True`
3. Start backend normally (`run-backend.bat`)
4. Launch games via LoRa
