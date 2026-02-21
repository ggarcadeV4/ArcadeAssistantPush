/**
 * UserProfileSelector — Family profile dropdown
 *
 * Shows the active user profile with avatar. Placeholder names for now;
 * will eventually wire to Vicky Voice broadcast (R-15).
 */
import React, { useState } from 'react'

const PLACEHOLDER_PROFILES = [
    { id: 'bobby', name: 'Bobby', initial: 'B', color: '#0ea5e9' },
    { id: 'guest', name: 'Guest', initial: 'G', color: '#6b7280' },
    { id: 'mom', name: 'Mom', initial: 'M', color: '#ec4899' },
    { id: 'dad', name: 'Dad', initial: 'D', color: '#f59e0b' },
    { id: 'sarah', name: 'Sarah', initial: 'S', color: '#10b981' },
]

export default function UserProfileSelector({ activeProfileId, onProfileChange }) {
    const [isOpen, setIsOpen] = useState(false)
    const activeProfile = PLACEHOLDER_PROFILES.find(p => p.id === activeProfileId) || PLACEHOLDER_PROFILES[0]

    return (
        <div style={{ position: 'relative' }}>
            {/* Profile avatars row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {PLACEHOLDER_PROFILES.slice(0, 2).map(profile => {
                    const isActive = profile.id === activeProfile.id
                    return (
                        <button
                            key={profile.id}
                            onClick={() => {
                                if (onProfileChange) onProfileChange(profile.id)
                                setIsOpen(false)
                            }}
                            style={{
                                width: 44,
                                height: 44,
                                borderRadius: '50%',
                                background: isActive
                                    ? `linear-gradient(135deg, ${profile.color}30, ${profile.color}10)`
                                    : '#1f2937',
                                border: isActive
                                    ? `2px solid ${profile.color}`
                                    : '2px solid #374151',
                                boxShadow: isActive
                                    ? `0 0 12px ${profile.color}40`
                                    : 'none',
                                color: isActive ? profile.color : '#6b7280',
                                fontSize: 16,
                                fontWeight: 700,
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                transition: 'all 0.2s ease',
                                position: 'relative',
                            }}
                            title={profile.name}
                        >
                            {profile.initial}
                        </button>
                    )
                })}

                {/* More profiles dropdown trigger */}
                {PLACEHOLDER_PROFILES.length > 2 && (
                    <button
                        onClick={() => setIsOpen(!isOpen)}
                        style={{
                            width: 32,
                            height: 32,
                            borderRadius: '50%',
                            background: '#1f2937',
                            border: '1px solid #374151',
                            color: '#6b7280',
                            fontSize: 12,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                        }}
                        title="More profiles"
                    >
                        +{PLACEHOLDER_PROFILES.length - 2}
                    </button>
                )}
            </div>

            {/* Active profile name */}
            <div style={{ textAlign: 'center', marginTop: 4 }}>
                <span style={{ color: activeProfile.color, fontSize: 11, fontWeight: 600 }}>
                    {activeProfile.name}
                </span>
            </div>

            {/* Dropdown */}
            {isOpen && (
                <div
                    style={{
                        position: 'absolute',
                        top: '100%',
                        right: 0,
                        marginTop: 8,
                        background: '#111827',
                        border: '1px solid #374151',
                        borderRadius: 8,
                        padding: 8,
                        minWidth: 160,
                        zIndex: 50,
                        boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                    }}
                >
                    {PLACEHOLDER_PROFILES.map(profile => (
                        <button
                            key={profile.id}
                            onClick={() => {
                                if (onProfileChange) onProfileChange(profile.id)
                                setIsOpen(false)
                            }}
                            style={{
                                width: '100%',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 10,
                                padding: '8px 12px',
                                background: profile.id === activeProfile.id ? `${profile.color}15` : 'transparent',
                                border: 'none',
                                borderRadius: 6,
                                color: profile.id === activeProfile.id ? profile.color : '#d1d5db',
                                fontSize: 13,
                                cursor: 'pointer',
                                transition: 'background 0.15s',
                            }}
                        >
                            <span
                                style={{
                                    width: 28,
                                    height: 28,
                                    borderRadius: '50%',
                                    background: `${profile.color}20`,
                                    border: `1px solid ${profile.color}50`,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontSize: 12,
                                    fontWeight: 700,
                                    color: profile.color,
                                }}
                            >
                                {profile.initial}
                            </span>
                            {profile.name}
                            {profile.id === activeProfile.id && (
                                <span style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.6 }}>Active</span>
                            )}
                        </button>
                    ))}
                </div>
            )}
        </div>
    )
}
