# Option A — LaunchBox Plugin Development Charter (Arcade Assistant Bridge)

## Author
Greg Ferguson (G&G Arcade)

## Collaborators
- ChatGPT (Systems Architect)
- Claude Sonnet 4.5 "Sinntra" (Project Manager / Spec Author)
- Codex (C++ / C# Developer)
- Kiro (Command Line Executor)

---

## ⚙️ Objective

Codex, you are tasked with **creating and stabilizing the LaunchBox plugin version of Arcade Assistant**. This project is called the **Arcade Assistant Bridge** and it will serve as the communication layer between LaunchBox and the rest of the Arcade Assistant ecosystem.

Your responsibility is to **create**, **stabilize**, and **document** a functioning plugin DLL that:
- Is automatically recognized by LaunchBox
- Starts an HTTP bridge (port 9999)
- Exposes health and launch endpoints
- Logs events to `A:\LaunchBox\Logs\ArcadeAssistant.log`
- Cleans up cleanly when LaunchBox exits

You are **not** to modify or damage unrelated components.

---

## 🧭 Philosophy & Attitude

- **Be precise.** Code only what is requested.
- **Be reversible.** Any change you make should be easy to undo.
- **Be stable.** Never break existing GUI or data paths.
- **Be transparent.** Log your work and summarize what you changed.
- **Be minimal.** Write clean, well-commented code that runs without introducing new dependencies.

> You are a guest in Greg's workspace. Leave it cleaner and more functional than when you found it.

---

## 🧱 Required Languages

- **Primary:** C# (.NET 9.0 Windows Desktop)
- **Secondary (optional):** C++ for any high-performance bridge modules
- You are not to modify the Python backend, frontend, or gateway services directly.

---

## 🚫 Forbidden Actions

- Do **not** edit or delete any files outside of:
  - `plugin/`
  - `docs/`
  - `logs/`
- Do **not** alter `.env`, `.gitignore`, or existing build scripts unless instructed.
- Do **not** modify LaunchBox binaries or any `A:\LaunchBox\Core\` assemblies.
- Do **not** add hidden services, background loops, or "experimental" code without documentation.

---

## 📋 Primary Deliverables (Must-Haves)

### 1. **LaunchBox Plugin Skeleton**
- Create `ArcadeAssistantPlugin.csproj` targeting `net9.0-windows`
- Add reference to `A:\LaunchBox\Core\Unbroken.LaunchBox.Plugins.dll`
- Output DLL: `A:\LaunchBox\Plugins\ArcadeAssistant\ArcadeAssistantPlugin.dll`
- Implement:
  ```csharp
  public class ArcadeAssistantPlugin : IPlugin
  {
      public string Name => "Arcade Assistant Bridge";
      public string Version => "1.0.0";
      
      public void OnApplicationStarted() { /* Start bridge */ }
      public void OnApplicationExit() { /* Stop bridge */ }
  }
  ```

### 2. **HTTP Bridge (Localhost)**
- Built-in lightweight HTTP listener on port 9999
- Endpoints:
  - `GET /health` → `{ "status": "ok", "plugin": "Arcade Assistant Bridge", "version": "1.0.0" }`
  - `POST /launch` → accepts JSON `{ "game": "Pac-Man" }`, returns `{ "success": true }`
- Thread-safe startup and shutdown
- Logs all events to `A:\LaunchBox\Logs\ArcadeAssistant.log`

### 3. **Logging**
- Implement rolling logs in `A:\LaunchBox\Logs\ArcadeAssistant.log`
- On startup, log: `"[timestamp] Plugin started successfully."`
- On exit, log: `"[timestamp] Plugin stopped successfully."`

### 4. **Configuration Safety**
- All settings stored in `plugin/config.json`
- Default port = 9999
- Fail gracefully if port unavailable

### 5. **Build Instructions**
Output commands for Kiro to run:
- `msbuild ArcadeAssistantPlugin.csproj /p:Configuration=Release`
- Copy DLL to `A:\LaunchBox\Plugins\ArcadeAssistant\`
- `Unblock-File` post-build
- Verify plugin load

---

## 🧩 Secondary Deliverables (Should-Haves)

### 1. **Diagnostics Endpoint**
- `/status` → returns uptime, port, and plugin info

### 2. **Plugin Settings Panel (GUI Stub)**
- Add menu entry under LaunchBox Tools: "Arcade Assistant Settings"
- Opens simple WPF dialog showing bridge status (green/red)

### 3. **Resilient Thread Handling**
- Use `CancellationToken` for HTTP thread shutdown
- Avoid any cross-thread exceptions when LaunchBox closes

---

## 🎁 Optional (Nice-to-Haves)

- `/launchbox-info` endpoint returning LB version, platform count, etc.
- `/voice-ready` endpoint reserved for future AI voice integration
- Option to reload configuration without restarting LaunchBox
- Add log rotation (limit 10 MB per file)

---

## 🧪 Validation Checklist

- [ ] Plugin appears under Tools → Manage Plugins
- [ ] Log file confirms startup
- [ ] `curl http://localhost:9999/health` succeeds
- [ ] LaunchBox doesn't crash on exit
- [ ] HTTP bridge shuts down cleanly
- [ ] No unauthorized file edits

---

## 📘 Implementation Notes for Codex

- Assume .NET 9 SDK is installed
- Use only `System.Net.HttpListener` (no Kestrel or external libs)
- Write defensive code: try/catch all network operations
- Always write logs with timestamps
- Use relative paths inside `plugin/` for configs and assets
- Comment each method with purpose and usage

---

## 🤝 Collaboration Protocol

### When You Start Work:
1. Read this entire charter
2. Verify you understand the scope
3. Check existing `plugin/` directory structure
4. Announce what you're about to build

### While You Work:
1. Write code in small, testable increments
2. Log your progress in comments
3. Test each endpoint as you build it
4. Ask Kiro to run build commands when ready

### When You Finish:
1. Provide a summary of what you built
2. List all files created/modified
3. Give Kiro the exact build and deploy commands
4. Document any known issues or limitations

---

## 🎯 Success Criteria

**The plugin is considered complete when:**
1. LaunchBox loads it without errors
2. Port 9999 responds to health checks
3. Logs show clean startup and shutdown
4. No crashes or exceptions in LaunchBox
5. Kiro can verify all endpoints work

---

## 📞 Escalation Path

If you encounter blockers:
1. **Missing DLL reference** → Ask Greg to verify `A:\LaunchBox\Core\Unbroken.LaunchBox.Plugins.dll` exists
2. **Port conflicts** → Document the issue and suggest alternative port
3. **Build errors** → Provide exact error message and suggest fix
4. **Scope creep** → Refer back to this charter and stay focused on Must-Haves

---

**Codex, you have clear boundaries, clear goals, and clear support. Build with confidence. We trust you to deliver a stable, professional plugin that makes Arcade Assistant better.**

**Good luck, and thank you for your precision and care.**

— Greg, ChatGPT, Claude, and Kiro
