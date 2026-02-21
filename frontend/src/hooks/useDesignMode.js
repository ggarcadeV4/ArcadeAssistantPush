/**
 * useDesignMode — Hook for LED button color painting.
 *
 * When design mode is active, the user clicks buttons on the visualizer
 * and the selected color from the palette is applied. Colors are tracked
 * per-button and can be saved/loaded as named profiles.
 *
 * Usage:
 *   const design = useDesignMode({ showToast })
 *   design.selectedColor     → current brush color
 *   design.setSelectedColor  → change brush
 *   design.paintButton(player, buttonId) → apply color
 *   design.customColors      → { 'p1.button1': '#ff0000', ... }
 *   design.saveProfile(name) → persist current layout
 *   design.loadProfile(name) → restore saved layout
 */
import { useState, useCallback, useMemo } from 'react'

// ─── Curated arcade color palette ────────────────────────────────────
export const PALETTE_COLORS = [
    { id: 'red', hex: '#ef4444', label: 'Red' },
    { id: 'orange', hex: '#f97316', label: 'Orange' },
    { id: 'amber', hex: '#f59e0b', label: 'Amber' },
    { id: 'yellow', hex: '#eab308', label: 'Yellow' },
    { id: 'lime', hex: '#84cc16', label: 'Lime' },
    { id: 'green', hex: '#22c55e', label: 'Green' },
    { id: 'cyan', hex: '#06b6d4', label: 'Cyan' },
    { id: 'blue', hex: '#3b82f6', label: 'Blue' },
    { id: 'purple', hex: '#9333ea', label: 'Purple' },
    { id: 'pink', hex: '#ec4899', label: 'Pink' },
    { id: 'white', hex: '#ffffff', label: 'White' },
    { id: 'off', hex: '#1a1a2e', label: 'Off' },
]

// ─── Local storage key for saved profiles ────────────────────────────
const STORAGE_KEY = 'aa_led_design_profiles'

/**
 * Load saved profiles from localStorage
 */
function loadSavedProfiles() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY)
        return raw ? JSON.parse(raw) : {}
    } catch {
        return {}
    }
}

/**
 * Persist profiles to localStorage
 */
function persistProfiles(profiles) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(profiles))
    } catch (err) {
        console.error('[DesignMode] Failed to save profiles:', err)
    }
}

/**
 * @param {Object} opts
 * @param {Function} opts.showToast
 */
export default function useDesignMode({ showToast }) {
    const [selectedColor, setSelectedColor] = useState(PALETTE_COLORS[0].hex)
    const [customColors, setCustomColors] = useState({})
    const [savedProfiles, setSavedProfiles] = useState(() => loadSavedProfiles())
    const [activeProfileName, setActiveProfileName] = useState(null)

    // ─── Paint a button with selected color ──────────────────────────
    const paintButton = useCallback((player, buttonId) => {
        const key = `p${player}.${buttonId}`
        setCustomColors(prev => ({
            ...prev,
            [key]: selectedColor,
        }))
    }, [selectedColor])

    // ─── Clear all custom colors ─────────────────────────────────────
    const clearAll = useCallback(() => {
        setCustomColors({})
        setActiveProfileName(null)
        showToast('Design cleared', 'success')
    }, [showToast])

    // ─── Fill all buttons with selected color ────────────────────────
    const fillAll = useCallback((playerCount = 4) => {
        const filled = {}
        for (let p = 1; p <= playerCount; p++) {
            const btnCount = p <= 2 ? 8 : 4
            for (let i = 1; i <= btnCount; i++) {
                filled[`p${p}.button${i}`] = selectedColor
            }
            filled[`p${p}.start`] = selectedColor
            filled[`p${p}.coin`] = selectedColor
        }
        setCustomColors(filled)
        showToast('All buttons filled', 'success')
    }, [selectedColor, showToast])

    // ─── Save current layout as a named profile ──────────────────────
    const saveProfile = useCallback((name) => {
        if (!name?.trim()) {
            showToast('Profile name required', 'error')
            return
        }
        const profiles = { ...savedProfiles, [name]: { ...customColors } }
        setSavedProfiles(profiles)
        persistProfiles(profiles)
        setActiveProfileName(name)
        showToast(`Profile "${name}" saved`, 'success')
    }, [customColors, savedProfiles, showToast])

    // ─── Load a saved profile ────────────────────────────────────────
    const loadProfile = useCallback((name) => {
        const profile = savedProfiles[name]
        if (!profile) {
            showToast(`Profile "${name}" not found`, 'error')
            return
        }
        setCustomColors({ ...profile })
        setActiveProfileName(name)
        showToast(`Loaded "${name}"`, 'success')
    }, [savedProfiles, showToast])

    // ─── Delete a saved profile ──────────────────────────────────────
    const deleteProfile = useCallback((name) => {
        const profiles = { ...savedProfiles }
        delete profiles[name]
        setSavedProfiles(profiles)
        persistProfiles(profiles)
        if (activeProfileName === name) setActiveProfileName(null)
        showToast(`Profile "${name}" deleted`, 'success')
    }, [savedProfiles, activeProfileName, showToast])

    // ─── Profile names list ──────────────────────────────────────────
    const profileNames = useMemo(() => Object.keys(savedProfiles), [savedProfiles])

    // ─── Has any custom colors? ──────────────────────────────────────
    const hasChanges = Object.keys(customColors).length > 0

    return {
        // Brush
        selectedColor,
        setSelectedColor,

        // Button colors
        customColors,
        paintButton,
        clearAll,
        fillAll,
        hasChanges,

        // Profiles
        saveProfile,
        loadProfile,
        deleteProfile,
        profileNames,
        activeProfileName,

        // Constants
        PALETTE_COLORS,
    }
}
