/**
 * ColorPalette - Arcade-themed color swatch picker for Design Mode.
 *
 * Renders a row of 12 color circles with glow effects.
 * Includes fill-all, clear, and local-draft save/load controls.
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
            <div className="color-palette__swatches">
                {colors.map((color) => (
                    <button
                        key={color.id}
                        className={`color-palette__swatch ${selectedColor === color.hex ? 'color-palette__swatch--active' : ''}`}
                        style={{
                            backgroundColor: color.hex,
                            boxShadow:
                                selectedColor === color.hex
                                    ? `0 0 12px ${color.hex}, 0 0 24px ${color.hex}40`
                                    : 'none',
                        }}
                        onClick={() => onColorSelect(color.hex)}
                        title={color.label}
                    >
                        {selectedColor === color.hex && (
                            <span className="color-palette__check">OK</span>
                        )}
                    </button>
                ))}
            </div>

            <div className="color-palette__actions">
                <button
                    className="color-palette__action-btn"
                    onClick={onFillAll}
                    title="Fill all buttons with selected color"
                >
                    Fill All
                </button>
                <button
                    className="color-palette__action-btn"
                    onClick={onClearAll}
                    disabled={!hasChanges}
                    title="Clear all custom colors"
                >
                    Clear
                </button>

                <div className="color-palette__profile-menu">
                    <button
                        className="color-palette__action-btn"
                        onClick={() => setShowProfileMenu(!showProfileMenu)}
                    >
                        Local Drafts {activeProfileName ? `(${activeProfileName})` : ''}
                    </button>

                    {showProfileMenu && (
                        <div className="color-palette__dropdown">
                            <div className="color-palette__dropdown-row">
                                <input
                                    className="color-palette__profile-input"
                                    placeholder="Draft name..."
                                    value={newProfileName}
                                    onChange={(event) => setNewProfileName(event.target.value)}
                                    onKeyDown={(event) => event.key === 'Enter' && handleSave()}
                                />
                                <button
                                    className="color-palette__dropdown-btn color-palette__dropdown-btn--save"
                                    onClick={handleSave}
                                    disabled={!newProfileName.trim() || !hasChanges}
                                >
                                    Save
                                </button>
                            </div>

                            {profileNames.length === 0 && (
                                <div className="color-palette__dropdown-empty">No local drafts</div>
                            )}
                            {profileNames.map((name) => (
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
                                        X
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
