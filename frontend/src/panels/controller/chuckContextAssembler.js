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
 *
 * TRUTH SOURCE (2026-04-14 reconciliation pass):
 *   Tier 1 hardware context comes from /api/local/controller/status —
 *   the Cabinet Control Status endpoint that already reconciles:
 *     • connected_board  (canonical live board lane)
 *     • saved_mapping    (controls.json board identity)
 *     • warnings         (drift between live vs saved)
 *   This is the same payload CabinetControlStatus.jsx renders.
 *   Do NOT call /hardware/usb/devices (different router, different field shape).
 *   Do NOT call /controller/baseline for hardware state
 *   (baseline is cascade/emulator state, not board identity).
 */

import { buildStandardHeaders } from '../../utils/identity';

const STATUS_API = '/api/local/controller/status';

/** Silent fetch — returns null on any error (hardware offline is normal) */
async function safeFetch(url) {
    try {
        const res = await fetch(url, {
            headers: buildStandardHeaders({ panel: 'controller-chuck', scope: 'state' }),
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
    // ── Tier 1: Always included ──────────────────────────────────────────────
    // Pull from the canonical status surface — already reconciled by the backend.
    const status = await safeFetch(STATUS_API);

    // connected_board: live board from the canonical detection lane
    const connectedBoard = status?.connected_board ?? {};
    // saved_mapping: what controls.json says
    const savedMapping = status?.saved_mapping ?? {};
    // warnings: backend-computed drift between live and saved
    const warnings = Array.isArray(status?.warnings) ? status.warnings : [];

    const isLiveBoardPresent = connectedBoard.status === 'connected';
    const liveBoardName = connectedBoard.name ?? null;
    const liveBoardStatus = isLiveBoardPresent ? 'connected' : (connectedBoard.status ?? 'not_detected');

    const tier1 = {
        diagMode: true,
        timestamp: new Date().toISOString(),
        hardware: {
            // Live board identity — the canonical truth
            boardStatus: liveBoardStatus,
            boardName: liveBoardName,
            boardVid: connectedBoard.vid ?? null,
            boardPid: connectedBoard.pid ?? null,
            boardSource: connectedBoard.source ?? null,
            boardSummary: connectedBoard.summary ?? null,
            // Saved mapping identity — secondary truth
            savedBoardName: savedMapping.name ?? null,
            savedBoardStatus: savedMapping.status ?? null,
            savedFilePath: savedMapping.file_path ?? 'config/mappings/controls.json',
            // Runtime child endpoints
            runtimeEndpointCount: status?.runtime?.endpoints?.length ?? 0,
            runtimeExplanation: status?.runtime?.explanation ?? null,
        },
        // Board identity mismatch flags — make Chuck immediately aware
        driftWarnings: warnings.map((w) => ({
            code: w.code,
            severity: w.severity,
            title: w.title,
            detail: w.detail,
        })),
        session: {
            playerMode: window._chuckPlayerMode ?? '4p',
            profileId: window?.AA_PROFILE_ID ?? 'default',
        },
    };

    // ── Tier 2: Conditional ──────────────────────────────────────────────────
    const tier2 = {};

    // Include cascade state when available
    const cascade = status?.cascade ?? {};
    if (cascade.status) {
        tier2.cascade = {
            status: cascade.status,
            historyCount: cascade.history_count ?? 0,
            ledStatus: cascade.led?.status ?? null,
            emulatorCount: Array.isArray(cascade.emulators) ? cascade.emulators.length : 0,
            summary: cascade.summary ?? null,
        };
    }

    // Surface the most critical warning at tier-2 for focused AI attention
    const criticalWarning = warnings.find((w) => w.severity === 'warning');
    if (criticalWarning) {
        tier2.primaryWarning = {
            code: criticalWarning.code,
            title: criticalWarning.title,
            detail: criticalWarning.detail,
        };
    }

    // ── Tier 3: Static knowledge ─────────────────────────────────────────────
    // Sacred numbering is the Rosetta Stone for all 45+ emulator configs.
    // Hard-coded here so the AI always has it available mid-session.
    const tier3 = {
        sacredLaw: {
            description: 'This numbering is immutable — it maps to all 45+ emulator configs.',
            p1p2: { topRow: '1-2-3-7', bottomRow: '4-5-6-8' },
            p3p4: { topRow: '1-2', bottomRow: '3-4', note: '4-button only' },
        },
        writeTargets: {
            profile: '${AA_DRIVE_ROOT}/.aa/state/profiles/{userId}/overrides.json',
            cabinet: '${AA_DRIVE_ROOT}/.aa/state/controller/cabinet_mapping.json',
        },
        aiToolAvailable: 'remediate_controller_config',
        identityRules: {
            liveBoard: 'What is physically connected right now — from canonical detection lane.',
            savedMapping: 'What controls.json says the cabinet is configured as.',
            runtimeEndpoints: 'Child HID/XInput nodes Windows sees — not separate boards.',
            precedence: 'Live board > saved mapping. Show both. Do not hide mismatch.',
        },
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
    const status = tier1?.hardware?.boardStatus ?? 'not_detected';
    const primaryWarning = tier2?.primaryWarning;

    if (status === 'not_detected') {
        return `Yo! Chuck on. No live encoder board on the wire right now. Saved mapping says ${tier1?.hardware?.savedBoardName ?? 'unknown'}. What do ya need?`;
    }

    if (status === 'error' || status === 'offline') {
        return `Yo! Chuck on. ${board} is showing ${status} — let's start there. What happened?`;
    }

    if (primaryWarning) {
        return `Diagnosis Mode live. ${board} is ${status} — but heads up: ${primaryWarning.title}. Let's sort it.`;
    }

    return `Yo! Diagnosis Mode is live. ${board} is connected and looking clean. What's giving you grief?`;
}
