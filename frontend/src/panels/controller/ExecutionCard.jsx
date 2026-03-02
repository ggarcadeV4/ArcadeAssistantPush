/**
 * ExecutionCard.jsx
 * ═══════════════════════════════════════════════════════════════════
 * V1 Safety Gate — renders whenever Diagnosis Mode AI proposes a
 * write action. User must physically click EXECUTE or CANCEL.
 *
 * Constitution rule: "The AI NEVER writes autonomously.
 * Every write requires a physical EXECUTE tap."
 *
 * Props:
 *   proposal  — { display: string, payload: object }
 *   onExecute — async fn(payload) → void
 *   onCancel  — fn() → void
 *   loading   — bool (show spinner during commit)
 */

import React, { useState, memo } from 'react';
import './ExecutionCard.css';

export const ExecutionCard = memo(function ExecutionCard({
    proposal,
    onExecute,
    onCancel,
    loading = false,
}) {
    const [confirming, setConfirming] = useState(false);
    const [error, setError] = useState(null);

    const handleExecute = async () => {
        if (confirming) return;
        setConfirming(true);
        setError(null);
        try {
            await onExecute?.(proposal.payload);
        } catch (err) {
            setError(err?.message ?? 'Execution failed. Check logs.');
            setConfirming(false);
        }
    };

    return (
        <div className={`exec-card ${confirming ? 'exec-card--running' : ''}`} role="region" aria-label="Proposed fix">
            <div className="exec-card__header">
                <span className="exec-card__icon">🔧</span>
                <span className="exec-card__label">Proposed Fix</span>
            </div>

            <p className="exec-card__display">{proposal?.display ?? 'Unknown action'}</p>

            {error && (
                <p className="exec-card__error" role="alert">⚠️ {error}</p>
            )}

            <div className="exec-card__actions">
                <button
                    type="button"
                    className="exec-card__btn exec-card__btn--execute"
                    onClick={handleExecute}
                    disabled={confirming || loading}
                    aria-label="Execute proposed fix"
                >
                    {confirming ? '⏳ Applying…' : '✅ EXECUTE'}
                </button>
                <button
                    type="button"
                    className="exec-card__btn exec-card__btn--cancel"
                    onClick={onCancel}
                    disabled={confirming || loading}
                    aria-label="Cancel proposed fix"
                >
                    ✕ CANCEL
                </button>
            </div>
        </div>
    );
});

ExecutionCard.displayName = 'ExecutionCard';
