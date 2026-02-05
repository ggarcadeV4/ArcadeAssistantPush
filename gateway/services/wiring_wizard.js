/**
 * Wiring Wizard Service
 * Part of: Phase 5.5 - Wiring Wizard Engine
 * 
 * Provides LED calibration workflow for mapping physical buttons to LED-Wiz ports.
 * Uses the aa-blinky gem's blinkSinglePort primitive for visual feedback.
 * 
 * Workflow:
 * 1. Start wizard session
 * 2. For each port, blink the LED and wait for user to press corresponding button
 * 3. Build button-to-port mapping
 * 4. Save mapping to led_channels.json
 * 
 * Persistence: configs/ledblinky/led_channels.json (respects AA_DRIVE_ROOT)
 */

import fs from 'fs';
import path from 'path';
import { EventEmitter } from 'events';
import * as blinky from '../gems/aa-blinky/index.js';

// ============================================================================
// CONFIGURATION
// ============================================================================

const LED_CHANNELS_FILENAME = 'led_channels.json';

/**
 * Get path to led_channels.json (respects AA_DRIVE_ROOT)
 * @returns {string} Absolute path to led_channels.json
 */
function getLedChannelsPath() {
    const driveRoot = process.env.AA_DRIVE_ROOT || 'A:\\';
    return path.join(driveRoot, 'configs', 'ledblinky', LED_CHANNELS_FILENAME);
}

// ============================================================================
// WIZARD STATE
// ============================================================================

class WiringWizard extends EventEmitter {
    constructor() {
        super();

        /** @type {boolean} */
        this.isActive = false;

        /** @type {number|null} */
        this.currentBlinkingPort = null;

        /** @type {object} */
        this.buttonToPortMap = {};

        /** @type {number} */
        this.totalPorts = 32;  // Default, can be adjusted based on device count

        /** @type {number} */
        this.currentStep = 0;

        /** @type {string[]} */
        this.buttonOrder = [];  // Order of buttons to map

        /** @type {string|null} */
        this.sessionId = null;
    }

    /**
     * Start a new wiring wizard session
     * @param {object} options - Session options
     * @param {string[]} options.buttons - List of button IDs to map (e.g., ['p1.button1', 'p1.button2', ...])
     * @param {number} [options.numPlayers=2] - Number of players (affects button count)
     * @returns {Promise<object>} Session info
     */
    async start(options = {}) {
        if (this.isActive) {
            return { error: 'Wizard session already active', sessionId: this.sessionId };
        }

        // Initialize blinky
        const status = await blinky.initialize();
        if (!status.ready) {
            return {
                error: 'LED-Wiz not available',
                reason: status.reason || 'no_devices',
                devices: status.devices
            };
        }

        // Generate default button order if not provided
        const numPlayers = options.numPlayers || 2;
        this.buttonOrder = options.buttons || this._generateDefaultButtonOrder(numPlayers);
        this.totalPorts = this.buttonOrder.length;

        // Reset state
        this.isActive = true;
        this.currentStep = 0;
        this.buttonToPortMap = {};
        this.currentBlinkingPort = null;
        this.sessionId = `wizard-${Date.now()}`;

        console.log(`[WiringWizard] Started session ${this.sessionId} with ${this.totalPorts} ports`);

        this.emit('started', {
            sessionId: this.sessionId,
            totalPorts: this.totalPorts,
            buttons: this.buttonOrder
        });

        return {
            sessionId: this.sessionId,
            totalPorts: this.totalPorts,
            buttons: this.buttonOrder,
            ready: true
        };
    }

    /**
     * Generate default button order for a given number of players
     * @param {number} numPlayers
     * @returns {string[]}
     */
    _generateDefaultButtonOrder(numPlayers) {
        const buttons = [];
        for (let player = 1; player <= numPlayers; player++) {
            // 8 buttons per player + start + coin
            for (let btn = 1; btn <= 8; btn++) {
                buttons.push(`p${player}.button${btn}`);
            }
            buttons.push(`p${player}.start`);
            buttons.push(`p${player}.coin`);
        }
        return buttons;
    }

    /**
     * Blink the next port in sequence
     * @returns {Promise<object>} Current state { port, buttonId, step, total }
     */
    async blinkNext() {
        if (!this.isActive) {
            return { error: 'No active wizard session' };
        }

        if (this.currentStep >= this.totalPorts) {
            return { error: 'All ports mapped', complete: true };
        }

        const portId = this.currentStep + 1;  // 1-based port ID
        const buttonId = this.buttonOrder[this.currentStep];

        this.currentBlinkingPort = portId;

        // Blink the port
        await blinky.blinkSinglePort(portId);

        this.emit('blinking', {
            port: portId,
            buttonId,
            step: this.currentStep + 1,
            total: this.totalPorts
        });

        return {
            port: portId,
            buttonId,
            step: this.currentStep + 1,
            total: this.totalPorts,
            instruction: `Press the button for "${buttonId}"`
        };
    }

    /**
     * Record a button press for the current blinking port
     * @param {string} buttonId - Button ID that was pressed
     * @param {number} [portOverride] - Optional port override (if user is manually specifying)
     * @returns {object} Result
     */
    recordButtonPress(buttonId, portOverride = null) {
        if (!this.isActive) {
            return { error: 'No active wizard session' };
        }

        const port = portOverride || this.currentBlinkingPort;
        if (!port) {
            return { error: 'No active blinking port' };
        }

        // Record the mapping
        this.buttonToPortMap[buttonId] = port;

        console.log(`[WiringWizard] Mapped ${buttonId} -> port ${port}`);

        this.emit('mapped', {
            buttonId,
            port,
            step: this.currentStep + 1,
            total: this.totalPorts
        });

        // Advance to next step
        this.currentStep++;
        this.currentBlinkingPort = null;

        if (this.currentStep >= this.totalPorts) {
            return {
                success: true,
                complete: true,
                map: this.buttonToPortMap
            };
        }

        return {
            success: true,
            complete: false,
            remaining: this.totalPorts - this.currentStep
        };
    }

    /**
     * Skip the current port (don't map anything to it)
     * @returns {object} Result
     */
    skip() {
        if (!this.isActive) {
            return { error: 'No active wizard session' };
        }

        console.log(`[WiringWizard] Skipped port ${this.currentBlinkingPort}`);

        this.currentStep++;
        this.currentBlinkingPort = null;

        if (this.currentStep >= this.totalPorts) {
            return { success: true, complete: true };
        }

        return {
            success: true,
            complete: false,
            remaining: this.totalPorts - this.currentStep
        };
    }

    /**
     * Get current wizard state
     * @returns {object}
     */
    getState() {
        return {
            isActive: this.isActive,
            sessionId: this.sessionId,
            currentPort: this.currentBlinkingPort,
            currentStep: this.currentStep,
            totalPorts: this.totalPorts,
            mappedCount: Object.keys(this.buttonToPortMap).length,
            buttonToPortMap: { ...this.buttonToPortMap }
        };
    }

    /**
     * Save the current mapping to led_channels.json
     * @returns {Promise<object>} Result { success, path }
     */
    async save() {
        const filePath = getLedChannelsPath();
        const dir = path.dirname(filePath);

        try {
            // Ensure directory exists
            fs.mkdirSync(dir, { recursive: true });

            // Build the full config
            const config = {
                version: '1.0',
                created: new Date().toISOString(),
                created_by: 'WiringWizard',
                session_id: this.sessionId,
                button_to_port: this.buttonToPortMap,
                // Also save the reverse mapping for convenience
                port_to_button: Object.fromEntries(
                    Object.entries(this.buttonToPortMap).map(([btn, port]) => [port, btn])
                )
            };

            // Write atomically
            const tmpPath = filePath + '.tmp';
            fs.writeFileSync(tmpPath, JSON.stringify(config, null, 2), 'utf-8');
            fs.renameSync(tmpPath, filePath);

            console.log(`[WiringWizard] Saved mapping to ${filePath}`);

            this.emit('saved', { path: filePath, map: this.buttonToPortMap });

            return { success: true, path: filePath };

        } catch (e) {
            console.error('[WiringWizard] Failed to save:', e.message);
            return { success: false, error: e.message };
        }
    }

    /**
     * Load existing mapping from led_channels.json
     * @returns {object|null} Loaded config or null
     */
    load() {
        const filePath = getLedChannelsPath();

        try {
            if (!fs.existsSync(filePath)) {
                return null;
            }

            const content = fs.readFileSync(filePath, 'utf-8');
            const config = JSON.parse(content);

            console.log(`[WiringWizard] Loaded mapping from ${filePath}`);
            return config;

        } catch (e) {
            console.error('[WiringWizard] Failed to load:', e.message);
            return null;
        }
    }

    /**
     * Cancel the current wizard session
     */
    cancel() {
        if (!this.isActive) return;

        console.log(`[WiringWizard] Cancelled session ${this.sessionId}`);

        // Turn off all LEDs
        blinky.allOff();

        this.emit('cancelled', { sessionId: this.sessionId });

        this.isActive = false;
        this.sessionId = null;
        this.currentBlinkingPort = null;
        this.currentStep = 0;
        this.buttonToPortMap = {};
    }

    /**
     * Complete the wizard and save
     * @returns {Promise<object>}
     */
    async finish() {
        if (!this.isActive) {
            return { error: 'No active wizard session' };
        }

        // Turn off all LEDs
        blinky.allOff();

        // Save the mapping
        const saveResult = await this.save();

        this.emit('finished', {
            sessionId: this.sessionId,
            map: this.buttonToPortMap,
            saved: saveResult.success
        });

        // Reset state
        const result = {
            success: saveResult.success,
            path: saveResult.path,
            map: { ...this.buttonToPortMap },
            mappedCount: Object.keys(this.buttonToPortMap).length
        };

        this.isActive = false;
        this.sessionId = null;

        return result;
    }
}

// ============================================================================
// SINGLETON INSTANCE
// ============================================================================

const wizard = new WiringWizard();

// ============================================================================
// EXPORTS
// ============================================================================

export {
    wizard,
    WiringWizard,
    getLedChannelsPath
};

export default wizard;
