import React, {
    useState,
    useRef,
    useEffect,
    useCallback,
    memo,
} from 'react';
import './WizSidebar.css';
import { speak, stopSpeaking } from '../../services/ttsClient';
import { logChatHistory } from '../../services/supabaseClient';
import { useDiagnosisMode } from '../../hooks/useDiagnosisMode';
import { DiagnosisToggle } from '../controller/DiagnosisToggle';
import { ContextChips } from '../controller/ContextChips';
import { MicButton } from '../controller/MicButton';
import { ExecutionCard } from '../controller/ExecutionCard';
import { assembleWizContext } from './wizContextAssembler';
import { WIZ_CHIPS } from './wizChips';

// ── Wiz TTS Voice ─────────────────────────────────────────────────────────────
const WIZ_VOICE_ID = 'CwhRBWXzGAHq8TQ4Fs17';

// ── API ───────────────────────────────────────────────────────────────────────
async function wizardAIChat({ message, history, isDiagnosisMode, extraContext }) {
    const res = await fetch('/api/local/console_wizard/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-panel': 'console-wizard',
            'x-scope': 'state',
            'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
        },
        body: JSON.stringify({ message, history, isDiagnosisMode, extraContext }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? 'Wiz AI request failed');
    }
    return res.json();
}

// ── Action block parser ───────────────────────────────────────────────────────
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

// ── Sub-components ────────────────────────────────────────────────────────────
const MessageBubble = memo(({ msg }) => {
    const ts = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (msg.role === 'assistant') {
        return (
            <div className="wsb-msg wsb-msg--assistant">
                <span className="wsb-msg__avatar">🧙</span>
                <div>
                    <p className="wsb-msg__text">{msg.content}</p>
                    <span className="wsb-msg__time">{ts}</span>
                </div>
            </div>
        );
    }
    if (msg.role === 'system') {
        return (
            <div className="wsb-msg wsb-msg--system">
                <p className="wsb-msg__text">{msg.content}</p>
            </div>
        );
    }
    return (
        <div className="wsb-msg wsb-msg--user">
            <p className="wsb-msg__text">{msg.content}</p>
            <span className="wsb-msg__time">{ts}</span>
        </div>
    );
});
MessageBubble.displayName = 'WizMessageBubble';

// ── Main component ────────────────────────────────────────────────────────────
export default function WizSidebar({ className = '' }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [isListening, setIsListening] = useState(false);
    const [pendingAction, setPendingAction] = useState(null);
    const [executeLoading, setExecuteLoading] = useState(false);

    const bottomRef = useRef(null);
    const inputRef = useRef(null);
    const messagesRef = useRef(messages);

    useEffect(() => { messagesRef.current = messages; }, [messages]);

    // ── Diagnosis Mode ────────────────────────────────────────────────────────
    const handleTimeout = useCallback(() => {
        addMessage('⏱️ Diagnosis Mode timed out after 5 minutes of inactivity.', 'system');
    }, []);

    const diag = useDiagnosisMode({
        panelId: 'console-wizard',
        contextAssembler: assembleWizContext,
        entryGreeting: 'Diagnosis Mode activated. Your emulator health and controllers are loaded. What needs fixing?',
        chips: WIZ_CHIPS,
        voiceId: WIZ_VOICE_ID,
        ttsSpeak: speak,
        ttsStop: stopSpeaking,
        onTimeout: handleTimeout,
    });

    // ── Scroll to bottom ──────────────────────────────────────────────────────
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, loading]);

    // ── addMessage helper ─────────────────────────────────────────────────────
    const addMessage = useCallback((content, role = 'assistant') => {
        setMessages((prev) => [
            ...prev,
            { id: Date.now() + Math.random(), role, content, timestamp: new Date().toISOString() },
        ]);
    }, []);

    // ── sendMessage ───────────────────────────────────────────────────────────
    const sendMessage = useCallback(async (text) => {
        const trimmed = (text ?? '').trim();
        if (!trimmed || loading) return;

        setInput('');
        diag.resetInteraction();
        addMessage(trimmed, 'user');
        setLoading(true);
        setPendingAction(null);

        // Build history from current messages (last 10 turns max)
        const history = messagesRef.current
            .filter((m) => m.role === 'user' || m.role === 'assistant')
            .slice(-10)
            .map((m) => ({ role: m.role, content: m.content }));

        try {
            const extraContext = diag.diagMode ? diag.context : null;
            const { reply } = await wizardAIChat({
                message: trimmed,
                history,
                isDiagnosisMode: diag.diagMode,
                extraContext,
            });

            const { action, cleanText } = parseActionBlock(reply);
            addMessage(cleanText, 'assistant');
            if (action) setPendingAction(action);

            if (diag.diagMode) {
                speak(cleanText.split('.')[0], { voice_id: WIZ_VOICE_ID });  // First sentence only in Diagnosis Mode
            } else {
                speak(cleanText, { voice_id: WIZ_VOICE_ID });
            }

            // Log to Supabase
            logChatHistory?.({
                panel: 'console-wizard',
                userMessage: trimmed,
                assistantReply: cleanText,
                isDiagnosisMode: diag.diagMode,
            }).catch(() => { });

        } catch (err) {
            addMessage(`⚠️ ${err.message ?? 'Wiz is unreachable. Check the backend.'}`, 'system');
        } finally {
            setLoading(false);
        }
    }, [loading, diag, addMessage]);

    // ── Execute action ────────────────────────────────────────────────────────
    const handleExecuteAction = useCallback(async (action) => {
        setExecuteLoading(true);
        try {
            const res = await fetch(action.endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-panel': 'console-wizard',
                    'x-scope': 'config',
                    'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
                },
                body: JSON.stringify(action.payload ?? {}),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail ?? 'Action failed');
            }
            addMessage(`✅ ${action.description ?? 'Fix applied successfully.'}`, 'system');
            setPendingAction(null);
        } catch (err) {
            addMessage(`❌ Execute failed: ${err.message}`, 'system');
        } finally {
            setExecuteLoading(false);
        }
    }, [addMessage]);

    const handleCancelAction = useCallback(() => {
        addMessage('❌ Fix cancelled.', 'system');
        setPendingAction(null);
    }, [addMessage]);

    // ── Keyboard submit ───────────────────────────────────────────────────────
    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(input);
        }
    }, [input, sendMessage]);

    // ── Voice transcript ──────────────────────────────────────────────────────
    const handleTranscript = useCallback((transcript) => {
        diag.resetInteraction();
        sendMessage(transcript);
    }, [sendMessage, diag]);

    // ── Sidebar class ─────────────────────────────────────────────────────────
    const sidebarClass = [
        'wiz-sidebar',
        diag.diagMode ? 'wiz-sidebar--diagnosis' : '',
        className,
    ].join(' ').trim();

    return (
        <aside className={sidebarClass} aria-label="Wiz AI Sidebar">

            {/* ── Header ─────────────────────────────────────────────────────── */}
            <div className="wsb-header">
                <div className="wsb-header__title">
                    <span className="wsb-header__icon">🧙</span>
                    <span>Wiz</span>
                    <span className="wsb-header__joystick" title="Arcade stick optimized">🕹️</span>
                    <span className="wsb-header__gamepad" title="Console controller support">🎮</span>
                    {diag.diagMode && (
                        <span className="wsb-header__diag-badge">DIAG</span>
                    )}
                </div>
                <DiagnosisToggle
                    active={diag.diagMode}
                    isTransitioning={diag.isTransitioning}
                    onToggle={diag.toggleDiagMode}
                    disabled={loading}
                    accentColor="var(--wiz-green)"
                />
            </div>

            {/* ── Message list ─────────────────────────────────────────────────── */}
            <div className="wsb-messages" role="log" aria-live="polite" aria-label="Chat messages">
                {messages.length === 0 && (
                    <div className="wsb-empty">
                        <span className="wsb-empty__icon">🧙</span>
                        {diag.diagMode
                            ? 'Diagnosis Mode active. Ask Wiz about your emulators or controllers.'
                            : 'Wiz is standing by.\nAsk about console controllers, emulator configs, or toggle DIAG to run diagnostics.'}
                    </div>
                )}
                {messages.map((msg) => (
                    <MessageBubble key={msg.id} msg={msg} />
                ))}
                {/* Always-on ambient scanner — dims when idle, bright when loading */}
                <div className={`wsb-kitt ${loading ? '' : 'wsb-kitt--ambient'}`}
                    aria-label={loading ? 'Wiz is scanning' : 'Wiz standby'}
                    aria-live={loading ? 'polite' : undefined}>
                    <span className="wsb-kitt__label">{loading ? 'Scanning…' : 'Standby'}</span>
                    <div className="wsb-kitt__track">
                        <div className="wsb-kitt__orb" />
                    </div>
                </div>
                <div ref={bottomRef} />
            </div>

            {/* ── Execution Card ─────────────────────────────────────────────── */}
            {pendingAction && (
                <ExecutionCard
                    proposal={pendingAction}
                    onExecute={handleExecuteAction}
                    onCancel={handleCancelAction}
                    loading={executeLoading}
                />
            )}

            {/* ── Context chips ───────────────────────────────────────────────── */}
            {diag.diagMode && (
                <ContextChips
                    chips={diag.chips}
                    onChipClick={sendMessage}
                    disabled={loading}
                />
            )}

            {/* ── Input row ────────────────────────────────────────────────────── */}
            <div className="wsb-input-row">
                <textarea
                    ref={inputRef}
                    className="wsb-input"
                    value={input}
                    onChange={(e) => {
                        setInput(e.target.value);
                        diag.resetInteraction();
                    }}
                    onKeyDown={handleKeyDown}
                    placeholder={diag.diagMode
                        ? 'What needs fixing? (Enter to send)'
                        : 'Ask Wiz… (Enter to send)'}
                    rows={1}
                    disabled={loading}
                    aria-label="Chat input"
                />

                <MicButton
                    onTranscript={handleTranscript}
                    onListeningChange={setIsListening}
                    stopTTS={stopSpeaking}
                    disabled={loading}
                />

                <button
                    type="button"
                    className="wsb-send"
                    onClick={() => sendMessage(input)}
                    disabled={loading || !input.trim()}
                    aria-label="Send message"
                >
                    ➤
                </button>
            </div>

        </aside>
    );
}
