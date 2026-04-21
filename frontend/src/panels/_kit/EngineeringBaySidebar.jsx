import React, {
    useState,
    useRef,
    useEffect,
    useCallback,
    memo,
} from 'react';
import './EngineeringBaySidebar.css';
import { speak, stopSpeaking } from '../../services/ttsClient';
import { useDiagnosisMode } from '../../hooks/useDiagnosisMode';
import { DiagnosisToggle } from '../controller/DiagnosisToggle';
import { ContextChips } from '../controller/ContextChips';
import { ExecutionCard } from '../controller/ExecutionCard';
import { useProfileContext } from '../../context/ProfileContext';
import { buildStandardHeaders } from '../../utils/identity';

const MAX_VISIBLE_DIAG_CHIPS = 3;

async function engineeringBayChat({ persona, panelLabel, message, history, isDiagnosisMode, extraContext }) {
    const chatEndpoint = persona?.chatEndpoint || '/api/local/engineering-bay/chat';
    const personaId = persona?.id || 'unknown';
    const res = await fetch(chatEndpoint, {
        method: 'POST',
        headers: buildStandardHeaders({
            panel: personaId,
            scope: 'state',
            extraHeaders: { 'Content-Type': 'application/json' },
        }),
        body: JSON.stringify({ persona: personaId, message, history, isDiagnosisMode, extraContext }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? `${personaId} AI request failed`);
    }
    return res.json();
}

function parseActionBlock(text) {
    const match = text.match(/```action\s*([\s\S]*?)```/);
    if (!match) return { action: null, cleanText: text };
    try {
        const action = JSON.parse(match[1].trim());
        const cleanText = text.replace(/```action[\s\S]*?```/, '').trim();
        return { action, cleanText };
    } catch {
        return { action: null, cleanText: text };
    }
}

const MessageBubble = memo(({ msg, persona }) => {
    const ts = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (msg.role === 'assistant') {
        return (
            <div className="eb-msg eb-msg--assistant">
                <span className="eb-msg__avatar">{persona.icon}</span>
                <div>
                    <p className="eb-msg__text">{msg.content}</p>
                    <span className="eb-msg__time">{ts}</span>
                </div>
            </div>
        );
    }

    if (msg.role === 'system') {
        return (
            <div className="eb-msg eb-msg--system">
                <p className="eb-msg__text">{msg.content}</p>
            </div>
        );
    }

    return (
        <div className="eb-msg eb-msg--user">
            <p className="eb-msg__text">{msg.content}</p>
            <span className="eb-msg__time">{ts}</span>
        </div>
    );
});
MessageBubble.displayName = 'EBMessageBubble';

export function EngineeringBaySidebar({ persona, contextAssembler, className = '', isOpen, onClose, onToggle, micHandlers, onSendRef, initialMessages = [] }) {
    const { profile } = useProfileContext();
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [pendingAction, setPendingAction] = useState(null);
    const [executeLoading, setExecuteLoading] = useState(false);
    const [isVoiceRecording, setIsVoiceRecording] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [chipPage, setChipPage] = useState(0);

    const bottomRef = useRef(null);
    const recognitionRef = useRef(null);
    const inputRef = useRef(null);
    const messagesRef = useRef(messages);
    const sendMessageRef = useRef(null);
    const startListeningRef = useRef(null);
    const diagModeRef = useRef(false);
    const pendingAutoListenRef = useRef(false);
    const prevDiagActiveRef = useRef(false);
    const initialMessagesAppliedRef = useRef(false);

    const addMessage = useCallback((content, role = 'assistant') => {
        setMessages(prev => [
            ...prev,
            { id: Date.now() + Math.random(), role, content, timestamp: new Date().toISOString() },
        ]);
    }, []);

    useEffect(() => { messagesRef.current = messages; }, [messages]);

    useEffect(() => {
        if (initialMessagesAppliedRef.current || !Array.isArray(initialMessages) || initialMessages.length === 0) {
            return;
        }

        setMessages(prev => (
            prev.length > 0
                ? prev
                : initialMessages.map((msg, index) => ({
                    id: msg.id ?? `${persona.id}-handoff-${index}`,
                    role: msg.role ?? 'system',
                    content: msg.content ?? '',
                    timestamp: msg.timestamp ?? new Date().toISOString(),
                }))
        ));
        initialMessagesAppliedRef.current = true;
    }, [initialMessages, persona.id]);

    useEffect(() => {
        if (typeof isOpen !== 'undefined' && !isOpen) {
            stopSpeaking();
            pendingAutoListenRef.current = false;
            if (recognitionRef.current) {
                try { recognitionRef.current.stop(); } catch { }
                recognitionRef.current = null;
            }
            setIsVoiceRecording(false);
            setIsSpeaking(false);
        }
    }, [isOpen]);

    const handleTimeout = useCallback(() => {
        addMessage('Diagnosis mode timed out.', 'system');
    }, [addMessage]);

    const diag = useDiagnosisMode({
        panelId: persona.id,
        contextAssembler,
        chips: persona.chips ?? [],
        voiceId: persona.voiceId ?? null,
        ttsSpeak: speak,
        ttsStop: stopSpeaking,
        onTimeout: handleTimeout,
        // DIAG_GREETING: post the spoken greeting into the visible chat history so
        // the mode transition is explicit to the user, not just spoken over TTS.
        // addMessage is stable ([] deps) so this does not cause enterDiagMode churn.
        onGreeting: addMessage,
        ...(persona.diagPermanent ? { forcedActive: true } : {}),
    });

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, [messages, loading, isSpeaking]);

    const activeProfileName = (profile?.displayName || '').trim() || 'Guest';
    const activeProfileId = (profile?.userId || '').trim() || 'guest';
    const activePlayerPosition = profile?.preferences?.playerPosition || null;

    const sendMessage = useCallback(async (text) => {
        const trimmed = (text ?? '').trim();
        if (!trimmed || loading || executeLoading) return;

        stopSpeaking();
        setIsSpeaking(false);
        pendingAutoListenRef.current = false;

        setInput('');
        diag.resetInteraction?.();
        addMessage(trimmed, 'user');
        setLoading(true);
        setPendingAction(null);

        const history = messagesRef.current
            .filter(m => m.role === 'user' || m.role === 'assistant')
            .slice(-10)
            .map(m => ({ role: m.role, content: m.content }));

        try {
            let extraContext = diag.context ?? null;
            if (!extraContext && contextAssembler) {
                try {
                    extraContext = await contextAssembler();
                } catch {
                    extraContext = null;
                }
            }

            const profileContext = {
                activeProfile: {
                    displayName: activeProfileName,
                    userId: activeProfileId,
                    initials: profile?.initials || '',
                    consent: !!profile?.consent,
                    playerPosition: activePlayerPosition,
                    preferences: profile?.preferences || {},
                }
            };

            extraContext = extraContext
                ? { ...extraContext, ...profileContext }
                : profileContext;

            const { reply } = await engineeringBayChat({
                persona,
                panelLabel: persona.name || persona.id,
                message: trimmed,
                history,
                isDiagnosisMode: diag.diagMode || persona.diagPermanent,
                extraContext,
            });

            const { action, cleanText } = parseActionBlock(reply);
            if (cleanText) addMessage(cleanText, 'assistant');
            if (action) setPendingAction(action);

            setLoading(false);

            const ttsOpts = persona.voiceId
                ? { voice_id: persona.voiceId }
                : persona.voiceProfile
                    ? { voice_profile: persona.voiceProfile }
                    : {};

            if (cleanText?.trim()) {
                setIsSpeaking(true);
                try {
                    await speak(cleanText, ttsOpts);
                } catch (ttsErr) {
                    console.warn('[EngineeringBaySidebar] TTS failed:', ttsErr);
                } finally {
                    setIsSpeaking(false);
                }
            }

            if (diagModeRef.current) {
                pendingAutoListenRef.current = true;
            }
        } catch (err) {
            setLoading(false);
            setIsSpeaking(false);
            addMessage(`Error: ${err.message ?? `${persona.name} is unreachable.`}`, 'system');
        }
    }, [
        loading,
        executeLoading,
        diag,
        addMessage,
        persona,
        contextAssembler,
        activeProfileName,
        activeProfileId,
        activePlayerPosition,
        profile
    ]);

    useEffect(() => { sendMessageRef.current = sendMessage; }, [sendMessage]);
    // SEND_BRIDGE: expose sendMessage outward so parent panels can route external
    // mic transcripts into this sidebar's canonical conversation path.
    // Only active when the parent passes an onSendRef; other panels are unaffected.
    useEffect(() => { if (onSendRef) onSendRef.current = sendMessage; }, [sendMessage, onSendRef]);

    const handleExecuteAction = useCallback(async (action) => {
        setExecuteLoading(true);
        try {
            const res = await fetch(action.endpoint, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: persona.id,
                    scope: 'config',
                    extraHeaders: { 'Content-Type': 'application/json' },
                }),
                body: JSON.stringify(action.payload ?? {}),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail ?? 'Action failed');
            }
            addMessage(`OK: ${action.description ?? 'Fix applied.'}`, 'system');
            setPendingAction(null);
        } catch (err) {
            addMessage(`Error: Execute failed: ${err.message}`, 'system');
        } finally {
            setExecuteLoading(false);
        }
    }, [addMessage, persona.id]);

    const handleCancelAction = useCallback(() => {
        addMessage('Cancelled.', 'system');
        setPendingAction(null);
    }, [addMessage]);

    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(input);
        }
    }, [input, sendMessage]);

    useEffect(() => {
        diagModeRef.current = diag.diagMode || persona.diagPermanent;
    }, [diag.diagMode, persona.diagPermanent]);

    const startListening = useCallback(() => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            addMessage('Voice input not supported in this browser.', 'system');
            return;
        }
        if (recognitionRef.current) return;

        try {
            const recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'en-US';
            recognitionRef.current = recognition;

            recognition.onstart = () => {
                setIsVoiceRecording(true);
            };

            recognition.onresult = (event) => {
                if (!event.results[0].isFinal) return;
                const transcript = event.results[0][0].transcript;
                setIsVoiceRecording(false);
                recognitionRef.current = null;
                if (!transcript.trim()) return;

                diag.resetInteraction?.();
                sendMessageRef.current?.(transcript);
            };

            recognition.onerror = (event) => {
                console.warn('[EngineeringBaySidebar] Voice error:', event.error);
                setIsVoiceRecording(false);
                recognitionRef.current = null;
            };

            recognition.onend = () => {
                setIsVoiceRecording(false);
                recognitionRef.current = null;
            };

            recognition.start();
        } catch (err) {
            console.error('[EngineeringBaySidebar] Failed to start voice input:', err);
            setIsVoiceRecording(false);
        }
    }, [addMessage, diag]);

    useEffect(() => { startListeningRef.current = startListening; }, [startListening]);
    useEffect(() => { setChipPage(0); }, [persona.id, diag.diagMode, diag.chips]);

    const isActive = diag.diagMode || persona.diagPermanent;
    const isControlled = typeof isOpen !== 'undefined';
    const isVisible = !isControlled || isOpen;
    // DEDUP_GUARD: extract the external recording flag here so the auto-listen
    // effect can treat it as a reactive dep. For panels without micHandlers this
    // is always false, leaving their auto-listen behavior completely unchanged.
    const externalMicRecording = micHandlers?.isRecording ?? false;

    useEffect(() => {
        const becameActive = isActive && !prevDiagActiveRef.current;
        const becameInactive = !isActive && prevDiagActiveRef.current;

        if (becameActive) {
            pendingAutoListenRef.current = true;
        }

        if (becameInactive) {
            pendingAutoListenRef.current = false;
            if (recognitionRef.current) {
                try { recognitionRef.current.stop(); } catch { }
                recognitionRef.current = null;
            }
            setIsVoiceRecording(false);
        }

        prevDiagActiveRef.current = isActive;
    }, [isActive]);

    useEffect(() => {
        if (!isVisible || !isActive) return;
        if (!pendingAutoListenRef.current) return;
        // Block internal Web Speech auto-listen when external (panel-local) recording
        // is already active. Without this guard the two capture paths can overlap,
        // producing duplicate submissions in panels that use micHandlers (e.g. Wizard).
        if (loading || executeLoading || isSpeaking || isVoiceRecording || externalMicRecording) return;
        if (recognitionRef.current) return;

        pendingAutoListenRef.current = false;
        startListeningRef.current?.();
    }, [isVisible, isActive, loading, executeLoading, isSpeaking, isVoiceRecording, externalMicRecording]);

    const toggleVoiceInput = useCallback(() => {
        if (isVoiceRecording) {
            if (recognitionRef.current) recognitionRef.current.stop();
            setIsVoiceRecording(false);
            pendingAutoListenRef.current = false;
            return;
        }
        stopSpeaking();
        setIsSpeaking(false);
        pendingAutoListenRef.current = false;
        startListening();
    }, [isVoiceRecording, startListening]);

    // MIC_HANDOFF: if a panel provides its own mic handlers, prefer those over
    // the shared Web Speech-only path. This allows panels with better capture
    // paths (getUserMedia + MediaRecorder) to opt in without touching global behavior.
    // Panels that do NOT pass micHandlers are completely unaffected.
    const effectiveMicRecording = micHandlers ? micHandlers.isRecording : isVoiceRecording;
    const effectiveMicToggle = micHandlers ? micHandlers.onToggle : toggleVoiceInput;

    const sidebarClass = [
        'eb-sidebar',
        isActive ? 'eb-sidebar--active' : '',
        isControlled && !isOpen ? 'eb-sidebar--collapsed' : '',
        className,
    ].join(' ').trim();
    const cssVars = { '--eb-accent': persona.accentColor, '--eb-glow': persona.accentGlow };
    const showDiagnosisToggle = persona.showDiagnosisToggle !== false && !persona.diagPermanent;

    const pillLabel = persona.diagLabel ?? (persona.diagPermanent ? 'SYS' : 'DIAG');
    const placeholder = isActive
        ? `${persona.name} DIAG - what needs fixing?`
        : `Ask ${persona.name}... (Enter to send)`;

    const showScanner = loading || isSpeaking || effectiveMicRecording || isActive;
    const scannerLabel = loading
        ? (persona.scannerLabel ?? 'Scanning...')
        : effectiveMicRecording
            ? 'Listening...'
            : isSpeaking
                ? 'Speaking...'
                : 'Standby';

    const modeLabel = isActive ? `${pillLabel} mode` : 'Chat mode';
    const statusLabel = loading
        ? 'Thinking'
        : effectiveMicRecording
            ? 'Listening'
            : isSpeaking
                ? 'Speaking'
                : 'Ready';

    const chips = Array.isArray(diag.chips) ? diag.chips : [];
    const chipPageCount = chips.length ? Math.ceil(chips.length / MAX_VISIBLE_DIAG_CHIPS) : 1;
    const chipStart = chipPage * MAX_VISIBLE_DIAG_CHIPS;
    const visibleChips = chips.slice(chipStart, chipStart + MAX_VISIBLE_DIAG_CHIPS);

    const showHandsFreeHint = isActive && !loading && !effectiveMicRecording && !isSpeaking;
    const micLabel = effectiveMicRecording ? 'Stop' : (isActive ? 'Talk' : 'Mic');
    const showSendButton = !isActive;

    return (
        <aside className={sidebarClass} style={cssVars} aria-label={`${persona.name} AI Sidebar`}>
            <div className="eb-header">
                <div className="eb-header__title">
                    <span className="eb-header__icon">{persona.icon}</span>
                    <span>{persona.name}</span>
                    {persona.icon2 && <span className="eb-header__icon2">{persona.icon2}</span>}
                    {isActive && <span className="eb-header__pill">{pillLabel}</span>}
                </div>

                {showDiagnosisToggle && (
                    <DiagnosisToggle
                        active={diag.diagMode}
                        isTransitioning={diag.isTransitioning}
                        onToggle={diag.toggleDiagMode}
                        disabled={loading || executeLoading}
                        accentColor={persona.accentColor}
                    />
                )}

                {isControlled && onClose && (
                    <button
                        type="button"
                        className="eb-header__close"
                        onClick={onClose}
                        aria-label={`Close ${persona.name} chat`}
                        title="Close chat"
                    >X</button>
                )}
            </div>

            <div className="eb-mode-row">
                <span className="eb-mode-row__pill">Profile: {activeProfileName}</span>
                <span className="eb-mode-row__status">{activePlayerPosition || activeProfileId}</span>
            </div>

            <div className="eb-mode-row">
                <span className={`eb-mode-row__pill ${isActive ? 'eb-mode-row__pill--diag' : ''}`}>{modeLabel}</span>
                <span className={`eb-mode-row__status ${(loading || effectiveMicRecording || isSpeaking) ? 'eb-mode-row__status--live' : ''}`}>{statusLabel}</span>
            </div>

            {showHandsFreeHint && (
                <div className="eb-hf-hint">Hands-free active. Tap Talk to interrupt and speak.</div>
            )}

            <div className="eb-messages" role="log" aria-live="polite">
                {messages.length === 0 && (
                    <div className="eb-empty">
                        <span className="eb-empty__icon">{persona.icon}</span>
                        {persona.emptyHint ?? `Ask ${persona.name} anything.`}
                    </div>
                )}

                {messages.map(msg => (
                    <MessageBubble key={msg.id} msg={msg} persona={persona} />
                ))}

                {showScanner && (
                    <div className={`eb-kitt ${(loading || effectiveMicRecording || isSpeaking) ? '' : 'eb-kitt--ambient'}`}
                        aria-label={`${persona.name} ${statusLabel.toLowerCase()}`}>
                        <span className="eb-kitt__label">{scannerLabel}</span>
                        <div className="eb-kitt__track">
                            <div className="eb-kitt__orb" />
                        </div>
                    </div>
                )}

                <div ref={bottomRef} />
            </div>

            {pendingAction && (
                <ExecutionCard
                    proposal={pendingAction}
                    onExecute={handleExecuteAction}
                    onCancel={handleCancelAction}
                    loading={executeLoading}
                />
            )}

            {isActive && chips.length > 0 && !loading && !effectiveMicRecording && (
                <div className="eb-chipbar">
                    <ContextChips chips={visibleChips} onChipClick={sendMessage} disabled={loading || executeLoading} />
                    {chipPageCount > 1 && (
                        <button
                            type="button"
                            className="eb-chipbar__more"
                            onClick={() => setChipPage(prev => (prev + 1) % chipPageCount)}
                            disabled={loading || executeLoading}
                            aria-label="Show more quick prompts"
                        >
                            More {chipPage + 1}/{chipPageCount}
                        </button>
                    )}
                </div>
            )}

            <div className="eb-input-row">
                <textarea
                    ref={inputRef}
                    className="eb-input"
                    value={input}
                    onChange={e => { setInput(e.target.value); diag.resetInteraction?.(); }}
                    onKeyDown={handleKeyDown}
                    placeholder={placeholder}
                    rows={1}
                    disabled={loading || executeLoading}
                    aria-label="Chat input"
                />
                <button
                    type="button"
                    className={`eb-mic ${effectiveMicRecording ? 'eb-mic--recording' : ''}`}
                    onClick={effectiveMicToggle}
                    disabled={executeLoading}
                    title={effectiveMicRecording ? 'Stop recording' : 'Voice input'}
                    aria-label={effectiveMicRecording ? 'Stop recording' : 'Voice input'}
                >
                    {micLabel}
                </button>
                {showSendButton && (
                    <button
                        type="button"
                        className="eb-send"
                        onClick={() => sendMessage(input)}
                        disabled={loading || executeLoading || !input.trim()}
                        aria-label="Send message"
                    >Send</button>
                )}
            </div>
        </aside>
    );
}

export default EngineeringBaySidebar;
