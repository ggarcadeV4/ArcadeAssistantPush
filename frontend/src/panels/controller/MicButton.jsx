/**
 * MicButton.jsx
 * ═══════════════════════════════════════════════════════════════════
 * Push-to-talk microphone button using Web Speech API.
 *
 * Decision refs (diagnosis_mode_plan.md):
 *   Q3  — No always-on listening; mic is cold until pressed
 *   Q11 — PTT is the gate; TTS auto-disabled while mic is hot;
 *          confidence threshold ≥ 0.7 before passing transcript
 *
 * startRef — optional ref that the parent can call to programmatically
 *            start listening (used for hands-free diagnostic auto-resume).
 * autoMode — when true, single-click toggles listening on/off instead
 *            of requiring hold-to-speak.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import './MicButton.css';

const MIN_CONFIDENCE = 0.7;

export function MicButton({ onTranscript, onListeningChange, disabled, stopTTS, startRef, autoMode = false }) {
    const [listening, setListening] = useState(false);
    const [micError, setMicError] = useState(null);
    const recognitionRef = useRef(null);

    // ── Start listening ────────────────────────────────────────────────────────
    const startListening = useCallback(() => {
        if (listening) return;
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            setMicError('Speech recognition not supported in this browser.');
            return;
        }

        // Q11: disable TTS while mic is hot — prevents feedback loop
        try { stopTTS?.(); } catch { /* noop */ }

        const rec = new SpeechRecognition();
        rec.lang = 'en-US';
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        rec.continuous = false;

        rec.onresult = (e) => {
            const result = e.results[0]?.[0];
            const transcript = result?.transcript ?? '';
            const confidence = result?.confidence ?? 0;

            // Q11: confidence threshold — drop low-confidence results (arcade noise)
            if (confidence < MIN_CONFIDENCE) {
                console.warn('[MicButton] Low confidence discarded', { transcript, confidence });
                return;
            }

            onTranscript?.(transcript.trim());
        };

        rec.onerror = (e) => {
            console.warn('[MicButton] SpeechRecognition error', e.error);
            if (e.error !== 'no-speech') {
                setMicError(e.error);
            }
            setListening(false);
            onListeningChange?.(false);
        };

        rec.onend = () => {
            setListening(false);
            onListeningChange?.(false);
        };

        rec.start();
        recognitionRef.current = rec;
        setListening(true);
        setMicError(null);
        onListeningChange?.(true);
    }, [listening, onTranscript, onListeningChange, stopTTS]);

    // ── Stop listening ─────────────────────────────────────────────────────────
    const stopListening = useCallback(() => {
        try { recognitionRef.current?.stop(); } catch { /* noop */ }
        setListening(false);
        onListeningChange?.(false);
    }, [onListeningChange]);

    // ── Expose startListening to parent via ref ────────────────────────────────
    useEffect(() => {
        if (startRef) startRef.current = startListening;
    }, [startRef, startListening]);

    // ── Toggle handler for autoMode ────────────────────────────────────────────
    const handleClick = useCallback(() => {
        if (listening) {
            stopListening();
        } else {
            startListening();
        }
    }, [listening, startListening, stopListening]);

    return (
        <div className="mic-btn-wrap">
            <button
                type="button"
                className={`mic-btn ${listening ? 'mic-btn--hot' : ''}`}
                {...(autoMode
                    ? { onClick: handleClick }
                    : {
                        onMouseDown: startListening,
                        onMouseUp: stopListening,
                        onMouseLeave: listening ? stopListening : undefined,
                        onTouchStart: startListening,
                        onTouchEnd: stopListening,
                    }
                )}
                disabled={disabled}
                aria-label={listening ? 'Listening — release to send' : (autoMode ? 'Click to speak' : 'Hold to speak')}
                title={autoMode ? 'Click to speak — auto-listen mode' : 'Push-to-talk — hold while speaking'}
            >
                {/* Ripple rings while hot */}
                {listening && (
                    <>
                        <span className="mic-btn__ring mic-btn__ring--1" />
                        <span className="mic-btn__ring mic-btn__ring--2" />
                    </>
                )}
                <span className="mic-btn__icon" aria-hidden="true">
                    {listening ? '●' : '🎤'}
                </span>
            </button>

            {micError && (
                <span className="mic-btn__error" role="alert">{micError}</span>
            )}
        </div>
    );
}
