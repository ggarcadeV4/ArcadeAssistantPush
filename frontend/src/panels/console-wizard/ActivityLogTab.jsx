import React, { useState, useCallback } from 'react'

/**
 * ActivityLogTab — Timestamped event log for Console Wizard.
 * Captures all panel events (scans, config applies, errors, controller detections).
 */

const LOG_ICONS = {
    success: { icon: 'check_circle', color: '#22C55E' },
    error: { icon: 'error', color: '#EF4444' },
    warning: { icon: 'warning', color: '#F59E0B' },
    info: { icon: 'info', color: '#3B82F6' },
    config: { icon: 'settings', color: '#A855F7' },
    scan: { icon: 'radar', color: '#06B6D4' },
}

export default function ActivityLogTab({ logs = [] }) {
    const [filter, setFilter] = useState('all')

    const filteredLogs = filter === 'all'
        ? logs
        : logs.filter(log => log.type === filter)

    const clearFilter = useCallback(() => setFilter('all'), [])

    return (
        <div className="wiz-tab-logs" role="tabpanel" aria-label="Activity Log">
            {/* ── Header ─────────────────────────────── */}
            <div className="wiz-logs-header">
                <div className="wiz-logs-header__title">
                    <span className="material-symbols-outlined" style={{ color: '#22C55E' }}>list_alt</span>
                    <h2>Activity Log</h2>
                    <span className="wiz-badge wiz-badge--info">{logs.length} events</span>
                </div>
                <div className="wiz-logs-filter">
                    {['all', 'success', 'error', 'warning', 'info'].map(f => (
                        <button
                            key={f}
                            className={`wiz-tab-btn ${filter === f ? 'wiz-tab-btn--active' : ''}`}
                            onClick={() => setFilter(f)}
                        >
                            {f.charAt(0).toUpperCase() + f.slice(1)}
                        </button>
                    ))}
                </div>
            </div>

            {/* ── Log Entries ────────────────────────── */}
            {filteredLogs.length === 0 ? (
                <div className="wiz-logs-empty">
                    <span className="material-symbols-outlined" style={{ fontSize: 48, color: 'rgba(34,197,94,0.3)' }}>
                        event_note
                    </span>
                    <h3>No Events Logged</h3>
                    <p>Activity will appear here as you interact with Console Wizard.</p>
                </div>
            ) : (
                <div className="wiz-logs-timeline">
                    {filteredLogs.map((log, idx) => {
                        const meta = LOG_ICONS[log.type] || LOG_ICONS.info
                        return (
                            <div key={log.id || idx} className="wiz-log-entry">
                                <div className="wiz-log-entry__dot" style={{ background: meta.color }} />
                                <div className="wiz-log-entry__line" />
                                <div className="wiz-log-entry__content">
                                    <div className="wiz-log-entry__header">
                                        <span className="material-symbols-outlined" style={{ color: meta.color, fontSize: 16 }}>
                                            {meta.icon}
                                        </span>
                                        <span className="wiz-log-entry__title">{log.title || log.event}</span>
                                        <span className="wiz-log-entry__time">
                                            {log.timestamp
                                                ? new Date(log.timestamp).toLocaleTimeString()
                                                : '—'}
                                        </span>
                                    </div>
                                    {log.detail && (
                                        <p className="wiz-log-entry__detail">{log.detail}</p>
                                    )}
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
