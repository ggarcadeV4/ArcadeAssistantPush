/**
 * Dewey HUD — Electron Overlay for Arcade Assistant
 * Part of: Phase 3 "Gem Architecture"
 *
 * Creates a frameless, transparent, always-on-top overlay window.
 * - F9: Toggle visibility (opacity-based, no focus stealing)
 * - Shift+F9: Quit the overlay
 * - Loads Gateway UI in overlay/concierge mode: http://127.0.0.1:8787/?mode=overlay
 *
 * Focus-steal fix: Uses setOpacity(0)/setIgnoreMouseEvents(true) instead
 * of win.hide()/win.show() to prevent Playnite from reclaiming focus.
 */

const { app, BrowserWindow, globalShortcut, screen } = require('electron');
const path = require('path');

// ============================================================================
// CONFIGURATION
// ============================================================================

const GATEWAY_URL = 'http://127.0.0.1:8787/?mode=overlay';
const WINDOW_WIDTH = 420;
const WINDOW_HEIGHT = 700;
const WINDOW_OPACITY = 0.95;
const MARGIN_RIGHT = 24;
const MARGIN_BOTTOM = 48;

// ============================================================================
// STATE
// ============================================================================

let win = null;
let isVisible = true;

// ============================================================================
// WINDOW CREATION
// ============================================================================

function createWindow() {
    const { width: screenW, height: screenH } = screen.getPrimaryDisplay().workAreaSize;

    win = new BrowserWindow({
        width: WINDOW_WIDTH,
        height: WINDOW_HEIGHT,
        x: screenW - WINDOW_WIDTH - MARGIN_RIGHT,
        y: screenH - WINDOW_HEIGHT - MARGIN_BOTTOM,
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

    // Set always-on-top at 'screen-saver' level to float above fullscreen apps
    win.setAlwaysOnTop(true, 'screen-saver');

    // Load Gateway in overlay/concierge mode
    win.loadURL(GATEWAY_URL);

    // Suppress navigation errors (Gateway not running yet)
    win.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
        console.log(`[Dewey] Load failed: ${errorDescription} — retrying in 3s...`);
        setTimeout(() => {
            if (win && !win.isDestroyed()) {
                win.loadURL(GATEWAY_URL);
            }
        }, 3000);
    });

    win.on('closed', () => {
        win = null;
    });

    console.log('[Dewey] HUD overlay created — F9 to toggle, Shift+F9 to quit');
}

// ============================================================================
// HOTKEYS
// ============================================================================

function registerShortcuts() {
    // F9: Toggle visibility using opacity (NO hide/show — prevents focus stealing)
    globalShortcut.register('F9', () => {
        if (!win || win.isDestroyed()) return;

        if (isVisible) {
            // "Hide" — make transparent and click-through
            win.setOpacity(0);
            win.setIgnoreMouseEvents(true);
            isVisible = false;
            console.log('[Dewey] HUD hidden (opacity=0, click-through)');
        } else {
            // "Show" — restore opacity and accept mouse events
            win.setOpacity(WINDOW_OPACITY);
            win.setIgnoreMouseEvents(false);
            win.focus();
            isVisible = true;
            console.log('[Dewey] HUD shown (opacity restored, interactive)');
        }
    });

    // Shift+F9: Quit the overlay entirely
    globalShortcut.register('Shift+F9', () => {
        console.log('[Dewey] Shift+F9 — quitting overlay');
        app.quit();
    });
}

// ============================================================================
// APP LIFECYCLE
// ============================================================================

app.whenReady().then(() => {
    createWindow();
    registerShortcuts();
});

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
    app.quit();
});
