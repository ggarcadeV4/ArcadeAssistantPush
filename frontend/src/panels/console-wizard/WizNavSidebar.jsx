import React from 'react'
import './WizNavSidebar.css'

const NAV_ITEMS = [
    { id: 'dashboard', icon: 'dashboard', label: 'Overview' },
    { id: 'diff', icon: 'difference', label: 'Visual Diff' },
    { id: 'logs', icon: 'list_alt', label: 'Logs' },
]

export default function WizNavSidebar({ activeTab, onTabChange, onChatToggle }) {
    return (
        <nav className="wiz-nav" role="tablist" aria-label="Console Wizard Navigation">
            <div className="wiz-nav__brand">
                <span className="wiz-nav__icon material-symbols-outlined">terminal</span>
                <span className="wiz-nav__title">WIZ</span>
            </div>

            <div className="wiz-nav__items">
                <button type="button" className="wiz-nav__item" onClick={onChatToggle} title="Chat with Wiz">
                    <span className="material-symbols-outlined">chat</span>
                    <span className="wiz-nav__label">Chat</span>
                </button>
                {NAV_ITEMS.map(item => (
                    <button
                        key={item.id}
                        role="tab"
                        aria-selected={activeTab === item.id}
                        className={`wiz-nav__item ${activeTab === item.id ? 'wiz-nav__item--active' : ''}`}
                        onClick={() => onTabChange(item.id)}
                        title={item.label}
                    >
                        <span className="material-symbols-outlined">{item.icon}</span>
                        <span className="wiz-nav__label">{item.label}</span>
                    </button>
                ))}
            </div>

            <div className="wiz-nav__footer">
                <div className="wiz-nav__status">
                    <span className="wiz-nav__status-dot" />
                    <span className="wiz-nav__status-text">Online</span>
                </div>
            </div>
        </nav>
    )
}
