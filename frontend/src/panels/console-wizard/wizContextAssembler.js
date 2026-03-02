/**
 * wizContextAssembler.js — Builds Diagnosis Mode context payload for WIZ AI calls.
 *
 * 3-tier context:
 *   Tier 1 (always):     timestamp, session
 *   Tier 2 (fetched):    emulator health, emulator list, detected controllers
 *   Tier 3 (static):     AI tool availability, domain scope reminder
 *
 * Stays under 1500 tokens. Console Wizard domain only — no cross-panel bleed.
 */

const ENDPOINTS = {
    health: '/api/local/console_wizard/health',
    emulators: '/api/local/console_wizard/emulators',
    controllers: '/api/local/console/controllers',
};

const PANEL_HEADERS = {
    'Content-Type': 'application/json',
    'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
    'x-panel': 'console-wizard',
    'x-scope': 'state',
};

async function safeFetch(url) {
    try {
        const res = await fetch(url, { headers: PANEL_HEADERS });
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

/**
 * Assembles the context payload for the current session.
 *
 * @returns {Promise<object>} Context object to pass as extraContext to the AI.
 */
export async function assembleWizContext() {
    // Tier 1 — always present
    const ctx = {
        timestamp: new Date().toISOString(),
        panel: 'console-wizard',
        domain: 'console controllers, emulator configs (RetroArch, Dolphin, PCSX2, TeknoParrot)',
    };

    // Tier 2 — fetched in parallel
    const [healthData, emulatorData, controllerData] = await Promise.allSettled([
        safeFetch(ENDPOINTS.health),
        safeFetch(ENDPOINTS.emulators),
        safeFetch(ENDPOINTS.controllers),
    ]);

    // Emulator health
    const rawHealth = healthData.status === 'fulfilled' ? healthData.value?.status : null;
    if (Array.isArray(rawHealth)) {
        ctx.emulatorHealth = rawHealth.map((e) => ({
            id: e.emulator || e.id,
            status: e.status,
            details: e.details || null,
        }));
    }

    // Emulator list
    const rawEmulators = emulatorData.status === 'fulfilled' ? emulatorData.value?.emulators : null;
    if (Array.isArray(rawEmulators)) {
        ctx.emulators = rawEmulators.map((e) => ({
            id: e.id,
            displayName: e.name || e.displayName || e.id,
            status: e.status || 'ok',
        }));
    }

    // Detected controllers
    const rawControllers = controllerData.status === 'fulfilled' ? controllerData.value : null;
    const controllerList = rawControllers?.controllers ?? rawControllers?.results ?? [];
    if (Array.isArray(controllerList) && controllerList.length) {
        ctx.detectedControllers = controllerList.slice(0, 4).map((c, i) => ({
            player: c.player ?? i + 1,
            name: c.name || c.displayName || c.id || 'Unknown',
            connected: c.connected ?? true,
        }));
    } else {
        ctx.detectedControllers = [];
    }

    // Tier 3 — static capability hint
    ctx.availableActions = [
        'Propose emulator config fix via action block',
        'Guide user through Scan / Preview / Apply flow',
        'Advise on Chuck sync gaps',
    ];

    return ctx;
}
