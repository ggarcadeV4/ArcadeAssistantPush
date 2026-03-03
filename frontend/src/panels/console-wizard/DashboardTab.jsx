import React from 'react'

/**
 * DashboardTab — Overview tab for Console Wizard V2.
 * Displays: health status, controller detection, emulator table, quick actions.
 * All state is owned by ConsoleWizardPanel and passed as props.
 */
export default function DashboardTab({
    emulators,
    filteredEmulators,
    selectedEmulatorId,
    selectedEmulator,
    selectedHealth,
    selectedPreviewEntry,
    selectedQuirks,
    healthMap,
    healthUnavailable,
    healthMessage,
    health,
    statusFilter,
    setStatusFilter,
    setSelectedEmulatorId,
    setDetailsTab,
    detailsTab,
    attentionEntries,
    panelStatus,
    scanInFlight,
    refreshAll,
    handlePreviewAll,
    previewLoading,
    previewResult,
    previewModalOpen,
    handleRestoreEmulator,
    handleRestoreAll,
    restoringEmulatorId,
    restoringAll,
    settingDefaults,
    lastActions,
    detectedControllers,
    controllerDetectionLoading,
    controllerDetectionError,
    autoConfiguring,
    autoConfigProgress,
    handleDetectControllers,
    handleAutoConfigureAll,
    chuckStatus,
    requiresRestart,
    quirkResults,
    tendenciesData,
    tendenciesProfileId,
    describeHealth,
    showDevErrorDetails,
    formatSystems,
    relativeTime,
}) {
    return (
        <div className="wiz-tab-dashboard" role="tabpanel" aria-label="Dashboard">
            {/* ── Status Cards ───────────────────────────── */}
            <div className="wiz-status-row">
                <div className="wiz-status-card">
                    <span className="wiz-status-card__icon material-symbols-outlined">monitoring</span>
                    <div className="wiz-status-card__body">
                        <span className="wiz-status-card__value">{emulators.length}</span>
                        <span className="wiz-status-card__label">Emulators</span>
                    </div>
                </div>
                <div className="wiz-status-card">
                    <span className="wiz-status-card__icon material-symbols-outlined">sports_esports</span>
                    <div className="wiz-status-card__body">
                        <span className="wiz-status-card__value">{detectedControllers.length}</span>
                        <span className="wiz-status-card__label">Controllers</span>
                    </div>
                </div>
                <div className={`wiz-status-card wiz-status-card--${panelStatus.tone}`}>
                    <span className="wiz-status-card__icon material-symbols-outlined">health_and_safety</span>
                    <div className="wiz-status-card__body">
                        <span className="wiz-status-card__value">{panelStatus.label}</span>
                        <span className="wiz-status-card__label">System Health</span>
                    </div>
                </div>
                <div className="wiz-status-card">
                    <span className="wiz-status-card__icon material-symbols-outlined">warning</span>
                    <div className="wiz-status-card__body">
                        <span className="wiz-status-card__value">{attentionEntries.length}</span>
                        <span className="wiz-status-card__label">Attention</span>
                    </div>
                </div>
            </div>

            {/* ── Controller Detection ───────────────────── */}
            <section className="wiz-section">
                <div className="wiz-section__header">
                    <h2>Controller Auto-Configuration</h2>
                    <p>Plug in your controller and auto-configure all emulators with one click</p>
                </div>

                <div className="wiz-section__actions">
                    <button
                        type="button"
                        className="wiz-btn wiz-btn--ghost"
                        onClick={handleDetectControllers}
                        disabled={controllerDetectionLoading || autoConfiguring}
                    >
                        <span className="material-symbols-outlined">gamepad</span>
                        {controllerDetectionLoading ? 'Detecting...' : 'Detect Controller'}
                    </button>

                    {detectedControllers.length > 0 && (
                        <button
                            type="button"
                            className="wiz-btn wiz-btn--primary"
                            onClick={handleAutoConfigureAll}
                            disabled={autoConfiguring || !emulators.length}
                        >
                            <span className="material-symbols-outlined">bolt</span>
                            {autoConfiguring ? 'Configuring...' : 'Auto-Configure All'}
                        </button>
                    )}
                </div>

                {controllerDetectionError && (
                    <div className="wiz-alert wiz-alert--error">
                        <span className="material-symbols-outlined">error</span>
                        {controllerDetectionError}
                    </div>
                )}

                {detectedControllers.length > 0 && (
                    <div className="wiz-controller-grid">
                        {detectedControllers.map((controller, idx) => (
                            <div key={idx} className="wiz-controller-card">
                                <div className="wiz-controller-card__icon">🎮</div>
                                <div className="wiz-controller-card__info">
                                    <span className="wiz-controller-card__name">{controller.name}</span>
                                    <span className="wiz-controller-card__details">
                                        {controller.manufacturer} • {controller.button_count} buttons
                                        {controller.has_profile && (
                                            <span className="wiz-badge wiz-badge--success">✓ Profile</span>
                                        )}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {autoConfigProgress && (
                    <div className="wiz-progress">
                        <div className="wiz-progress__info">
                            <span>⚙️ {autoConfigProgress.status}</span>
                            <span>{autoConfigProgress.current} / {autoConfigProgress.total}</span>
                        </div>
                        <div className="wiz-progress__bar">
                            <div
                                className="wiz-progress__fill"
                                style={{ width: `${(autoConfigProgress.current / autoConfigProgress.total) * 100}%` }}
                            />
                        </div>
                    </div>
                )}
            </section>

            {/* ── Emulator Table ─────────────────────────── */}
            <section className="wiz-section">
                <div className="wiz-section__header">
                    <h2>Emulator Health</h2>
                    <div className="wiz-section__filter">
                        <button
                            className={`wiz-tab-btn ${statusFilter === 'all' ? 'wiz-tab-btn--active' : ''}`}
                            onClick={() => setStatusFilter('all')}
                        >
                            All ({emulators.length})
                        </button>
                        <button
                            className={`wiz-tab-btn ${statusFilter === 'attention' ? 'wiz-tab-btn--active' : ''}`}
                            onClick={() => setStatusFilter('attention')}
                        >
                            Attention ({attentionEntries.length})
                        </button>
                    </div>
                </div>

                <div className="wiz-emulator-list">
                    {filteredEmulators.map((emu) => {
                        const hEntry = healthMap.get(emu.id)
                        const isSelected = emu.id === selectedEmulatorId
                        return (
                            <div
                                key={emu.id}
                                className={`wiz-emulator-row ${isSelected ? 'wiz-emulator-row--selected' : ''}`}
                                onClick={() => {
                                    setSelectedEmulatorId(emu.id)
                                    setDetailsTab('summary')
                                }}
                                role="button"
                                tabIndex={0}
                            >
                                <div className="wiz-emulator-row__name">
                                    <span className={`wiz-dot wiz-dot--${emu.status || 'unknown'}`} />
                                    {emu.displayName}
                                </div>
                                <div className="wiz-emulator-row__type">{emu.type}</div>
                                <div className="wiz-emulator-row__systems">
                                    {formatSystems(emu.systems)}
                                </div>
                                <div className="wiz-emulator-row__health">
                                    {hEntry ? describeHealth(hEntry) : '—'}
                                </div>
                            </div>
                        )
                    })}
                </div>
            </section>

            {/* ── Quick Actions ──────────────────────────── */}
            <section className="wiz-section wiz-section--actions">
                <button
                    type="button"
                    className="wiz-btn wiz-btn--ghost"
                    onClick={refreshAll}
                    disabled={scanInFlight}
                >
                    <span className="material-symbols-outlined">refresh</span>
                    {scanInFlight ? 'Scanning...' : 'Scan Emulators'}
                </button>
                <button
                    type="button"
                    className="wiz-btn wiz-btn--primary"
                    onClick={handlePreviewAll}
                    disabled={previewLoading}
                >
                    <span className="material-symbols-outlined">preview</span>
                    {previewLoading ? 'Generating...' : 'Generate Configs'}
                </button>
                <button
                    type="button"
                    className="wiz-btn wiz-btn--ghost"
                    onClick={handleRestoreAll}
                    disabled={restoringAll}
                >
                    <span className="material-symbols-outlined">restore</span>
                    {restoringAll ? 'Restoring...' : 'Restore All'}
                </button>
            </section>
        </div>
    )
}
