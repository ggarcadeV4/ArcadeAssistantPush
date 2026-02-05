/**
 * aa-blinky Gem - Entry Point
 * Part of: Phase 5 Blinky Gem Pivot
 * 
 * LED-Wiz HID driver and genre profile integration for arcade cabinet LEDs.
 * Provides:
 * - LED-Wiz device discovery and control
 * - Genre-based LED profile application
 * - Port contention detection (single-writer pattern)
 * 
 * REDLINES (from GEMS_PIVOT_VIGILANCE.md):
 * - SUPPORTED_IDS hex values - DO NOT MODIFY
 * - mame_config_generator.py JOYCODE - DO NOT TOUCH
 */

import {
    gemInfo as driverGemInfo,
    discover,
    getDevices,
    getDevice,
    closeAll,
    isPythonLEDEngineActive,
    LEDWizDevice,
    SUPPORTED_IDS,
    LEDWIZ_VID,
    CHANNEL_COUNT
} from './ledwiz_driver.js';

import {
    loadProfiles,
    reloadProfiles,
    listProfiles,
    getProfile,
    getProfileForGenre,
    getLEDProfileForGenre,
    getButtonLayout,
    getEmulatorMapping,
    ledProfileToFrame
} from './genre_profiles.js';

// ============================================================================
// GEM METADATA
// ============================================================================

export const gemInfo = {
    name: 'aa-blinky',
    version: '1.0.0',
    description: 'LED-Wiz HID driver and genre profile integration for arcade cabinet LEDs',
    author: 'Arcade Assistant',
    created: '2026-02-04',
    phase: 'Phase 5 Blinky Gem Pivot',
    dependencies: ['node-hid']
};

// ============================================================================
// SPEAKING MODE STATE
// ============================================================================

let speakingTimer = null;
let speakingStartTime = 0;

/**
 * Speaking mode animation - P1/P2 Start buttons "breathe"
 * Uses 10Hz timer (100ms interval) with sinusoidal brightness oscillation
 * 
 * @param {boolean} enabled - true to start, false to stop
 */
export function speakingMode(enabled) {
    if (enabled) {
        // Guard: only one timer at a time
        if (speakingTimer !== null) {
            console.log('[aa-blinky] speakingMode already active, ignoring');
            return;
        }

        console.log('[aa-blinky] Starting speaking mode animation');
        speakingStartTime = Date.now();

        speakingTimer = setInterval(() => {
            const elapsed = (Date.now() - speakingStartTime) / 1000;
            // Sine wave: oscillate between 5 and 48 brightness
            // ~2Hz breathing cycle (full cycle every 0.5 seconds)
            const brightness = Math.round(26.5 + 21.5 * Math.sin(elapsed * 4 * Math.PI));

            // Port 1 = P1 Start, Port 2 = P2 Start (Device 0)
            setPort(1, brightness);
            setPort(2, brightness);
        }, 100); // 10Hz = 100ms interval

    } else {
        if (speakingTimer !== null) {
            console.log('[aa-blinky] Stopping speaking mode animation');
            clearInterval(speakingTimer);
            speakingTimer = null;

            // Turn off the speaking LEDs
            setPort(1, 0);
            setPort(2, 0);
        }
    }
}

// ============================================================================
// HIGH-LEVEL API
// ============================================================================

/**
 * Initialize the Blinky gem - discover devices and load profiles
 * @returns {Promise<object>} Status { devices, profiles, ready }
 */
export async function initialize() {
    // Check port contention
    const pythonActive = await isPythonLEDEngineActive();
    if (pythonActive) {
        console.log('[aa-blinky] Python LEDEngine is active - running in read-only mode');
        return {
            devices: [],
            profiles: listProfiles(),
            ready: false,
            reason: 'python_engine_active'
        };
    }

    // Discover devices
    const devices = await discover();

    // Load profiles
    const profiles = listProfiles();

    return {
        devices: devices.map(d => d.getInfo()),
        profiles,
        ready: devices.length > 0
    };
}

/**
 * Apply a genre profile to all discovered LED-Wiz devices
 * @param {string} genre - Genre name from LaunchBox
 * @param {object} buttonToPort - Mapping of button IDs to LED-Wiz port numbers
 * @returns {boolean} Success
 */
export function applyGenreProfile(genre, buttonToPort = {}) {
    const ledProfile = getLEDProfileForGenre(genre);
    if (!ledProfile) {
        console.log(`[aa-blinky] No LED profile for genre: ${genre}`);
        return false;
    }

    const frame = ledProfileToFrame(ledProfile, buttonToPort);
    const devices = getDevices();

    let success = true;
    for (const device of devices) {
        if (!device.writeFrame(frame)) {
            success = false;
        }
    }

    console.log(`[aa-blinky] Applied genre profile for "${genre}" to ${devices.length} device(s)`);
    return success;
}

/**
 * Set all LEDs to a specific color/brightness
 * @param {number} brightness - Brightness (0-48)
 * @returns {boolean} Success
 */
export function setAllBrightness(brightness) {
    const frame = new Array(CHANNEL_COUNT).fill(Math.max(0, Math.min(48, brightness)));
    const devices = getDevices();

    let success = true;
    for (const device of devices) {
        if (!device.writeFrame(frame)) {
            success = false;
        }
    }

    return success;
}

/**
 * Turn all LEDs off
 * @returns {boolean} Success
 */
export function allOff() {
    const devices = getDevices();
    let success = true;
    for (const device of devices) {
        if (!device.allOff()) {
            success = false;
        }
    }
    return success;
}

/**
 * Set a single port brightness across all devices
 * Port numbers are 1-indexed and span across devices:
 * - Ports 1-32: Device 0
 * - Ports 33-64: Device 1
 * - etc.
 * 
 * @param {number} portId - Port number (1-based)
 * @param {number} brightness - Brightness (0-48)
 * @returns {boolean} Success
 */
export function setPort(portId, brightness) {
    if (portId < 1) return false;

    const devices = getDevices();
    if (devices.length === 0) return false;

    // Determine which device and local port
    const deviceIndex = Math.floor((portId - 1) / CHANNEL_COUNT);
    const localPort = ((portId - 1) % CHANNEL_COUNT) + 1;

    const device = devices[deviceIndex];
    if (!device) return false;

    return device.setPort(localPort, Math.max(0, Math.min(48, brightness)));
}

/**
 * Blink a single port - used by Wiring Wizard for calibration
 * Sequence: ON (48) -> 350ms -> OFF (0) -> 150ms
 * 
 * @param {number} portId - Port number (1-based, spans across devices)
 * @returns {Promise<boolean>} Success
 */
export async function blinkSinglePort(portId) {
    if (portId < 1) return false;

    const devices = getDevices();
    if (devices.length === 0) {
        console.log('[aa-blinky] No devices available for blink');
        return false;
    }

    try {
        // Turn ON at full brightness
        const onSuccess = setPort(portId, 48);
        if (!onSuccess) return false;

        // Wait 350ms (visible blink)
        await new Promise(resolve => setTimeout(resolve, 350));

        // Turn OFF
        const offSuccess = setPort(portId, 0);
        if (!offSuccess) return false;

        // Wait 150ms (debounce between blinks)
        await new Promise(resolve => setTimeout(resolve, 150));

        console.log(`[aa-blinky] Blinked port ${portId}`);
        return true;

    } catch (e) {
        console.error(`[aa-blinky] Blink failed for port ${portId}:`, e.message);
        return false;
    }
}

/**
 * Get status of all devices and profiles
 * @returns {Promise<object>} Status object
 */
export async function getStatus() {
    const pythonActive = await isPythonLEDEngineActive();
    const devices = getDevices();
    const profiles = listProfiles();

    return {
        pythonEngineActive: pythonActive,
        deviceCount: devices.length,
        devices: devices.map(d => d.getInfo()),
        profileCount: profiles.length,
        supportedIds: SUPPORTED_IDS.map(([v, p]) => `${v.toString(16)}:${p.toString(16)}`),
        ready: !pythonActive && devices.length > 0
    };
}

// ============================================================================
// EXPORTS
// ============================================================================

// Re-export everything from submodules for convenience
export {
    // Driver
    discover,
    getDevices,
    getDevice,
    closeAll,
    isPythonLEDEngineActive,
    LEDWizDevice,
    SUPPORTED_IDS,
    LEDWIZ_VID,
    CHANNEL_COUNT,

    // Profiles
    loadProfiles,
    reloadProfiles,
    listProfiles,
    getProfile,
    getProfileForGenre,
    getLEDProfileForGenre,
    getButtonLayout,
    getEmulatorMapping,
    ledProfileToFrame
};

export default {
    gemInfo,

    // High-level API
    initialize,
    applyGenreProfile,
    setAllBrightness,
    allOff,
    setPort,
    blinkSinglePort,
    getStatus,
    speakingMode,

    // Driver
    discover,
    getDevices,
    getDevice,
    closeAll,
    isPythonLEDEngineActive,
    LEDWizDevice,
    SUPPORTED_IDS,
    LEDWIZ_VID,
    CHANNEL_COUNT,

    // Profiles
    loadProfiles,
    reloadProfiles,
    listProfiles,
    getProfile,
    getProfileForGenre,
    getLEDProfileForGenre,
    getButtonLayout,
    getEmulatorMapping,
    ledProfileToFrame
};
