/**
 * Button mapping utilities for LED profile data.
 * Converts between form-key format (p1_button1) and logical-key format (p1.button1).
 * Extracted from LEDBlinkyPanel.jsx for reuse across hooks and components.
 */

export const DEFAULT_MAPPING_FORM = Object.freeze({
    p1_button1: '#FF0000',
    p1_button2: '#00FF00',
    p1_button3: '#0000FF',
    p1_button4: '#FFFF00',
    p2_button1: '#FF00FF',
    p2_button2: '#00FFFF',
    p2_button3: '#FF8800',
    p2_button4: '#8800FF'
})

export const PLAYER_KEYS = ['player1', 'player2', 'player3', 'player4']
export const FORM_KEY_REGEX = /^p(\d+)_button(\d+)$/i
export const LOGICAL_KEY_REGEX = /^p(\d+)\.(button\d+)$/i

export const normalizeButtonValue = (value) => {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        return { ...value }
    }
    if (typeof value === 'string' && value.trim()) {
        return { color: value.trim() }
    }
    if (value === null || value === undefined) {
        return {}
    }
    return { color: String(value) }
}

export const extractButtonsFromPayload = (payload = {}) => {
    const buttons = {}
    const register = (key, value) => {
        if (!key) return
        const normalizedKey = key.trim()
        if (!normalizedKey) return
        buttons[normalizedKey] = normalizeButtonValue(value)
    }

    if (payload.buttons && typeof payload.buttons === 'object') {
        Object.entries(payload.buttons).forEach(([logicalKey, value]) => register(logicalKey, value))
    }

    PLAYER_KEYS.forEach((playerKey, playerIndex) => {
        const playerSection = payload[playerKey]
        if (playerSection && typeof playerSection === 'object') {
            Object.entries(playerSection).forEach(([buttonKey, value]) => {
                register(`p${playerIndex + 1}.${buttonKey}`, value)
            })
        }
    })

    Object.entries(payload).forEach(([key, value]) => {
        if (LOGICAL_KEY_REGEX.test(key)) {
            register(key, value)
        }
    })

    return buttons
}

export const buildFormFromButtons = (buttons = {}) => {
    const form = { ...DEFAULT_MAPPING_FORM }
    Object.entries(buttons).forEach(([logicalKey, value]) => {
        const match = logicalKey.match(LOGICAL_KEY_REGEX)
        if (!match) return
        const [, player, buttonKey] = match
        const formKey = `p${player}_${buttonKey.toLowerCase()}`
        const color = typeof value === 'string' ? value : value?.color
        if (form[formKey] && color) {
            form[formKey] = color
        }
    })
    return form
}

export const buildButtonsFromForm = (form = {}) => {
    const buttons = {}
    Object.entries(form).forEach(([formKey, color]) => {
        const match = formKey.match(FORM_KEY_REGEX)
        if (!match) return
        const [, player, buttonIndex] = match
        buttons[`p${player}.button${buttonIndex}`] = { color }
    })
    return buttons
}
