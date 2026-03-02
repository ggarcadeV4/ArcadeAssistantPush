/**
 * wizChips.js — Diagnosis Mode context chips for Console Wizard (WIZ)
 *
 * 4 chips shown when Diagnosis Mode is active.
 * Each chip sends a pre-filled message via sendMessage().
 */

export const WIZ_CHIPS = [
    {
        id: 'scan_devices',
        label: 'Scan Devices',
        prompt: 'Scan connected controllers and check their driver profiles.',
    },
    {
        id: 'view_drivers',
        label: 'View Drivers',
        prompt: 'Show me the current emulator health and any configs that have drifted from defaults.',
    },
    {
        id: 'test_input',
        label: 'Test Input',
        prompt: 'How do I test if my controller inputs are being correctly mapped in RetroArch?',
    },
    {
        id: 'reset_profile',
        label: 'Reset Profile',
        prompt: 'I need to restore an emulator config back to its default snapshot.',
    },
];
