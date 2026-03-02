/**
 * chuckContextAssembler.js
 * ═══════════════════════════════════════════════════════════════════
 * Builds Controller Chuck's 3-tier Diagnosis Mode context payload.
 * Called by useDiagnosisMode() on entry and every 30 s during session.
 *
 * Decision refs (diagnosis_mode_plan.md):
 *   Q4 — ControllerBridge is sole merge authority; GPIO + Semantic layers
 *   Q6 — Tier 1 always, Tier 2 conditional, Tier 3 static; total < 1500 tokens
 *
 * PANEL ISOLATION RULE: Chuck's world only.
 * No LaunchBox feed, no LED states, no score data, no other panel data.
 */

const CONTROLLER_API = '/api/local/controller';
const HARDWARE_API = '/api/local/hardware';

/** Silent fetch — returns null on any error (hardware offline is normal) */
async function safeFetch(url) {
    try {
        const res = await fetch(url, {
            headers: {
                'x-panel': 'controller-chuck',
                'x-scope': 'state',
                'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
            },
        });
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

/**
 * Main assembler — exported and consumed by useDiagnosisMode.
 * @returns {Promise<{tier1, tier2, tier3}>}
 */
export async function chuckContextAssembler() {
    // ── Tier 1: Always included (every message while diagMode is active) ────────
    // Parallel fetch — hardware + mapping baseline
    const [hardware, baseline] = await Promise.all([
        safeFetch(`${HARDWARE_API}/devices`),
        safeFetch(`${CONTROLLER_API}/baseline`),
    ]);

    const tier1 = {
        diagMode: true,
        timestamp: new Date().toISOString(),
        hardware: {
            detected: hardware?.devices ?? [],
            boardStatus: hardware?.status ?? 'unknown',
            boardName: hardware?.board_name ?? null,
        },
        session: {
            playerMode: window._chuckPlayerMode ?? '4p',
            mappedButtonCount: Object.keys(baseline?.mapping ?? {}).length,
            profileId: window?.AA_PROFILE_ID ?? 'default',
        },
    };

    // ── Tier 2: Conditional (only included when meaningful data exists) ─────────
    const tier2 = {};

    const mapping = baseline?.mapping ?? {};
    if (Object.keys(mapping).length > 0) {
        // Summarise — don't dump the raw object (token budget)
        const playerSummary = {};
        Object.entries(mapping).forEach(([key, val]) => {
            const [player] = key.split('.');
            if (!playerSummary[player]) playerSummary[player] = 0;
            if (val?.pin != null) playerSummary[player]++;
        });
        tier2.activeMappingSummary = playerSummary;   // e.g. { p1: 12, p2: 10 }
        tier2.totalMappedInputs = Object.keys(mapping).length;
    }

    if (baseline?.lastUpdated) {
        tier2.lastSaved = baseline.lastUpdated;
    }

    if (baseline?.profileName) {
        tier2.profileName = baseline.profileName;
    }

    // ── Tier 3: Static knowledge (always present, never changes at runtime) ─────
    // Sacred numbering is the Rosetta Stone for all 45+ emulator configs.
    // Hard-coded here so the AI always has it available mid-session.
    const tier3 = {
        sacredLaw: {
            description: 'This numbering is immutable — it maps to all 45+ emulator configs.',
            p1p2: { topRow: '1-2-3-7', bottomRow: '4-5-6-8' },
            p3p4: { topRow: '1-2', bottomRow: '3-4', note: '4-button only' },
        },
        writeTargets: {
            profile: 'A:\\.aa\\state\\profiles\\{userId}\\overrides.json',
            cabinet: 'A:\\.aa\\state\\controller\\cabinet_mapping.json',
        },
        aiToolAvailable: 'remediate_controller_config',
    };

    return { tier1, tier2, tier3 };
}

/**
 * Builds a contextual greeting from the assembled payload.
 * Returns a short Chuck-voiced string (1–2 sentences).
 *
 * @param {object|null} ctx — result of chuckContextAssembler()
 * @returns {string}
 */
export function buildChuckGreeting(ctx) {
    if (!ctx) {
        return "Yo! Chuck here — Diagnosis Mode is HOT. Hardware's offline but I got my notes. What are we fixin'?";
    }

    const { tier1, tier2 } = ctx;
    const board = tier1?.hardware?.boardName ?? 'the encoder';
    const status = tier1?.hardware?.boardStatus ?? 'unknown';
    const mapped = tier2?.totalMappedInputs ?? 0;

    if (status === 'error' || status === 'offline') {
        return `Yo! Chuck on. ${board} is showing ${status} — let's start there. What happened?`;
    }

    if (mapped === 0) {
        return `Chuck here. ${board} is up but the mapping's empty. Let's wire this cabinet from scratch. Where ya wanna start?`;
    }

    return `Yo! Diagnosis Mode is live. ${board} is ${status}, ${mapped} inputs mapped. What's giving you grief?`;
}
