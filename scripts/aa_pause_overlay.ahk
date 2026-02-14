; ============================================
; Arcade Assistant - Global Pause Menu Overlay
; ============================================
; This script listens for a global hotkey and triggers
; the Arcade Assistant pause menu overlay.
;
; Hotkey: F1 (configurable below)
; Works even when Pegasus or emulators have focus.
;
; Install: Run this script at startup to enable pause menu
; ============================================

#SingleInstance Force
#NoEnv
SetWorkingDir %A_ScriptDir%

; Configuration
global PauseMenuUrl := "http://localhost:5173/#/pause-menu"
global BackendUrl := "http://localhost:8787"
global OverlayActive := false

; Hotkey: F1 to toggle pause menu
; Change this to any key you prefer (e.g., `Pause::` or `~Joy7::` for controller)
F1::
    TogglePauseOverlay()
return

; Alternative: Guide button on Xbox controller (Button 8)
; Uncomment the line below to enable controller support
; ~Joy8::TogglePauseOverlay()

; Alternative: Select + Start combo (Joy7 + Joy8)
; ~Joy7 & Joy8::TogglePauseOverlay()

TogglePauseOverlay() {
    global OverlayActive
    
    if (OverlayActive) {
        ; Close overlay and resume
        CloseOverlay()
    } else {
        ; Open overlay and pause emulator
        OpenOverlay()
    }
}

OpenOverlay() {
    global OverlayActive, BackendUrl
    
    ; Notify backend that hotkey was pressed (triggers WebSocket event)
    try {
        WebRequest := ComObjCreate("WinHttp.WinHttpRequest.5.1")
        WebRequest.Open("POST", BackendUrl . "/api/local/hotkey/pause", false)
        WebRequest.SetRequestHeader("Content-Type", "application/json")
        WebRequest.SetRequestHeader("x-scope", "state")
        WebRequest.Send("{""action"": ""pause_pressed""}")
    } catch e {
        ; Backend might not be running - continue anyway
    }
    
    ; Try to pause the emulator (RetroArch network command)
    try {
        WebRequest := ComObjCreate("WinHttp.WinHttpRequest.5.1")
        WebRequest.Open("POST", BackendUrl . "/api/local/emulator/pause_toggle", false)
        WebRequest.SetRequestHeader("Content-Type", "application/json")
        WebRequest.SetRequestHeader("x-scope", "state")
        WebRequest.Send("")
    } catch e {
        ; Emulator might not support pause - continue anyway
    }
    
    ; Open the overlay in default browser (fullscreen)
    ; Using Chrome in app mode for clean overlay appearance
    ChromePath := "C:\Program Files\Google\Chrome\Application\chrome.exe"
    EdgePath := "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    
    if (FileExist(ChromePath)) {
        Run, "%ChromePath%" --app="%PauseMenuUrl%" --start-fullscreen --disable-infobars
    } else if (FileExist(EdgePath)) {
        Run, "%EdgePath%" --app="%PauseMenuUrl%" --start-fullscreen --disable-infobars
    } else {
        ; Fallback to default browser
        Run, %PauseMenuUrl%
    }
    
    OverlayActive := true
}

CloseOverlay() {
    global OverlayActive, BackendUrl
    
    ; Close any browser windows showing the pause menu
    ; This is a best-effort approach
    WinClose, Pause Menu
    WinClose, Arcade Assistant
    WinClose, ahk_exe chrome.exe
    WinClose, ahk_exe msedge.exe
    
    ; Resume emulator
    try {
        WebRequest := ComObjCreate("WinHttp.WinHttpRequest.5.1")
        WebRequest.Open("POST", BackendUrl . "/api/local/emulator/pause_toggle", false)
        WebRequest.SetRequestHeader("Content-Type", "application/json")
        WebRequest.SetRequestHeader("x-scope", "state")
        WebRequest.Send("")
    } catch e {
        ; Emulator might not support pause - continue anyway
    }
    
    OverlayActive := false
}

; ESC key closes overlay when it's active
#If OverlayActive
Escape::
    CloseOverlay()
return
#If

; Show tray icon and menu
Menu, Tray, Tip, Arcade Assistant Pause Menu (F1)
Menu, Tray, Add, Open Pause Menu, MenuOpenOverlay
Menu, Tray, Add, Exit, MenuExit
return

MenuOpenOverlay:
    OpenOverlay()
return

MenuExit:
    ExitApp
return
