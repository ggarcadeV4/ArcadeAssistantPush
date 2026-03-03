import React, { useState, useMemo } from 'react'

/**
 * VisualDiffTab — Side-by-side config diff viewer.
 * Shows local config vs. proposed changes with red/green diff highlighting.
 * Reuses previewResult state from the parent.
 */
export default function VisualDiffTab({
    previewResult,
    previewLoading,
    emulatorMap,
    handlePreviewAll,
    applyInFlight,
}) {
    const [expandedId, setExpandedId] = useState(null)
    const [viewMode, setViewMode] = useState('split') // 'split' | 'unified'

    const diffEntries = useMemo(() => {
        if (!previewResult?.emulators) return []
        return previewResult.emulators.filter(entry =>
            entry.files?.some(f => f.additions > 0 || f.removals > 0)
        )
    }, [previewResult])

    const totalStats = useMemo(() => {
        let additions = 0, removals = 0
        diffEntries.forEach(entry => {
            entry.files?.forEach(f => {
                additions += f.additions || 0
                removals += f.removals || 0
            })
        })
        return { additions, removals }
    }, [diffEntries])

    if (!previewResult) {
        return (
            <div className="wiz-tab-diff" role="tabpanel" aria-label="Visual Diff">
                <div className="wiz-diff-empty">
                    <span className="material-symbols-outlined" style={{ fontSize: 48, color: 'rgba(34,197,94,0.3)' }}>
                        difference
                    </span>
                    <h3>No Config Diff Available</h3>
                    <p>Run "Generate Configs" from the Dashboard tab to preview config changes before applying.</p>
                    <button
                        className="wiz-btn wiz-btn--primary"
                        onClick={handlePreviewAll}
                        disabled={previewLoading}
                    >
                        <span className="material-symbols-outlined">preview</span>
                        {previewLoading ? 'Generating...' : 'Generate Config Preview'}
                    </button>
                </div>
            </div>
        )
    }

    return (
        <div className="wiz-tab-diff" role="tabpanel" aria-label="Visual Diff">
            {/* ── Header ─────────────────────────────── */}
            <div className="wiz-diff-header">
                <div className="wiz-diff-header__title">
                    <span className="material-symbols-outlined" style={{ color: '#22C55E' }}>difference</span>
                    <h2>Visual Diff Viewer</h2>
                    <span className="wiz-badge wiz-badge--info">{diffEntries.length} file(s)</span>
                </div>
                <div className="wiz-diff-header__stats">
                    <span className="wiz-diff-stat wiz-diff-stat--add">+ {totalStats.additions} Additions</span>
                    <span className="wiz-diff-stat wiz-diff-stat--rem">- {totalStats.removals} Removals</span>
                </div>
                <div className="wiz-diff-header__actions">
                    <div className="wiz-toggle-group">
                        <button
                            className={`wiz-toggle ${viewMode === 'split' ? 'wiz-toggle--active' : ''}`}
                            onClick={() => setViewMode('split')}
                        >
                            Split
                        </button>
                        <button
                            className={`wiz-toggle ${viewMode === 'unified' ? 'wiz-toggle--active' : ''}`}
                            onClick={() => setViewMode('unified')}
                        >
                            Unified
                        </button>
                    </div>
                </div>
            </div>

            {/* ── Diff Entries ───────────────────────── */}
            <div className="wiz-diff-list">
                {diffEntries.map(entry => {
                    const emu = emulatorMap.get(entry.id)
                    const isExpanded = expandedId === entry.id
                    return (
                        <div key={entry.id} className={`wiz-diff-entry ${isExpanded ? 'wiz-diff-entry--expanded' : ''}`}>
                            <button
                                className="wiz-diff-entry__header"
                                onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                            >
                                <span className="material-symbols-outlined">
                                    {isExpanded ? 'expand_more' : 'chevron_right'}
                                </span>
                                <span className="wiz-diff-entry__name">
                                    {emu?.displayName || entry.displayName || entry.id}
                                </span>
                                <span className="wiz-diff-entry__badge">
                                    {entry.files?.length || 0} file(s)
                                </span>
                            </button>

                            {isExpanded && entry.files?.map((file, idx) => (
                                <div key={idx} className="wiz-diff-file">
                                    <div className="wiz-diff-file__path">
                                        <span className="material-symbols-outlined">description</span>
                                        {file.path || file.displayName || `File ${idx + 1}`}
                                        <span className="wiz-diff-stat wiz-diff-stat--add">+{file.additions || 0}</span>
                                        <span className="wiz-diff-stat wiz-diff-stat--rem">-{file.removals || 0}</span>
                                    </div>

                                    {viewMode === 'split' ? (
                                        <div className="wiz-diff-split">
                                            <div className="wiz-diff-pane wiz-diff-pane--local">
                                                <div className="wiz-diff-pane__label">LOCAL CONFIGURATION</div>
                                                <pre className="wiz-diff-code">
                                                    {file.localContent || file.before || '(empty)'}
                                                </pre>
                                            </div>
                                            <div className="wiz-diff-pane wiz-diff-pane--remote">
                                                <div className="wiz-diff-pane__label">REMOTE UPDATE</div>
                                                <pre className="wiz-diff-code">
                                                    {file.remoteContent || file.after || '(empty)'}
                                                </pre>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="wiz-diff-unified">
                                            <pre className="wiz-diff-code">
                                                {(file.unifiedDiff || file.diff || '(no diff available)')}
                                            </pre>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )
                })}
            </div>

            {/* ── Footer Actions ─────────────────────── */}
            <div className="wiz-diff-footer">
                <button
                    className="wiz-btn wiz-btn--ghost"
                    onClick={handlePreviewAll}
                    disabled={previewLoading}
                >
                    <span className="material-symbols-outlined">refresh</span>
                    Refresh
                </button>
                {totalStats.additions + totalStats.removals > 0 && (
                    <button
                        className="wiz-btn wiz-btn--primary"
                        onClick={handlePreviewAll}
                        disabled={applyInFlight}
                    >
                        <span className="material-symbols-outlined">bolt</span>
                        {applyInFlight ? 'Applying...' : 'Apply Changes'}
                    </button>
                )}
            </div>
        </div>
    )
}
