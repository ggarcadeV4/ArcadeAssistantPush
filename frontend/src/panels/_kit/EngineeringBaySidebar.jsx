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

// ── API ────────────────────────────────────────────────────────────────────────
async function engineeringBayChat({ persona, message, history, isDiagnosisMode, extraContext }) {
    const res = await fetch('/api/local/engineering-bay/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-panel': persona,
            'x-scope': 'state',
            'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
        },
        body: JSON.stringify({ persona, message, history, isDiagnosisMode, extraContext }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? `${persona} AI request failed`);
    }
    return res.json();
}

// ── Action block parser ────────────────────────────────────────────────────────
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

// ── Message bubble ─────────────────────────────────────────────────────────────
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

// ── Main component ─────────────────────────────────────────────────────────────
/**
 * EngineeringBaySidebar — generic AI chat sidebar for all Engineering Bay personas.
 *
 * @param {object} persona - Config: { id, name, icon, icon2, accentColor, accentGlow,
 *                           scannerLabel, diagLabel, diagPermanent, emptyHint, chips }
 * @param {function} [contextAssembler] - async fn returning extra context payload
 * @param {string} [className]
 */
export function EngineeringBaySidebar({ persona, contextAssembler, className = '' }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [pendingAction, setPendingAction] = useState(null);
    const [executeLoading, setExecuteLoading] = useState(false);
    const [isVoiceRecording, setIsVoiceRecording] = useState(false);

    const bottomRef = useRef(null);
    const recognitionRef = useRef(null);
    const inputRef = useRef(null);
    const messagesRef = useRef(messages);
    useEffect(() => { messagesRef.current = messages; }, [messages]);

    // ── Diagnosis Mode hook ───────────────────────────────────────────────────
    const handleTimeout = useCallback(() => {
        addMessage('⏱️ Diagnosis Mode timed out.', 'system');
    }, []);

    const diag = useDiagnosisMode({
        panelId: persona.id,
        contextAssembler,
        chips: persona.chips ?? [],
        ttsSpeak: speak,
        ttsStop: stopSpeaking,
        onTimeout: handleTimeout,
        // Doc is always active — user can never toggle off
        ...(persona.diagPermanent ? { forcedActive: true } : {}),
    });

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, loading]);

    const addMessage = useCallback((content, role = 'assistant') => {
        setMessages(prev => [
            ...prev,
            { id: Date.now() + Math.random(), role, content, timestamp: new Date().toISOString() },
        ]);
    }, []);

    // ── Send ──────────────────────────────────────────────────────────────────
    const sendMessage = useCallback(async (text) => {
        const trimmed = (text ?? '').trim();
        if (!trimmed || loading) return;

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
            const extraContext = diag.context ?? null;
            const { reply } = await engineeringBayChat({
                persona: persona.id,
                message: trimmed,
                history,
                isDiagnosisMode: diag.diagMode || persona.diagPermanent,
                extraContext,
            });

            const { action, cleanText } = parseActionBlock(reply);
            addMessage(cleanText, 'assistant');
            if (action) setPendingAction(action);

            // TTS: first sentence only in Diagnosis Mode
            const ttsOpts = persona.voiceProfile
                ? { voice_profile: persona.voiceProfile }
                : {};
            if (diag.diagMode || persona.diagPermanent) {
                speak(cleanText.split('.')[0], ttsOpts);
            } else {
                speak(cleanText, ttsOpts);
            }
        } catch (err) {
            addMessage(`⚠️ ${err.message ?? `${persona.name} is unreachable.`}`, 'system');
        } finally {
            setLoading(false);
        }
    }, [loading, diag, addMessage, persona]);

    // ── Execute action ────────────────────────────────────────────────────────
    const handleExecuteAction = useCallback(async (action) => {
        setExecuteLoading(true);
        try {
            const res = await fetch(action.endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-panel': persona.id,
                    'x-scope': 'config',
                    'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
                },
                body: JSON.stringify(action.payload ?? {}),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail ?? 'Action failed');
            }
            addMessage(`✅ ${action.description ?? 'Fix applied.'}`, 'system');
            setPendingAction(null);
        } catch (err) {
            addMessage(`❌ Execute failed: ${err.message}`, 'system');
        } finally {
            setExecuteLoading(false);
        }
    }, [addMessage, persona.id]);

    const handleCancelAction = useCallback(() => {
        addMessage('❌ Cancelled.', 'system');
        setPendingAction(null);
    }, [addMessage]);

    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input); }
    }, [input, sendMessage]);

    // ── Click-toggle voice input (adapted from LED Blinky) ─────────────────────
    const toggleVoiceInput = useCallback(() => {
        if (isVoiceRecording) {
            if (recognitionRef.current) recognitionRef.current.stop();
            setIsVoiceRecording(false);
            return;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            addMessage('Voice input not supported in this browser.', 'system');
            return;
        }

        try {
            // Stop TTS before recording to prevent feedback
            stopSpeaking();

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
                sendMessage(transcript);
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
    }, [isVoiceRecording, addMessage, sendMessage, diag]);

    // ── Active state: diagnosis OR always-on (Doc) ────────────────────────────
    const isActive = diag.diagMode || persona.diagPermanent;
    const sidebarClass = ['eb-sidebar', isActive ? 'eb-sidebar--active' : '', className].join(' ').trim();
    const cssVars = { '--eb-accent': persona.accentColor, '--eb-glow': persona.accentGlow };

    const pillLabel = persona.diagLabel ?? (persona.diagPermanent ? 'SYS' : 'DIAG');
    const placeholder = isActive
        ? `${persona.name} DIAG — what needs fixing?`
        : `Ask ${persona.name}… (Enter to send)`;

    return (
        <aside className={sidebarClass} style={cssVars} aria-label={`${persona.name} AI Sidebar`}>

            {/* Header */}
            <div className="eb-header">
                <div className="eb-header__title">
                    <span className="eb-header__icon">{persona.icon}</span>
                    <span>{persona.name}</span>
                    {persona.icon2 && <span className="eb-header__icon2">{persona.icon2}</span>}
                    {isActive && <span className="eb-header__pill">{pillLabel}</span>}
                </div>
                {!persona.diagPermanent && (
                    <DiagnosisToggle
                        active={diag.diagMode}
                        isTransitioning={diag.isTransitioning}
                        onToggle={diag.toggleDiagMode}
                        disabled={loading}
                        accentColor={persona.accentColor}
                    />
                )}
            </div>

            {/* Messages */}
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
                {/* Always-on ambient scanner */}
                <div className={`eb-kitt ${loading ? '' : 'eb-kitt--ambient'}`}
                    aria-label={loading ? `${persona.name} thinking` : `${persona.name} standby`}>
                    <span className="eb-kitt__label">
                        {loading ? (persona.scannerLabel ?? 'Scanning…') : 'Standby'}
                    </span>
                    <div className="eb-kitt__track">
                        <div className="eb-kitt__orb" />
                    </div>
                </div>
                <div ref={bottomRef} />
            </div>

            {/* Execution Card */}
            {pendingAction && (
                <ExecutionCard
                    proposal={pendingAction}
                    onExecute={handleExecuteAction}
                    onCancel={handleCancelAction}
                    loading={executeLoading}
                />
            )}

            {/* Context chips */}
            {isActive && persona.chips?.length > 0 && (
                <ContextChips chips={diag.chips} onChipClick={sendMessage} disabled={loading} />
            )}

            {/* Input row */}
            <div className="eb-input-row">
                <textarea
                    ref={inputRef}
                    className="eb-input"
                    value={input}
                    onChange={e => { setInput(e.target.value); diag.resetInteraction?.(); }}
                    onKeyDown={handleKeyDown}
                    placeholder={placeholder}
                    rows={1}
                    disabled={loading}
                    aria-label="Chat input"
                />
                <button
                    type="button"
                    className={`eb-mic ${isVoiceRecording ? 'eb-mic--recording' : ''}`}
                    onClick={toggleVoiceInput}
                    disabled={loading}
                    title={isVoiceRecording ? 'Stop recording' : 'Voice input'}
                    aria-label={isVoiceRecording ? 'Stop recording' : 'Voice input'}
                >
                    {isVoiceRecording ? '⏹' : '🎤'}
                </button>
                <button
                    type="button"
                    className="eb-send"
                    onClick={() => sendMessage(input)}
                    disabled={loading || !input.trim()}
                    aria-label="Send message"
                >➤</button>
            </div>
        </aside>
    );
}

export default EngineeringBaySidebar;
