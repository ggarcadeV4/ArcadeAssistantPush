/**
 * ContextChips.jsx
 * ═══════════════════════════════════════════════════════════════════
 * Horizontally scrollable row of suggestion chips.
 * Renders below the chat input row in Diagnosis Mode.
 */

import React from 'react';
import './ContextChips.css';

export function ContextChips({ chips = [], onChipClick, disabled = false }) {
    if (!chips.length) return null;

    return (
        <div className="ctx-chips" role="list" aria-label="Quick diagnosis prompts">
            {chips.map((chip) => (
                <button
                    key={chip.id}
                    type="button"
                    role="listitem"
                    className="ctx-chip"
                    onClick={() => onChipClick?.(chip.prompt)}
                    disabled={disabled}
                    title={chip.prompt}
                >
                    {chip.label}
                </button>
            ))}
        </div>
    );
}
