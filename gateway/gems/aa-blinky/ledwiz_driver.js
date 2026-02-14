/**
 * aa-blinky Gem - LED-Wiz Shim Client for JavaScript
 * Part of: Phase 5 Blinky Gem Pivot
 * 
 * Replaces node-hid with a Named Pipe client that talks to the Python LED-Wiz Direct driver.
 * This avoids the "Imposter Device" phenomenon and event loop blocking.
 */

import net from 'net';
import path from 'path';
import fs from 'fs';

// ============================================================================
// GEM METADATA
// ============================================================================

export const gemInfo = {
    name: 'aa-blinky',
    version: '2.0.0',
    description: 'LED-Wiz driver via Named Pipe (Python ctypes backend)',
    author: 'Arcade Assistant',
    created: '2026-02-05',
    phase: 'Phase 5 Blinky Gem Pivot',
    dependencies: []  // No longer depends on node-hid
};

// ============================================================================
// CONSTANTS
// ============================================================================

const PIPE_NAME = '\\\\.\\pipe\\ArcadeLED';
const CHANNEL_COUNT_INTERNAL = 32;
const WRITE_THROTTLE_MS = 10;

// ============================================================================
// LEGACY STUB: LEDWizDevice class for compatibility
// ============================================================================

export class LEDWizDevice {
    constructor(deviceId = 'shim', product = 'LED-Wiz Shim') {
        this.deviceId = deviceId;
        this.product = product;
    }

    writeFrame(frame) {
        return globalClient.writeFrame(1, frame);
    }

    allOff() {
        return globalClient.sendCommand('ALL_OFF');
    }

    setPort(port, val) {
        return globalClient.setPort(port, val);
    }

    getInfo() {
        return { deviceId: this.deviceId, product: this.product };
    }
}

// ============================================================================
// SHIM CLIENT
// ============================================================================

class LEDWizShimClient {
    constructor() {
        this.client = null;
        this.connected = false;
        this._lastWriteTime = 0;
        this._lastFrame = new Array(CHANNEL_COUNT_INTERNAL).fill(0);
    }

    connect() {
        if (this.connected) return Promise.resolve(true);

        return new Promise((resolve) => {
            console.log(`[aa-blinky] Connecting to shim pipe: ${PIPE_NAME}`);
            this.client = net.connect(PIPE_NAME, () => {
                console.log('[aa-blinky] Connected to LED-Wiz Shim');
                this.connected = true;
                resolve(true);
            });

            this.client.on('error', (err) => {
                console.error('[aa-blinky] Shim pipe error:', err.message);
                this.connected = false;
                this.client = null;
                resolve(false);
            });

            this.client.on('end', () => {
                console.log('[aa-blinky] Shim pipe disconnected');
                this.connected = false;
                this.client = null;
            });
        });
    }

    sendCommand(cmd) {
        if (!this.connected) {
            this.connect().then(success => {
                if (success) this._write(cmd);
            });
            return;
        }
        this._write(cmd);
    }

    _write(cmd) {
        try {
            this.client.write(cmd + '\n');
        } catch (e) {
            console.error('[aa-blinky] Failed to write to shim:', e.message);
            this.connected = false;
        }
    }

    /**
     * Write LED frame using shim SBA + PBA protocol
     * @param {number} boardId - 1-based board ID
     * @param {number[]} frame - 32-element array of brightness values (0-48)
     */
    writeFrame(boardId, frame) {
        const now = Date.now();
        if (now - this._lastWriteTime < WRITE_THROTTLE_MS) return;

        // SBA Command
        let bank0 = 0, bank1 = 0, bank2 = 0, bank3 = 0;
        for (let i = 0; i < 32; i++) {
            if (frame[i] > 0) {
                if (i < 8) bank0 |= (1 << i);
                else if (i < 16) bank1 |= (1 << (i - 8));
                else if (i < 24) bank2 |= (1 << (i - 16));
                else bank3 |= (1 << (i - 24));
            }
        }
        this.sendCommand(`SBA ${boardId} ${bank0} ${bank1} ${bank2} ${bank3} 2`);

        // PBA Chunks
        for (let chunk = 0; chunk < 4; chunk++) {
            const start = chunk * 8;
            const chunkData = frame.slice(start, start + 8);
            const pbaVals = chunkData.map(v => Math.max(0, Math.min(48, Math.floor(v)))).join(' ');
            this.sendCommand(`PBA_CHUNK ${boardId} ${chunk} ${pbaVals}`);
        }

        this._lastFrame = [...frame];
        this._lastWriteTime = now;
    }

    setPort(port, brightness) {
        // Simple mapping: port 1-32 = board 1, 33-64 = board 2, etc.
        const boardId = Math.floor((port - 1) / CHANNEL_COUNT_INTERNAL) + 1;
        const localPort = ((port - 1) % CHANNEL_COUNT_INTERNAL) + 1;

        // Use the last known frame to avoid turning off other LEDs
        const frame = [...this._lastFrame];
        frame[localPort - 1] = brightness;
        this.writeFrame(boardId, frame);
    }
}

const globalClient = new LEDWizShimClient();

// ============================================================================
// EXPORTS (Matching original driver interface where possible)
// ============================================================================

export async function discover() {
    // In shim model, discovery is background.
    // We just ensure daemon is started (backend handles this usually, but we can too)
    await globalClient.connect();
    return [{ deviceId: 'shim', product: 'LED-Wiz Shim' }];
}

export function getDevices() {
    return [{
        writeFrame: (frame) => globalClient.writeFrame(1, frame),
        allOff: () => globalClient.sendCommand('ALL_OFF'),
        setPort: (port, val) => globalClient.setPort(port, val),
        getInfo: () => ({ deviceId: 'shim', product: 'LED-Wiz Shim' })
    }];
}

export function getDevice(index) {
    if (index === 0) return getDevices()[0];
    return null;
}

export function closeAll() {
    if (globalClient.client) {
        globalClient.client.end();
    }
}

export async function isPythonLEDEngineActive() {
    // With the shim, we might allow multiple clients if the shim handles it,
    // but typically we still want to avoid contention.
    return false; // Shim allows multiplexing
}

export const SUPPORTED_IDS = [[0xFAFA, 0x00F0]];
export const LEDWIZ_VID = 0xFAFA;
export { CHANNEL_COUNT_INTERNAL as CHANNEL_COUNT };

export default {
    discover,
    getDevices,
    getDevice,
    closeAll,
    isPythonLEDEngineActive,
    SUPPORTED_IDS,
    LEDWIZ_VID,
    CHANNEL_COUNT: CHANNEL_COUNT_INTERNAL
};
