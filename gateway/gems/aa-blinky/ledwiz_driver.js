/**
 * aa-blinky Gem - LED-Wiz HID Driver for JavaScript
 * Part of: Phase 5 Blinky Gem Pivot
 * 
 * Ports the HID logic from backend/services/led_engine/ledwiz_driver.py
 * Target: VID 0xFAFA, PIDs 0x00F0-0x00F7 (8 boards max)
 * 
 * REDLINES (from GEMS_PIVOT_VIGILANCE.md):
 * - DO NOT modify SUPPORTED_IDS hex values (ported as-is from Python)
 * - DO NOT touch mame_config_generator.py JOYCODE
 * - DO NOT hold HID handle while Python LEDEngine is active
 */

import HID from 'node-hid';
import path from 'path';
import fs from 'fs';

// ============================================================================
// CONSTANTS - MUST MATCH LEDWIZ_DRIVER.PY EXACTLY (REDLINE PROTECTED)
// ============================================================================

/**
 * LED-Wiz VID and PID ranges
 * These values MUST NOT be modified - they're hardware constants
 */
const LEDWIZ_VID = 0xFAFA;
const LEDWIZ_PID_START = 0x00F0;
const LEDWIZ_PID_END = 0x00F7;

/**
 * Supported device IDs (VID, PID) tuples
 * REDLINE: Do NOT modify these hex values
 */
const SUPPORTED_IDS = [
    [0xFAFA, 0x00F0],  // LED-Wiz Device 1
    [0xFAFA, 0x00F1],  // LED-Wiz Device 2
    [0xFAFA, 0x00F2],  // LED-Wiz Device 3
    [0xFAFA, 0x00F3],  // LED-Wiz Device 4
    [0xFAFA, 0x00F4],  // LED-Wiz Device 5
    [0xFAFA, 0x00F5],  // LED-Wiz Device 6
    [0xFAFA, 0x00F6],  // LED-Wiz Device 7
    [0xFAFA, 0x00F7],  // LED-Wiz Device 8
];

const CHANNEL_COUNT = 32;
const PACKET_LENGTH = 9;  // HID report length including report ID byte
const WRITE_THROTTLE_MS = 10;  // Minimum ms between writes

// ============================================================================
// PORT CONTENTION LOGIC - Single-Writer Pattern
// ============================================================================

/**
 * Check if Python LED Engine is currently active
 * Prevents dual-writer conflicts on HID handles
 * 
 * @returns {Promise<boolean>} True if Python LEDEngine is active
 */
async function isPythonLEDEngineActive() {
    try {
        // Check for backend LED engine lock file or health endpoint
        const driveRoot = process.env.AA_DRIVE_ROOT || 'A:\\';
        const lockFile = path.join(driveRoot, '.aa', 'state', 'led_engine.lock');

        if (fs.existsSync(lockFile)) {
            // Check if lock file is stale (older than 5 seconds)
            const stats = fs.statSync(lockFile);
            const ageMs = Date.now() - stats.mtimeMs;
            if (ageMs < 5000) {
                console.log('[aa-blinky] Python LEDEngine is active (lock file fresh)');
                return true;
            }
        }

        // Also check backend health endpoint for LED engine status
        try {
            const response = await fetch('http://localhost:8000/api/local/led/status', {
                method: 'GET',
                signal: AbortSignal.timeout(1000)
            });
            if (response.ok) {
                const data = await response.json();
                if (data.engine_active) {
                    console.log('[aa-blinky] Python LEDEngine is active (API confirmed)');
                    return true;
                }
            }
        } catch (e) {
            // Backend not available or endpoint not responding - assume inactive
        }

        return false;
    } catch (e) {
        console.error('[aa-blinky] Error checking Python LED engine:', e.message);
        return false;  // Assume safe if can't check
    }
}

// ============================================================================
// LED-WIZ DRIVER CLASS
// ============================================================================

/**
 * LED-Wiz HID device wrapper
 */
class LEDWizDevice {
    constructor(deviceInfo) {
        this.path = deviceInfo.path;
        this.vendorId = deviceInfo.vendorId;
        this.productId = deviceInfo.productId;
        this.serial = deviceInfo.serialNumber || 'unknown';
        this.product = deviceInfo.product || 'LED-Wiz';
        this.manufacturer = deviceInfo.manufacturer || 'Groovy Game Gear';
        this.deviceId = `${this.vendorId.toString(16).padStart(4, '0')}:${this.productId.toString(16).padStart(4, '0')}`;
        this.channelCount = CHANNEL_COUNT;

        /** @type {HID.HID|null} */
        this._device = null;
        this._lastWriteTime = 0;
        this._lastFrame = new Array(CHANNEL_COUNT).fill(0);
        this._isOpen = false;
    }

    /**
     * Open HID connection to device
     * @returns {boolean} Success
     */
    open() {
        if (this._isOpen) return true;

        try {
            this._device = new HID.HID(this.path);
            this._isOpen = true;
            console.log(`[aa-blinky] Opened device ${this.deviceId} at ${this.path}`);
            return true;
        } catch (e) {
            console.error(`[aa-blinky] Failed to open device ${this.deviceId}:`, e.message);
            return false;
        }
    }

    /**
     * Close HID connection
     */
    close() {
        if (this._device && this._isOpen) {
            try {
                this._device.close();
            } catch (e) {
                // Ignore close errors
            }
            this._device = null;
            this._isOpen = false;
            console.log(`[aa-blinky] Closed device ${this.deviceId}`);
        }
    }

    /**
     * Write LED frame using SBA + PBA protocol
     * @param {number[]} frame - 32-element array of brightness values (0-48)
     * @returns {boolean} Success
     */
    writeFrame(frame) {
        if (!this._isOpen || !this._device) {
            if (!this.open()) return false;
        }

        // Throttle writes
        const now = Date.now();
        const delta = now - this._lastWriteTime;
        if (delta < WRITE_THROTTLE_MS) {
            // Skip write, too fast
            return true;
        }

        try {
            // Ensure frame is 32 elements
            const fullFrame = frame.slice(0, CHANNEL_COUNT);
            while (fullFrame.length < CHANNEL_COUNT) {
                fullFrame.push(0);
            }

            // Build bank bitmasks for SBA command (which outputs are ON)
            let bank0 = 0, bank1 = 0, bank2 = 0, bank3 = 0;
            for (let i = 0; i < 32; i++) {
                if (fullFrame[i] > 0) {
                    if (i < 8) bank0 |= (1 << i);
                    else if (i < 16) bank1 |= (1 << (i - 8));
                    else if (i < 24) bank2 |= (1 << (i - 16));
                    else bank3 |= (1 << (i - 24));
                }
            }

            // Send SBA command: turn outputs ON/OFF + pulse speed (2)
            const sbaPacket = [0x00, bank0, bank1, bank2, bank3, 2, 0, 0, 0];
            this._device.write(sbaPacket.slice(0, PACKET_LENGTH));

            // Send PBA commands: 4 chunks of 8 brightness values
            for (let chunk = 0; chunk < 4; chunk++) {
                const start = chunk * 8;
                const chunkData = fullFrame.slice(start, start + 8);
                // Clamp to LED-Wiz brightness range (0-48)
                const clamped = chunkData.map(v => Math.max(0, Math.min(48, Math.floor(v))));
                // PBA packet: marker + 8 brightness values
                const marker = 0x40 + chunk;  // 0x40, 0x41, 0x42, 0x43
                const pbaPacket = [0x00, marker, ...clamped];
                while (pbaPacket.length < PACKET_LENGTH) pbaPacket.push(0x00);
                this._device.write(pbaPacket.slice(0, PACKET_LENGTH));
            }

            this._lastFrame = fullFrame;
            this._lastWriteTime = Date.now();
            return true;

        } catch (e) {
            console.error(`[aa-blinky] Write failed for ${this.deviceId}:`, e.message);
            this.close();
            return false;
        }
    }

    /**
     * Turn all outputs off
     * @returns {boolean} Success
     */
    allOff() {
        return this.writeFrame(new Array(CHANNEL_COUNT).fill(0));
    }

    /**
     * Set a single port brightness
     * @param {number} port - Port number (1-32)
     * @param {number} intensity - Brightness (0-48)
     * @returns {boolean} Success
     */
    setPort(port, intensity) {
        if (port < 1 || port > CHANNEL_COUNT) return false;
        const frame = [...this._lastFrame];
        frame[port - 1] = Math.max(0, Math.min(48, intensity));
        return this.writeFrame(frame);
    }

    /**
     * Get device info
     * @returns {object} Device information
     */
    getInfo() {
        return {
            deviceId: this.deviceId,
            vendorId: `0x${this.vendorId.toString(16)}`,
            productId: `0x${this.productId.toString(16)}`,
            serial: this.serial,
            product: this.product,
            manufacturer: this.manufacturer,
            path: this.path,
            isOpen: this._isOpen
        };
    }
}

// ============================================================================
// DISCOVERY AND MANAGEMENT
// ============================================================================

/** @type {LEDWizDevice[]} */
let _discoveredDevices = [];

/**
 * Discover all connected LED-Wiz devices
 * @returns {Promise<LEDWizDevice[]>} Array of discovered devices
 */
async function discover() {
    // Check for port contention first
    if (await isPythonLEDEngineActive()) {
        console.log('[aa-blinky] Skipping discovery - Python LEDEngine is active');
        return [];
    }

    try {
        const allDevices = HID.devices();
        const ledWizDevices = allDevices.filter(d => {
            const vid = d.vendorId;
            const pid = d.productId;
            return SUPPORTED_IDS.some(([v, p]) => v === vid && p === pid);
        });

        _discoveredDevices = ledWizDevices.map(info => new LEDWizDevice(info));

        console.log(`[aa-blinky] Discovered ${_discoveredDevices.length} LED-Wiz device(s)`);
        return _discoveredDevices;

    } catch (e) {
        console.error('[aa-blinky] Discovery failed:', e.message);
        return [];
    }
}

/**
 * Get all discovered devices
 * @returns {LEDWizDevice[]}
 */
function getDevices() {
    return _discoveredDevices;
}

/**
 * Get device by index (0-based)
 * @param {number} index - Device index
 * @returns {LEDWizDevice|null}
 */
function getDevice(index) {
    return _discoveredDevices[index] || null;
}

/**
 * Close all open device handles
 */
function closeAll() {
    for (const device of _discoveredDevices) {
        device.close();
    }
}

// ============================================================================
// GEM METADATA
// ============================================================================

export const gemInfo = {
    name: 'aa-blinky',
    version: '1.0.0',
    description: 'LED-Wiz HID driver for JavaScript (Blinky Gem)',
    author: 'Arcade Assistant',
    created: '2026-02-04',
    phase: 'Phase 5 Blinky Gem Pivot'
};

// ============================================================================
// EXPORTS
// ============================================================================

export {
    // Constants (read-only reference)
    SUPPORTED_IDS,
    LEDWIZ_VID,
    CHANNEL_COUNT,

    // Classes
    LEDWizDevice,

    // Discovery
    discover,
    getDevices,
    getDevice,
    closeAll,

    // Port contention
    isPythonLEDEngineActive
};

export default {
    gemInfo,
    discover,
    getDevices,
    getDevice,
    closeAll,
    isPythonLEDEngineActive,
    LEDWizDevice,
    SUPPORTED_IDS,
    LEDWIZ_VID,
    CHANNEL_COUNT
};
