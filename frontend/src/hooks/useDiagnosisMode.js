/**
 * useDiagnosisMode.js
 * ═══════════════════════════════════════════════════════════════════
 * Shared hook — Diagnosis Mode infrastructure for all specialist panels.
 *
 * Decision refs (diagnosis_mode_plan.md):
 *   Q2  — Confirmations-only TTS, interruptible
 *   Q3  — No wake word; self-declaratory mode toggle fires greeting
 *   Q9  — One shared hook, per-panel context assembler registration
 *   Q10 — Soft-lock on inactivity; never persists across page load
 *   Q11 — Push-to-talk is the gate; TTS disabled while mic is hot
 *
 * Usage:
 *   const diag = useDiagnosisMode({
 *     contextAssembler : chuckContextAssembler,   // async fn → payload
 *     chips            : chuckChips,              // suggestion chip array
 *     buildGreeting    : (ctx) => string,         // greeting text builder
 *     exitMessage      : "Chuck OUT.",            // optional farewell TTS
 *     voiceId          : CHUCK_VOICE_ID,          // ElevenLabs voice id
 *     onGreeting       : (text) => addMsg(text),  // post to chat history
 *     onContextUpdate  : (ctx) => { ... },        // optional side-effect
 *     timeoutMinutes   : 5,                       // 0 = disabled
 *   });
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { speak, stopSpeaking } from '../services/ttsClient';

const REFRESH_INTERVAL_MS = 30_000; // re-fetch hardware context every 30 s
const SOFT_LOCK_CHECK_MS = 10_000; // idle-check cadence

export function useDiagnosisMode({
    contextAssembler = null,
    chips = [],
    buildGreeting = null,
    exitMessage = null,
    voiceId = null,
    onGreeting = null,
    onContextUpdate = null,
    onTimeout = null,      // called when Diagnosis Mode auto-reverts on idle
    timeoutMinutes = 5,
} = {}) {

    // ── Public state ───────────────────────────────────────────────────────────
    const [diagMode, setDiagMode] = useState(false);
    const [softLocked, setSoftLocked] = useState(false);
    const [isTransitioning, setIsTransitioning] = useState(false);
    const [context, setContext] = useState(null);

    // ── Internal refs ──────────────────────────────────────────────────────────
    const lastInteractionRef = useRef(Date.now());
    const softLockTimerRef = useRef(null);
    const contextRefreshRef = useRef(null);
    const diagModeRef = useRef(false);   // readable inside intervals

    // Keep ref in sync with state
    useEffect(() => { diagModeRef.current = diagMode; }, [diagMode]);

    // ── Interaction tracking ───────────────────────────────────────────────────
    /** Call on every user interaction while Diagnosis Mode is active. */
    const resetInteraction = useCallback(() => {
        lastInteractionRef.current = Date.now();
        if (softLocked) setSoftLocked(false);
    }, [softLocked]);

    /** Click-to-resume from soft-lock banner. */
    const resumeFromSoftLock = useCallback(() => {
        setSoftLocked(false);
        lastInteractionRef.current = Date.now();
    }, []);

    // ── Timeout auto-revert watcher ────────────────────────────────────────────
    // V1 Constitution: after idle timeout, fully revert to Chat Mode (not soft-lock).
    // Clears quietly — no TTS — appends a system message via onTimeout callback.
    useEffect(() => {
        if (!diagMode || timeoutMinutes <= 0) return undefined;

        softLockTimerRef.current = setInterval(() => {
            const idleMs = Date.now() - lastInteractionRef.current;
            if (idleMs >= timeoutMinutes * 60_000) {
                // Full revert — clear all Diagnosis Mode state
                clearInterval(contextRefreshRef.current);
                clearInterval(softLockTimerRef.current);
                setDiagMode(false);
                setSoftLocked(false);
                setContext(null);
                // Notify caller to append system message to chat
                onTimeout?.();
            }
        }, SOFT_LOCK_CHECK_MS);

        return () => clearInterval(softLockTimerRef.current);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [diagMode, timeoutMinutes]);

    // ── Context refresh ────────────────────────────────────────────────────────
    const refreshContext = useCallback(async () => {
        if (!contextAssembler) return null;
        try {
            const payload = await contextAssembler();
            setContext(payload);
            onContextUpdate?.(payload);
            return payload;
        } catch (err) {
            console.warn('[useDiagnosisMode] contextAssembler failed', err);
            return null;
        }
    }, [contextAssembler, onContextUpdate]);

    // ── Enter Diagnosis Mode ───────────────────────────────────────────────────
    const enterDiagMode = useCallback(async () => {
        if (diagModeRef.current) return;   // already active — no-op

        // Kill any in-progress TTS to prevent echo/overlap
        try { stopSpeaking(); } catch { /* noop */ }

        setIsTransitioning(true);

        // 1. Fetch Tier 1 context before doing anything visible
        const payload = await refreshContext();

        // 2. Build the contextual greeting text
        let greetingText = "Diagnosis Mode active. What are we fixing today?";
        if (typeof buildGreeting === 'function') {
            try { greetingText = buildGreeting(payload) || greetingText; }
            catch { /* use default */ }
        }

        // 3. Flip state
        setDiagMode(true);
        setIsTransitioning(false);
        lastInteractionRef.current = Date.now();

        // 4. Post greeting to chat history
        onGreeting?.(greetingText);

        // 5. Speak greeting (TTS — confirmations / entries only per Q2)
        if (voiceId) {
            try { await speak(greetingText, { voice_id: voiceId }); }
            catch (err) { console.warn('[useDiagnosisMode] TTS failed', err); }
        }

        // 6. Start periodic context refresh
        contextRefreshRef.current = setInterval(refreshContext, REFRESH_INTERVAL_MS);
    }, [refreshContext, buildGreeting, onGreeting, voiceId]);

    // ── Exit Diagnosis Mode ────────────────────────────────────────────────────
    const exitDiagMode = useCallback(async () => {
        if (!diagModeRef.current) return;  // already inactive — no-op

        // Kill any in-progress TTS to prevent echo/overlap
        try { stopSpeaking(); } catch { /* noop */ }

        clearInterval(contextRefreshRef.current);
        clearInterval(softLockTimerRef.current);

        setDiagMode(false);
        setSoftLocked(false);
        setContext(null);

        // Farewell TTS (optional per panel)
        if (exitMessage && voiceId) {
            try { await speak(exitMessage, { voice_id: voiceId }); }
            catch { /* noop */ }
        }
    }, [exitMessage, voiceId]);

    // ── Toggle ─────────────────────────────────────────────────────────────────
    const toggleDiagMode = useCallback(() => {
        if (diagModeRef.current) {
            exitDiagMode();
        } else {
            enterDiagMode();
        }
    }, [enterDiagMode, exitDiagMode]);

    // ── Cleanup on unmount ─────────────────────────────────────────────────────
    // Also fulfils Q10: Diagnosis Mode never survives a page unload.
    useEffect(() => {
        return () => {
            clearInterval(contextRefreshRef.current);
            clearInterval(softLockTimerRef.current);
            try { stopSpeaking(); } catch { /* noop */ }
        };
    }, []);

    // ── Public API ─────────────────────────────────────────────────────────────
    return {
        // State
        diagMode,
        softLocked,
        isTransitioning,
        context,
        chips,
        // Actions
        toggleDiagMode,
        enterDiagMode,
        exitDiagMode,
        resetInteraction,
        refreshContext,
    };
}
