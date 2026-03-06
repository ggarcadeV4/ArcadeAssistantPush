/**
 * wizChips.js — Diagnosis Mode context chips for Console Wizard (WIZ)
 *
 * 4 chips shown when Diagnosis Mode is active.
 * Each chip sends a pre-filled message via sendMessage().
 */

export const WIZ_CHIPS = [
    {
        id: 'fix_buttons',
        label: 'Fix My Buttons',
        prompt: 'My buttons work on the cabinet but they\'re wrong in the emulator. Can you fix the config?',
    },
    {
        id: 'sync_chuck',
        label: 'Sync from Chuck',
        prompt: 'I just remapped buttons in Controller Chuck. Sync all my emulator configs to match.',
    },
    {
        id: 'scan_devices',
        label: 'Scan Devices',
        prompt: 'Scan connected controllers and check their driver profiles.',
    },
    {
        id: 'view_drivers',
        label: 'Check Health',
        prompt: 'Show me the current emulator health and any configs that have drifted from defaults.',
    },
    {
        id: 'test_input',
        label: 'Test Input',
        prompt: 'How do I test if my controller inputs are being correctly mapped in RetroArch?',
    },
    {
        id: 'reset_profile',
        label: 'Restore Defaults',
        prompt: 'I need to restore all emulator configs back to their default Golden state.',
    },
];
