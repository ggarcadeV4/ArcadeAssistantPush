/**
 * DiagnosisToggle.jsx
 * ═══════════════════════════════════════════════════════════════════
 * Amber pill toggle that switches between Standard ↔ Diagnosis Mode.
 * Sits in the Chuck sidebar header. Shows spinner while transitioning.
 */

import React from 'react';
import './DiagnosisToggle.css';

export function DiagnosisToggle({ active, disabled, isTransitioning, onToggle }) {
    return (
        <button
            type="button"
            className={[
                'diag-toggle',
                active ? 'diag-toggle--active' : '',
                isTransitioning ? 'diag-toggle--transitioning' : '',
            ].join(' ').trim()}
            onClick={onToggle}
            disabled={disabled || isTransitioning}
            aria-pressed={active}
            title={active ? 'Exit Diagnosis Mode' : 'Enter Diagnosis Mode'}
        >
            <span className="diag-toggle__track">
                <span className="diag-toggle__thumb" />
            </span>
            <span className="diag-toggle__label">
                {isTransitioning ? 'Loading…' : active ? 'Diagnosis' : 'Standard'}
            </span>
        </button>
    );
}
