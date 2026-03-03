import React, { useMemo } from 'react'

/**
 * TeknoParrotTab — TeknoParrot Hub with game-card grid.
 * V2 design: game cards with platform badges, last-sync timestamps, and sync status.
 */

const PLATFORM_BADGES = {
    'Sega RingEdge 2': { label: 'RingEdge 2', color: '#3B82F6' },
    'Sega RingEdge': { label: 'RingEdge', color: '#6366F1' },
    'Sega Lindbergh': { label: 'Lindbergh', color: '#8B5CF6' },
    'Namco System ES3': { label: 'ES3', color: '#EF4444' },
    'Namco System 357': { label: 'Sys 357', color: '#F97316' },
    'Taito Type X': { label: 'Type X', color: '#14B8A6' },
    'Taito Type X2': { label: 'Type X2', color: '#06B6D4' },
    'Examu Ex-Board': { label: 'Ex-Board', color: '#EC4899' },
    racing: { label: 'Racing', color: '#22C55E' },
    fighting: { label: 'Fighting', color: '#EF4444' },
    shooting: { label: 'Shooting', color: '#F59E0B' },
    rhythm: { label: 'Rhythm', color: '#A855F7' },
}

function getPlatformBadge(game) {
    if (game.hardware) {
        return PLATFORM_BADGES[game.hardware] || { label: game.hardware, color: '#6B7280' }
    }
    if (game.category) {
        return PLATFORM_BADGES[game.category] || { label: game.category, color: '#6B7280' }
    }
    return { label: 'Arcade', color: '#6B7280' }
}

export default function TeknoParrotTab({
    tpGames,
    tpSelectedGame,
    setTpSelectedGame,
    tpPreviewLoading,
    tpApplyLoading,
    tpPreviewResult,
    tpApplyResult,
    tpError,
    handleTpPreflight,
    handleTpApply,
    setTpPreviewResult,
    setTpApplyResult,
    setTpError,
}) {
    const gameList = useMemo(() => {
        if (tpGames.length > 0) return tpGames
        // Fallback defaults
        return [
            { name: 'InitialD8', display_name: 'Initial D Arcade Stage 8', category: 'racing', hardware: 'Sega RingEdge 2' },
            { name: 'MarioKartGPDX', display_name: 'Mario Kart GP DX', category: 'racing', hardware: 'Namco System ES3' },
            { name: 'WanganMT5', display_name: 'Wangan Midnight Maximum Tune 5', category: 'racing', hardware: 'Namco System ES3' },
            { name: 'OutRun2SP', display_name: 'OutRun 2 SP SDX', category: 'racing', hardware: 'Sega Lindbergh' },
        ]
    }, [tpGames])

    return (
        <div className="wiz-tab-teknoparrot" role="tabpanel" aria-label="TeknoParrot">
            {/* ── Header ─────────────────────────────── */}
            <div className="wiz-tp-header">
                <div className="wiz-tp-header__title">
                    <span className="material-symbols-outlined" style={{ fontSize: 28, color: '#22C55E' }}>sports_esports</span>
                    <div>
                        <h2>TeknoParrot Hub</h2>
                        <p>High-performance arcade hardware configuration & synchronization manager</p>
                    </div>
                </div>
                <div className="wiz-tp-header__actions">
                    <button
                        className="wiz-btn wiz-btn--ghost"
                        onClick={handleTpPreflight}
                        disabled={tpPreviewLoading || tpApplyLoading || !tpSelectedGame}
                    >
                        <span className="material-symbols-outlined">search</span>
                        {tpPreviewLoading ? 'Checking...' : 'Preflight Check'}
                    </button>
                </div>
            </div>

            {/* ── Game Cards Grid ────────────────────── */}
            <div className="wiz-tp-grid">
                {gameList.map(game => {
                    const badge = getPlatformBadge(game)
                    const isSelected = tpSelectedGame === game.name
                    return (
                        <div
                            key={game.name}
                            className={`wiz-tp-card ${isSelected ? 'wiz-tp-card--selected' : ''}`}
                            onClick={() => {
                                setTpSelectedGame(game.name)
                                setTpPreviewResult(null)
                                setTpApplyResult(null)
                                setTpError(null)
                            }}
                            role="button"
                            tabIndex={0}
                        >
                            <div className="wiz-tp-card__art">
                                <span className="material-symbols-outlined" style={{ fontSize: 48, color: badge.color }}>
                                    sports_esports
                                </span>
                            </div>
                            <div className="wiz-tp-card__info">
                                <h3 className="wiz-tp-card__name">{game.display_name || game.name}</h3>
                                <div className="wiz-tp-card__meta">
                                    <span
                                        className="wiz-tp-badge"
                                        style={{ '--badge-color': badge.color }}
                                    >
                                        {badge.label}
                                    </span>
                                </div>
                            </div>
                            {isSelected && (
                                <div className="wiz-tp-card__check">
                                    <span className="material-symbols-outlined">check_circle</span>
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>

            {/* ── Error ──────────────────────────────── */}
            {tpError && (
                <div className="wiz-alert wiz-alert--error">
                    <span className="material-symbols-outlined">error</span>
                    {tpError}
                </div>
            )}

            {/* ── Preview Result ─────────────────────── */}
            {tpPreviewResult && !tpError && (
                <div className={`wiz-tp-result ${tpPreviewResult.has_changes ? 'wiz-tp-result--changes' : 'wiz-tp-result--ok'}`}>
                    <div className="wiz-tp-result__header">
                        <span className="material-symbols-outlined">
                            {tpPreviewResult.has_changes ? 'edit_note' : 'check_circle'}
                        </span>
                        <h3>
                            {tpPreviewResult.has_changes
                                ? `${tpPreviewResult.changes_count} binding(s) need updating`
                                : 'All bindings are correct'}
                        </h3>
                    </div>

                    {tpPreviewResult.diffs && tpPreviewResult.diffs.length > 0 && (
                        <div className="wiz-tp-diffs">
                            {tpPreviewResult.diffs.slice(0, 10).map((diff, idx) => (
                                <div key={idx} className={`wiz-tp-diff ${diff.needs_update ? 'wiz-tp-diff--changed' : ''}`}>
                                    <span className="wiz-tp-diff__key">{diff.input_name}</span>
                                    <span className="wiz-tp-diff__arrow">→</span>
                                    <span className="wiz-tp-diff__val">{diff.expected_value}</span>
                                </div>
                            ))}
                        </div>
                    )}

                    {tpPreviewResult.has_changes && (
                        <div className="wiz-tp-result__actions">
                            <button
                                className="wiz-btn wiz-btn--ghost"
                                onClick={() => { setTpPreviewResult(null) }}
                            >
                                Discard
                            </button>
                            <button
                                className="wiz-btn wiz-btn--primary"
                                onClick={handleTpApply}
                                disabled={tpApplyLoading}
                            >
                                <span className="material-symbols-outlined">bolt</span>
                                {tpApplyLoading ? 'Applying...' : `Apply ${tpPreviewResult.changes_count} Changes`}
                            </button>
                        </div>
                    )}
                </div>
            )}

            {/* ── Apply Result ───────────────────────── */}
            {tpApplyResult && (
                <div className="wiz-alert wiz-alert--success">
                    <span className="material-symbols-outlined">check_circle</span>
                    Changes applied successfully to {tpSelectedGame}.
                </div>
            )}
        </div>
    )
}
