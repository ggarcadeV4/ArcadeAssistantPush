/**
 * chuckChips.js
 * ═══════════════════════════════════════════════════════════════════
 * Suggestion chips for Controller Chuck's Diagnosis Mode sidebar.
 * Rendered by ContextChips.jsx below the chat input.
 *
 * Each chip: { id, label, prompt }
 *   - id     : unique key
 *   - label  : visible button text (keep short — 2–3 words)
 *   - prompt : message auto-sent to AI when chip is tapped
 */

export const chuckChips = [
    {
        id: 'scan',
        label: '🔍 Scan Devices',
        prompt: 'Scan for connected encoder boards and USB controller devices right now.',
    },
    {
        id: 'status',
        label: '⚡ Board Status',
        prompt: "What's the live status of the encoder board? Is anything failing or disconnected?",
    },
    {
        id: 'mapping',
        label: '🎮 Show Mapping',
        prompt: 'Show me a summary of the current button-to-GPIO pin mapping for all players.',
    },
    {
        id: 'mame',
        label: '🕹️ MAME Config',
        prompt: 'Generate or review the MAME config file from the current controller mapping.',
    },
    {
        id: 'sacred',
        label: '📋 Button Law',
        prompt: 'Remind me of the sacred button numbering law (1-2-3-7 / 4-5-6-8) and why it matters.',
    },
    {
        id: 'fix',
        label: '🔧 Fix It',
        prompt: 'Based on what you can see right now, what should I fix first?',
    },
];
