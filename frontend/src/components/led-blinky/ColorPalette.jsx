/**
 * ColorPalette — Arcade-themed color swatch picker for Design Mode.
 *
 * Renders a row of 12 color circles with glow effects.
 * Includes fill-all, clear, and profile save/load controls.
 */
import React, { useState } from 'react'

const ColorPalette = ({
    colors = [],
    selectedColor,
    onColorSelect,
    onFillAll,
    onClearAll,
    onSaveProfile,
    onLoadProfile,
    onDeleteProfile,
    profileNames = [],
    activeProfileName,
    hasChanges,
}) => {
    const [showProfileMenu, setShowProfileMenu] = useState(false)
    const [newProfileName, setNewProfileName] = useState('')

    const handleSave = () => {
        if (newProfileName.trim()) {
            onSaveProfile(newProfileName.trim())
            setNewProfileName('')
            setShowProfileMenu(false)
        }
    }

    return (
        <div className="color-palette">
            {/* ── Swatch Row ─────────────────────────────── */}
            <div className="color-palette__swatches">
                {colors.map(color => (
                    <button
                        key={color.id}
                        className={`color-palette__swatch ${selectedColor === color.hex ? 'color-palette__swatch--active' : ''}`}
                        style={{
                            backgroundColor: color.hex,
                            boxShadow: selectedColor === color.hex
                                ? `0 0 12px ${color.hex}, 0 0 24px ${color.hex}40`
                                : 'none',
                        }}
                        onClick={() => onColorSelect(color.hex)}
                        title={color.label}
                    >
                        {selectedColor === color.hex && (
                            <span className="color-palette__check">✓</span>
                        )}
                    </button>
                ))}
            </div>

            {/* ── Action Buttons ──────────────────────────── */}
            <div className="color-palette__actions">
                <button
                    className="color-palette__action-btn"
                    onClick={onFillAll}
                    title="Fill all buttons with selected color"
                >
                    🪣 Fill All
                </button>
                <button
                    className="color-palette__action-btn"
                    onClick={onClearAll}
                    disabled={!hasChanges}
                    title="Clear all custom colors"
                >
                    🗑 Clear
                </button>

                {/* Profile dropdown */}
                <div className="color-palette__profile-menu">
                    <button
                        className="color-palette__action-btn"
                        onClick={() => setShowProfileMenu(!showProfileMenu)}
                    >
                        💾 Profiles {activeProfileName ? `(${activeProfileName})` : ''}
                    </button>

                    {showProfileMenu && (
                        <div className="color-palette__dropdown">
                            {/* Save new profile */}
                            <div className="color-palette__dropdown-row">
                                <input
                                    className="color-palette__profile-input"
                                    placeholder="Profile name…"
                                    value={newProfileName}
                                    onChange={(e) => setNewProfileName(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                                />
                                <button
                                    className="color-palette__dropdown-btn color-palette__dropdown-btn--save"
                                    onClick={handleSave}
                                    disabled={!newProfileName.trim() || !hasChanges}
                                >
                                    Save
                                </button>
                            </div>

                            {/* Saved profiles list */}
                            {profileNames.length === 0 && (
                                <div className="color-palette__dropdown-empty">No saved profiles</div>
                            )}
                            {profileNames.map(name => (
                                <div key={name} className="color-palette__dropdown-row">
                                    <button
                                        className={`color-palette__dropdown-btn color-palette__dropdown-btn--load ${activeProfileName === name ? 'color-palette__dropdown-btn--active' : ''}`}
                                        onClick={() => {
                                            onLoadProfile(name)
                                            setShowProfileMenu(false)
                                        }}
                                    >
                                        {name}
                                    </button>
                                    <button
                                        className="color-palette__dropdown-btn color-palette__dropdown-btn--delete"
                                        onClick={() => onDeleteProfile(name)}
                                        title={`Delete "${name}"`}
                                    >
                                        ✕
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}

export default ColorPalette
