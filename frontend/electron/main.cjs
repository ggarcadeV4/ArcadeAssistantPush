/**
 * Dewey HUD - Electron Overlay for Arcade Assistant
 *
 * Creates a frameless, transparent, always-on-top overlay window.
 * - F9: Toggle visibility (global shortcut path)
 * - Shift+F9: Quit the overlay
 * - Backend hotkey bridge fallback: /ws/hotkey events can also toggle the HUD
 *
 * Golden-image note: this overlay launches separately from start-aa.bat.
 * Duplication readiness still requires it to load successfully against the shipped gateway build.
 */

const { app, BrowserWindow, globalShortcut, screen, session } = require('electron');
const WebSocket = require('ws');

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
    try { console.log('[Dewey] Overlay already running; exiting duplicate process'); } catch { }
    app.quit();
    process.exit(0);
}

// ============================================================================
// CONFIGURATION
// ============================================================================

const GATEWAY_URL = 'http://127.0.0.1:8787/assistants?agent=dewey&mode=overlay';
const WINDOW_WIDTH = 420;
const WINDOW_HEIGHT = 700;
const WINDOW_OPACITY = 0.95;
const MARGIN_RIGHT = 24;
const MARGIN_BOTTOM = 48;
const MIN_TOGGLE_INTERVAL_MS = 120;
const CROSS_SOURCE_DUPLICATE_MS = 400;
const WS_PING_INTERVAL_MS = 15000;
const OVERLAY_CMD_PARAM = '__overlay_cmd';

// ============================================================================
// STATE
// ============================================================================

let win = null;
let isVisible = true;
let isExpanded = false;
let lastToggleAt = 0;
let lastGlobalShortcutAt = 0;
let lastBackendWsAt = 0;
let hotkeyWs = null;
let hotkeyReconnectTimer = null;
let hotkeyReconnectDelay = 2000;
let hotkeyPingTimer = null;
let pendingShowTimer = null;

// ============================================================================
// WINDOW HELPERS
// ============================================================================

function getTargetDisplay() {
    try {
        const cursorPoint = screen.getCursorScreenPoint();
        return screen.getDisplayNearestPoint(cursorPoint) || screen.getPrimaryDisplay();
    } catch {
        return screen.getPrimaryDisplay();
    }
}

function getWorkArea() {
    return getTargetDisplay().workArea;
}

function getCompactBounds() {
    const area = getWorkArea();
    return {
        x: area.x + area.width - WINDOW_WIDTH - MARGIN_RIGHT,
        y: area.y + area.height - WINDOW_HEIGHT - MARGIN_BOTTOM,
        width: WINDOW_WIDTH,
        height: WINDOW_HEIGHT,
    };
}

function applyCompactBounds() {
    if (!win || win.isDestroyed()) return;
    const bounds = getCompactBounds();
    win.setBounds(bounds, true);
    win.setResizable(false);
    isExpanded = false;
}

function applyExpandedBounds() {
    if (!win || win.isDestroyed()) return;
    const area = getWorkArea();
    win.setBounds({ x: area.x, y: area.y, width: area.width, height: area.height }, true);
    win.setResizable(true);
    isExpanded = true;
}

function forceRevealWindow() {
    if (!win || win.isDestroyed()) return;
    try {
        win.setAlwaysOnTop(true, 'screen-saver');
        win.show();
        if (typeof win.moveTop === 'function') win.moveTop();
        // Intentionally NOT calling win.focus() — avoid stealing keyboard
        // focus from the active game/emulator.
    } catch (error) {
        try { console.warn('[Dewey] forceRevealWindow failed:', error); } catch { }
    }
}

function resetToCompactDeweyShell() {
    if (pendingShowTimer) {
        clearTimeout(pendingShowTimer);
        pendingShowTimer = null;
    }
    applyCompactBounds();
    setTimeout(() => {
        if (win && !win.isDestroyed()) {
            win.loadURL(GATEWAY_URL);
        }
    }, 50);
}

// ============================================================================
// WINDOW CREATION
// ============================================================================

function createWindow() {
    const bounds = getCompactBounds();

    win = new BrowserWindow({
        width: bounds.width,
        height: bounds.height,
        x: bounds.x,
        y: bounds.y,
        frame: false,
        transparent: true,
        alwaysOnTop: true,
        skipTaskbar: true,
        resizable: false,
        hasShadow: false,
        opacity: WINDOW_OPACITY,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
        },
    });

    // Float above fullscreen apps when possible.
    win.setAlwaysOnTop(true, 'screen-saver');
    // Keep visible across workspaces/fullscreen contexts.
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

    // Load Gateway in overlay mode.
    win.loadURL(GATEWAY_URL);

    // Suppress navigation errors (Gateway not running yet).
    win.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
        try { console.log(`[Dewey] Load failed: ${errorDescription} - retrying in 3s...`); } catch { }
        setTimeout(() => {
            if (win && !win.isDestroyed()) {
                win.loadURL(GATEWAY_URL);
            }
        }, 3000);
    });

    win.webContents.on('will-navigate', (event, targetUrl) => {
        if (handleOverlayCommand(targetUrl)) {
            event.preventDefault();
        }
    });

    win.webContents.setWindowOpenHandler(({ url }) => {
        if (handleOverlayCommand(url)) {
            return { action: 'deny' };
        }
        return { action: 'allow' };
    });

    win.on('closed', () => {
        win = null;
    });

    try { console.log('[Dewey] HUD overlay created - F9 to toggle, Shift+F9 to quit'); } catch { }
}

function getHotkeyWsUrl() {
    if (process.env.DEWEY_HOTKEY_WS_URL) {
        return process.env.DEWEY_HOTKEY_WS_URL;
    }
    const parsed = new URL(GATEWAY_URL);
    const wsProto = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
    // Gateway /ws/hotkey now rejects anonymous connections (close code 4401).
    // Identify this sidecar so the hotkey bridge accepts the socket and
    // forwards backend hotkey_pressed events for F9 summon.
    const deviceId =
        (process.env.AA_DEVICE_ID || '').trim() || 'dewey-overlay';
    const params = new URLSearchParams({
        device: deviceId,
        panel: 'dewey_overlay'
    });
    return `${wsProto}//${parsed.host}/ws/hotkey?${params.toString()}`;
}

function getToggleSourceKind(source) {
    if ((source || '').startsWith('global_shortcut:')) return 'global_shortcut';
    if ((source || '').startsWith('backend_ws:')) return 'backend_ws';
    if (source === 'overlay_close_button') return 'overlay_close_button';
    return 'other';
}

function toggleHud(source) {
    if (!win || win.isDestroyed()) return;

    const now = Date.now();
    const sourceKind = getToggleSourceKind(source);

    if (now - lastToggleAt < MIN_TOGGLE_INTERVAL_MS) {
        try { console.log('[Dewey] Toggle ignored (min-interval) source=' + source); } catch { }
        return;
    }

    // Prefer Electron's local shortcut path when it fires; the backend WS
    // event is usually an echo of the same physical F9 press.
    if (
        sourceKind === 'backend_ws' &&
        now - lastGlobalShortcutAt < CROSS_SOURCE_DUPLICATE_MS
    ) {
        try { console.log('[Dewey] Toggle ignored (duplicate backend echo) source=' + source); } catch { }
        return;
    }

    // Keep the reverse guard in case event ordering flips under load.
    if (
        sourceKind === 'global_shortcut' &&
        now - lastBackendWsAt < CROSS_SOURCE_DUPLICATE_MS
    ) {
        try { console.log('[Dewey] Toggle ignored (duplicate global echo) source=' + source); } catch { }
        return;
    }

    lastToggleAt = now;
    if (sourceKind === 'global_shortcut') lastGlobalShortcutAt = now;
    if (sourceKind === 'backend_ws') lastBackendWsAt = now;

    if (isVisible) {
        win.setIgnoreMouseEvents(true);
        win.hide();
        isVisible = false;
        // If we were expanded (e.g., Console Wizard), reset to compact Dewey
        // shell so next reveal is clean.
        if (isExpanded) {
            resetToCompactDeweyShell();
        }
        try { console.log('[Dewey] HUD hidden (source=' + source + ', wasExpanded=' + isExpanded + ')'); } catch { }
    } else {
        // If expanded, reset to compact Dewey first (will reload URL).
        if (isExpanded) {
            resetToCompactDeweyShell();
        }
        win.setIgnoreMouseEvents(false);
        win.setOpacity(WINDOW_OPACITY);
        applyCompactBounds();
        pendingShowTimer = setTimeout(() => {
            pendingShowTimer = null;
            if (!win || win.isDestroyed()) return;
            forceRevealWindow();
            isVisible = true;
            try { console.log('[Dewey] HUD shown (source=' + source + ')'); } catch { }
        }, 50);
    }
}

function handleOverlayCommand(targetUrl) {
    let parsed = null;
    try {
        parsed = new URL(targetUrl);
    } catch {
        return false;
    }

    const cmd = (parsed.searchParams.get(OVERLAY_CMD_PARAM) || '').toLowerCase();
    if (!cmd) {
        return false;
    }

    if (cmd === 'hide') {
        if (isVisible) {
            toggleHud('overlay_close_button');
        }
        // Return to compact Dewey shell for next reveal.
        resetToCompactDeweyShell();
        return true;
    }

    if (cmd === 'expand') {
        const target = parsed.searchParams.get('target') || '/assistants';
        const targetUrlExpanded = new URL(target, `${parsed.protocol}//${parsed.host}`).toString();

        applyExpandedBounds();
        if (win && !win.isDestroyed()) {
            win.setOpacity(WINDOW_OPACITY);
            win.setIgnoreMouseEvents(false);
            win.loadURL(targetUrlExpanded);
            if (typeof win.moveTop === 'function') win.moveTop();
            win.focus();
            isVisible = true;
            try { console.log(`[Dewey] Expanded window handoff -> ${targetUrlExpanded}`); } catch { }
        }
        return true;
    }

    if (cmd === 'quit') {
        app.quit();
        return true;
    }

    return false;
}

function scheduleHotkeyReconnect() {
    if (hotkeyReconnectTimer) return;
    hotkeyReconnectTimer = setTimeout(() => {
        hotkeyReconnectTimer = null;
        connectHotkeyBridge();
    }, hotkeyReconnectDelay);
    // Exponential backoff: 2s -> 4s -> 8s -> 16s -> 30s cap
    hotkeyReconnectDelay = Math.min(hotkeyReconnectDelay * 2, 30000);
}

function connectHotkeyBridge() {
    const wsUrl = getHotkeyWsUrl();
    try {
        hotkeyWs = new WebSocket(wsUrl);
    } catch (err) {
        try { console.error(`[Dewey] Hotkey WS connect failed (${wsUrl}): ${err.message}`); } catch { }
        scheduleHotkeyReconnect();
        return;
    }

    hotkeyWs.on('open', () => {
        try { console.log(`[Dewey] Hotkey WS connected: ${wsUrl}`); } catch { }
        // Reset backoff on successful connection
        hotkeyReconnectDelay = 2000;
        // Start heartbeat to detect dead connections
        if (hotkeyPingTimer) clearInterval(hotkeyPingTimer);
        hotkeyPingTimer = setInterval(() => {
            if (hotkeyWs && hotkeyWs.readyState === WebSocket.OPEN) {
                try { hotkeyWs.send('ping'); } catch { }
            }
        }, WS_PING_INTERVAL_MS);
    });

    hotkeyWs.on('message', (raw) => {
        let msg = null;
        try {
            msg = JSON.parse(raw.toString());
        } catch {
            return;
        }
        if (msg?.type === 'hotkey_pressed') {
            toggleHud(`backend_ws:${msg.key || 'unknown'}`);
        }
    });

    hotkeyWs.on('close', () => {
        try { console.log('[Dewey] Hotkey WS closed'); } catch { }
        if (hotkeyPingTimer) { clearInterval(hotkeyPingTimer); hotkeyPingTimer = null; }
        scheduleHotkeyReconnect();
    });

    hotkeyWs.on('error', (err) => {
        try { console.error(`[Dewey] Hotkey WS error: ${err.message}`); } catch { }
    });
}

// ============================================================================
// HOTKEYS
// ============================================================================

function registerShortcuts() {
    const f9Registered = globalShortcut.register('F9', () => {
        toggleHud('global_shortcut:F9');
    });

    if (!f9Registered) {
        try { console.error('[Dewey] Failed to register F9 global shortcut'); } catch { }
    }

    const shiftF9Registered = globalShortcut.register('Shift+F9', () => {
        try { console.log('[Dewey] Shift+F9 - quitting overlay'); } catch { }
        app.quit();
    });

    if (!shiftF9Registered) {
        try { console.error('[Dewey] Failed to register Shift+F9 global shortcut'); } catch { }
    }
}

// ============================================================================
// APP LIFECYCLE
// ============================================================================

app.on('second-instance', () => {
    if (!win || win.isDestroyed()) return;

    resetToCompactDeweyShell();
    win.setOpacity(WINDOW_OPACITY);
    win.setIgnoreMouseEvents(false);
    if (typeof win.moveTop === 'function') win.moveTop();
    win.focus();
    isVisible = true;
    try { console.log('[Dewey] Existing overlay instance activated and reset to Dewey'); } catch { }
});

app.whenReady().then(() => {
    // ── Microphone Permission Handler ───────────────────────────────────────────────
    // Electron blocks getUserMedia() by default. This handler grants mic/camera
    // access so LoRa's voice recording can work inside the renderer.
    // We grant only media-related permissions; all others are denied.
    session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
        const ALLOWED_PERMISSIONS = ['media', 'microphone', 'audioCapture', 'speaker'];
        const granted = ALLOWED_PERMISSIONS.includes(permission);
        if (granted) {
            try { console.log(`[Dewey] Permission granted: ${permission}`); } catch { }
        } else {
            try { console.log(`[Dewey] Permission denied: ${permission}`); } catch { }
        }
        callback(granted);
    });

    createWindow();
    registerShortcuts();
    connectHotkeyBridge();
});

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
    if (pendingShowTimer) clearTimeout(pendingShowTimer);
    pendingShowTimer = null;
    if (hotkeyReconnectTimer) clearTimeout(hotkeyReconnectTimer);
    hotkeyReconnectTimer = null;
    if (hotkeyPingTimer) { clearInterval(hotkeyPingTimer); hotkeyPingTimer = null; }
    if (hotkeyWs) {
        try { hotkeyWs.close(); } catch { }
    }
    hotkeyWs = null;
});

app.on('window-all-closed', () => {
    app.quit();
});
