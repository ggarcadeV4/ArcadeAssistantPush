Arcade Assistant Bridge — Stage 2: Deploy & Discovery

Goal: Make LaunchBox recognize and load the plugin.

Prerequisites
- .NET 9 SDK installed (Windows Desktop).
- LaunchBox installed at A:\LaunchBox (adjust paths if different).

Build
- Open a PowerShell window.
- Run: dotnet build plugin/ArcadeAssistantPlugin.csproj -c Release

Deploy
- Run: plugin/deploy.ps1 (builds and copies DLL to A:\LaunchBox\Plugins\ArcadeAssistant\)
  - Optional: plugin/deploy.ps1 -SkipBuild to only copy the latest build.

Verify
- Start LaunchBox and open Tools -> Manage Plugins to confirm "Arcade Assistant Bridge".
- Check A:\LaunchBox\Logs\ArcadeAssistant.log for startup log lines.
- Test: curl http://localhost:9999/health (should return status ok).

Notes
- The project only compiles sources under plugin/src/** to avoid legacy files.
- If port 9999 is in use, the bridge logs an error and LaunchBox continues running.

