/**
 * ChuckSidebar.jsx
 * ═══════════════════════════════════════════════════════════════════
 * Controller Chuck's chat sidebar with integrated Diagnosis Mode.
 *
 * Decision refs (diagnosis_mode_plan.md):
 *   Q2  — TTS on entry greeting + confirmations only; interruptible
 *   Q3  — Self-declaratory mode switch; contextual greeting on toggle
 *   Q6  — Context payload injected into every AI call when diagMode active
 *   Q8  — Optimistic input; chat is ephemeral until session commit
 *   Q9  — Uses shared useDiagnosisMode() hook
 *   Q10 — Soft-lock banner on inactivity; click to resume
 *   Q11 — MicButton is push-to-talk gate; TTS stops on mic press
 */

import React, {
    useState, useRef, useEffect, useCallback, memo,
} from 'react';
import { useDiagnosisMode } from '../../hooks/useDiagnosisMode';
import {
    chuckContextAssembler,
    buildChuckGreeting
} from './chuckContextAssembler';
import { chuckChips } from './chuckChips';
import { DiagnosisToggle } from './DiagnosisToggle';
import { ContextChips } from './ContextChips';
import { MicButton } from './MicButton';
import { ExecutionCard } from './ExecutionCard';
import { controllerAIChat } from '../../services/controllerAI';
import { speak, stopSpeaking } from '../../services/ttsClient';
import { logChatHistory } from '../../services/supabaseClient';
import './chuck-sidebar.css';
import './chuck-layout.css';
import './ExecutionCard.css';


const CHUCK_VOICE_ID = 'f5HLTX707KIM4SzJYzSz';
const MAX_VISIBLE_MSGS = 80;   // trim history to avoid memory bloat

// ── Message bubble ─────────────────────────────────────────────────────────
const MessageBubble = memo(({ msg }) => (
    <div className={`csb-msg csb-msg--${msg.role}`}>
        {msg.role === 'assistant' && (
            <span className="csb-msg__avatar" aria-hidden="true">⚙️</span>
        )}
        <p className="csb-msg__text">{msg.text}</p>
        {msg.timestamp && (
            <time className="csb-msg__time" dateTime={msg.timestamp}>
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </time>
        )}
    </div>
));
MessageBubble.displayName = 'MessageBubble';

// ── Soft-lock overlay ──────────────────────────────────────────────────────
const SoftLockBanner = memo(({ onResume }) => (
    <div className="csb-soft-lock" role="alert">
        <span>💤 Diagnosis Mode paused — idle timeout</span>
        <button type="button" onClick={onResume}>Tap to resume</button>
    </div>
));
SoftLockBanner.displayName = 'SoftLockBanner';

// ── Main sidebar ────────────────────────────────────────────────────────────
export function ChuckSidebar({ panelState = {}, className = '' }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [isListening, setIsListening] = useState(false);
    const [pendingAction, setPendingAction] = useState(null);   // ExecutionCard proposal
    const [executeLoading, setExecuteLoading] = useState(false);
    const bottomRef = useRef(null);
    const inputRef = useRef(null);

    // ── Add a message to history ───────────────────────────────────────────────
    const addMessage = useCallback((text, role = 'assistant', opts = {}) => {
        const msg = {
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            role,
            text,
            timestamp: new Date().toISOString(),
            ...opts,
        };
        setMessages((prev) => {
            const next = [...prev, msg];
            return next.length > MAX_VISIBLE_MSGS ? next.slice(-MAX_VISIBLE_MSGS) : next;
        });
        return msg;
    }, []);

    // ── Diagnosis Mode hook ────────────────────────────────────────────────────
    const diag = useDiagnosisMode({
        contextAssembler: chuckContextAssembler,
        chips: chuckChips,
        buildGreeting: buildChuckGreeting,
        exitMessage: "Aight, powering down Diagnosis Mode. Hit me up if anything breaks.",
        voiceId: CHUCK_VOICE_ID,
        onGreeting: (text) => addMessage(text, 'assistant'),
        // V1 Constitution: timeout fully reverts to Chat Mode, appends system message
        onTimeout: () => addMessage(
            '🔔 Diagnosis Mode powered down due to inactivity.',
            'system'
        ),
        timeoutMinutes: 5,
    });

    // ── Auto-scroll to latest message ─────────────────────────────────────────
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // ── Send a message (text or chip prompt) ──────────────────────────────────
    const sendMessage = useCallback(async (text) => {
        if (!text.trim() || loading) return;

        diag.resetInteraction();
        addMessage(text, 'user');
        setInput('');
        setLoading(true);

        try {
            const enrichedState = {
                ...panelState,
                ...(diag.diagMode && diag.context
                    ? { diagnosisContext: diag.context }
                    : {}),
                isDiagnosisMode: diag.diagMode,
            };

            const result = await controllerAIChat(text, enrichedState, {
                panel: 'controller-chuck',
                deviceId: window?.AA_DEVICE_ID ?? 'cabinet-001',
            });

            const replyRaw = result?.reply ?? result?.response ?? 'No response.';

            // Check for action block (Diagnosis Mode write proposals)
            const parsed = diag.diagMode ? parseActionBlock(replyRaw) : null;
            if (parsed) {
                // Show clean text without the code block
                if (parsed.cleanText) addMessage(parsed.cleanText, 'assistant');
                setPendingAction(parsed.proposal);
            } else {
                addMessage(replyRaw, 'assistant');
                // Q2: speak in Diag Mode only — 1-2 sentence confirmations
                if (diag.diagMode) {
                    try { await speak(replyRaw, CHUCK_VOICE_ID); } catch { /* noop */ }
                }
            }

            try {
                await logChatHistory({
                    panel: 'controller-chuck',
                    userMsg: text,
                    aiReply: replyRaw,
                    diagMode: diag.diagMode,
                });
            } catch { /* noop */ }

        } catch (err) {
            const errText = err?.message ?? 'Something went wrong. Try again.';
            addMessage(`⚠️ ${errText}`, 'assistant');
            console.error('[ChuckSidebar] sendMessage failed', err);
        } finally {
            setLoading(false);
            inputRef.current?.focus();
        }
    }, [loading, panelState, diag, addMessage]);

    // ── Execute proposed action ───────────────────────────────────────────────────
    const handleExecuteAction = useCallback(async (payload) => {
        setExecuteLoading(true);
        try {
            const res = await fetch('/api/profiles/mapping-override', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...payload,
                    confirmed_by: 'user',
                    ai_reasoning: 'User confirmed via ExecutionCard',
                }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err?.detail ?? `HTTP ${res.status}`);
            }
            const data = await res.json();
            addMessage(`✅ Done. ${data?.message ?? payload.display ?? 'Change applied.'}`, 'assistant');
            setPendingAction(null);
        } finally {
            setExecuteLoading(false);
        }
    }, [addMessage]);

    const handleCancelAction = useCallback(() => {
        addMessage('❌ Fix cancelled.', 'system');
        setPendingAction(null);
    }, [addMessage]);

    // ── Keyboard submit ────────────────────────────────────────────────────────
    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(input);
        }
    }, [input, sendMessage]);

    // ── Voice transcript from MicButton ───────────────────────────────────────
    const handleTranscript = useCallback((transcript) => {
        diag.resetInteraction();
        sendMessage(transcript);
    }, [sendMessage, diag]);

    // ── Sidebar border class — amber when diagnosis mode active ───────────────
    const sidebarClass = [
        'chuck-sidebar',
        diag.diagMode ? 'chuck-sidebar--diagnosis' : '',
        className,
    ].join(' ').trim();

    return (
        <aside className={sidebarClass} aria-label="Chuck AI Sidebar">

            {/* ── Header ─────────────────────────────────────────────────────── */}
            <div className="csb-header">
                <div className="csb-header__title">
                    <span className="csb-header__icon">⚙️</span>
                    <span>Chuck</span>
                    <span className="csb-header__joystick" title="Arcade stick optimized">🕹️</span>
                    {diag.diagMode && (
                        <span className="csb-header__diag-badge">DIAG</span>
                    )}
                </div>
                <DiagnosisToggle
                    active={diag.diagMode}
                    isTransitioning={diag.isTransitioning}
                    onToggle={diag.toggleDiagMode}
                    disabled={loading}
                />
            </div>

            {/* ── Message list ────────────────────────────────────────────────── */}
            <div className="csb-messages" role="log" aria-live="polite" aria-label="Chat messages">
                {messages.length === 0 && (
                    <p className="csb-empty">
                        {diag.diagMode
                            ? 'Diagnosis Mode is active. Ask Chuck anything.'
                            : "Ask Chuck about your controller setup."}
                    </p>
                )}
                {messages.map((msg) => (
                    <MessageBubble key={msg.id} msg={msg} />
                ))}
                {loading && (
                    <div className="csb-kitt" aria-label="Chuck is analyzing">
                        <span className="csb-kitt__label">Analyzing…</span>
                        <div className="csb-kitt__track">
                            <div className="csb-kitt__orb" />
                        </div>
                    </div>
                )}
                <div ref={bottomRef} />
            </div>

            {/* ── Execution Card (Diagnosis Mode write proposals) ──────────────── */}
            {pendingAction && (
                <ExecutionCard
                    proposal={pendingAction}
                    onExecute={handleExecuteAction}
                    onCancel={handleCancelAction}
                    loading={executeLoading}
                />
            )}

            {/* ── Diagnosis Mode context chips ─────────────────────────────── */}
            {diag.diagMode && (
                <ContextChips
                    chips={diag.chips}
                    onChipClick={sendMessage}
                    disabled={loading || diag.softLocked}
                />
            )}

            {/* ── Input row ───────────────────────────────────────────────────── */}
            <div className="csb-input-row">
                <textarea
                    ref={inputRef}
                    className="csb-input"
                    value={input}
                    onChange={(e) => {
                        setInput(e.target.value);
                        diag.resetInteraction();
                    }}
                    onKeyDown={handleKeyDown}
                    placeholder={diag.diagMode
                        ? 'What are we fixing? (Enter to send)'
                        : 'Ask Chuck… (Enter to send)'}
                    rows={1}
                    disabled={loading}
                    aria-label="Chat input"
                />

                <MicButton
                    onTranscript={handleTranscript}
                    onListeningChange={setIsListening}
                    stopTTS={stopSpeaking}
                    disabled={loading || diag.softLocked}
                />

                <button
                    type="button"
                    className="csb-send"
                    onClick={() => sendMessage(input)}
                    disabled={!input.trim() || loading || diag.softLocked}
                    aria-label="Send message"
                >
                    ▶
                </button>
            </div>
        </aside>
    );
}
