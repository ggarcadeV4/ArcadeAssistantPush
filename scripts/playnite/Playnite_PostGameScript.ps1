# ============================================================================
# PLAYNITE SCRIPT: Execute AFTER exiting a game
# ============================================================================
# Paste this into: Playnite > Settings > Scripts > Execute after exiting a game
#
# What it does:
#   1. POSTs to /api/game/stop to reset LEDs to attract/idle mode
#   2. Refocuses Playnite window (some emulators leave Windows out of focus)
#   3. Wrapped in try/catch with 2-second timeout — NEVER blocks Playnite
# ============================================================================

try {
    # POST to Arcade Assistant backend to reset LEDs
    $params = @{
        Uri         = "http://127.0.0.1:8000/api/game/stop"
        Method      = "POST"
        ContentType = "application/json"
        TimeoutSec  = 2
    }
    Invoke-RestMethod @params | Out-Null

}
catch {
    # Silently swallow errors
    # Uncomment the next line for debugging:
    # $__logger.Warn("Arcade Assistant game/stop failed: $_")
}

# Refocus Playnite after emulator closes
# Some emulators (MAME, RetroArch) leave the desktop or another app in focus
try {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public class FocusHelper {
    [DllImport("user32.dll")]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

    # Find Playnite window and bring to front
    $hwnd = [FocusHelper]::FindWindow($null, "Playnite")
    if ($hwnd -eq [IntPtr]::Zero) {
        # Try fullscreen mode title
        $hwnd = [FocusHelper]::FindWindow($null, "Playnite Fullscreen")
    }

    if ($hwnd -ne [IntPtr]::Zero) {
        [FocusHelper]::ShowWindow($hwnd, 9)  # SW_RESTORE
        [FocusHelper]::SetForegroundWindow($hwnd) | Out-Null
    }
}
catch {
    # Focus restore is best-effort
}
