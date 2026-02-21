/**
 * GameProfilesTab.jsx
 * ─────────────────────────────────────────────────────────────
 * Extracted from LEDBlinkyPanel.jsx (L3145–3732)
 *
 * Renders the "Game Profiles" tab:
 *   • Live LED Preview (ArcadePanelPreview)
 *   • LaunchBox game search + selection
 *   • Selected game → LED profile binding (preview / apply / clear)
 *   • Game Profile Library (search, preview, apply, edit)
 *   • Library profile preview summary
 *
 * All state and callbacks are received via props – no direct
 * ledBlinkyClient calls.  This keeps the component a pure "view"
 * layer that the orchestrator can wire up in one place.
 * ─────────────────────────────────────────────────────────────
 */

import React from 'react'

/* ------------------------------------------------------------------ */
/*  Sub-section: Live LED Preview                                      */
/* ------------------------------------------------------------------ */
const LiveLEDPreview = ({
    ArcadePanelPreview,
    mappingForm,
    currentActiveButtons,
    cabinetPlayerCount,
    wizardState,
    toggleLED,
    handleWizardMapButton
}) => (
    <div style={{
        background: '#000000',
        borderRadius: '12px',
        border: '1px solid #7c3aed',
        overflow: 'hidden'
    }}>
        <div style={{
            padding: '16px 20px',
            borderBottom: '1px solid #7c3aed',
            fontSize: '16px',
            fontWeight: '700',
            color: '#9333ea',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
        }}>
            <span>🎮</span>
            <span>Live LED Preview</span>
        </div>
        <div style={{ padding: '20px' }}>
            <ArcadePanelPreview
                mappingForm={mappingForm}
                activeButtons={currentActiveButtons}
                playerCount={cabinetPlayerCount}
                showLabels={true}
                onButtonClick={(player, button) => {
                    if (wizardState?.isActive) {
                        handleWizardMapButton(`p${player}.button${button}`)
                    } else {
                        toggleLED(player, button)
                    }
                }}
            />
        </div>
    </div>
)

/* ------------------------------------------------------------------ */
/*  Sub-section: LaunchBox Game Search                                  */
/* ------------------------------------------------------------------ */
const LaunchBoxSearch = ({
    gameSearchTerm,
    setGameSearchTerm,
    handleGameSearchKeyDown,
    handleSearchGames,
    isLoadingGames,
    loadGameResults,
    gameResults,
    selectedGame,
    handleSelectGame
}) => (
    <div style={{
        padding: '24px',
        background: '#000000',
        borderRadius: '12px',
        border: '1px solid #7c3aed',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px'
    }}>
        <div style={{
            fontSize: '18px',
            fontWeight: '700',
            color: '#9333ea',
            display: 'flex',
            alignItems: 'center',
            gap: '10px'
        }}>
            <span>[LG]</span>
            <span>LaunchBox Games</span>
        </div>

        {/* Search controls */}
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <input
                type="text"
                value={gameSearchTerm}
                onChange={(e) => setGameSearchTerm(e.target.value)}
                onKeyDown={handleGameSearchKeyDown}
                placeholder="Search by game title or leave blank to list recent cache"
                style={{
                    flex: '1 1 260px',
                    padding: '12px',
                    background: '#0a0a0a',
                    border: '1px solid #4c1d95',
                    borderRadius: '8px',
                    color: '#ffffff',
                    fontSize: '13px'
                }}
            />
            <button
                onClick={handleSearchGames}
                disabled={isLoadingGames}
                style={{
                    padding: '12px 18px',
                    background: isLoadingGames ? '#312e81' : '#9333ea',
                    border: 'none',
                    borderRadius: '8px',
                    color: '#ffffff',
                    fontWeight: '600',
                    cursor: isLoadingGames ? 'not-allowed' : 'pointer',
                    opacity: isLoadingGames ? 0.6 : 1
                }}
            >
                {isLoadingGames ? 'Searching…' : 'Search'}
            </button>
            <button
                onClick={() => loadGameResults('')}
                disabled={isLoadingGames}
                style={{
                    padding: '12px 18px',
                    background: '#111827',
                    border: '1px solid #4b5563',
                    borderRadius: '8px',
                    color: '#e5e7eb',
                    fontWeight: '600',
                    cursor: isLoadingGames ? 'not-allowed' : 'pointer',
                    opacity: isLoadingGames ? 0.6 : 1
                }}
            >
                Reset
            </button>
        </div>

        {/* Results list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '260px', overflowY: 'auto' }}>
            {isLoadingGames ? (
                <div style={{ color: '#9ca3af', fontSize: '13px' }}>Loading LaunchBox games…</div>
            ) : gameResults.length > 0 ? (
                gameResults.map(game => {
                    const isActive = selectedGame?.id === game.id
                    const assignedName = game.assigned_profile?.profile_name
                    return (
                        <div
                            key={game.id}
                            style={{
                                border: `1px solid ${isActive ? '#9333ea' : '#1f2937'}`,
                                borderRadius: '10px',
                                padding: '14px',
                                background: '#050505',
                                display: 'flex',
                                justifyContent: 'space-between',
                                gap: '12px',
                                flexWrap: 'wrap'
                            }}
                        >
                            <div>
                                <div style={{ fontSize: '15px', fontWeight: '600', color: '#f3f4f6' }}>{game.title || 'Unknown Game'}</div>
                                <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                                    {game.platform || 'Unknown Platform'}
                                    {' • '}
                                    {assignedName ? `LED Profile: ${assignedName}` : 'No LED profile assigned'}
                                </div>
                            </div>
                            <button
                                onClick={() => handleSelectGame(game)}
                                disabled={isActive}
                                style={{
                                    padding: '10px 16px',
                                    borderRadius: '8px',
                                    border: '1px solid #7c3aed',
                                    background: isActive ? '#1f2937' : '#000000',
                                    color: isActive ? '#6b7280' : '#d1d5db',
                                    fontSize: '12px',
                                    fontWeight: '600',
                                    cursor: isActive ? 'default' : 'pointer'
                                }}
                            >
                                {isActive ? 'Selected' : 'Select'}
                            </button>
                        </div>
                    )
                })
            ) : (
                <div style={{ color: '#9ca3af', fontSize: '13px' }}>
                    {gameSearchTerm.trim() ? 'No LaunchBox games match that search.' : 'No LaunchBox games loaded yet.'}
                </div>
            )}
        </div>
    </div>
)

/* ------------------------------------------------------------------ */
/*  Sub-section: Selected Game Binding                                 */
/* ------------------------------------------------------------------ */
const SelectedGameBinding = ({
    selectedGame,
    selectedGameBinding,
    selectedGameProfileName,
    setSelectedGameProfileName,
    isLoadingBinding,
    availableProfiles,
    canPreviewBinding,
    canApplyBinding,
    canClearBinding,
    isPreviewingBinding,
    isApplyingBinding,
    isClearingBinding,
    handlePreviewGameProfile,
    handleApplyGameProfile,
    handleClearGameProfile,
    bindingPreview
}) => {
    if (!selectedGame) return null

    return (
        <div style={{
            padding: '24px',
            background: '#000000',
            borderRadius: '12px',
            border: '1px solid #7c3aed',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px'
        }}>
            <div style={{
                fontSize: '18px',
                fontWeight: '700',
                color: '#9333ea',
                display: 'flex',
                alignItems: 'center',
                gap: '10px'
            }}>
                <span>[SG]</span>
                <span>Selected Game</span>
            </div>
            <div style={{ fontSize: '14px', color: '#f3f4f6' }}>{selectedGame.title}</div>
            <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                Platform: {selectedGame.platform || 'Unknown'} • Current profile: {selectedGameBinding?.profile_name || 'None'}
            </div>

            {/* Profile selector */}
            <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Assign LED Profile</label>
                <select
                    value={selectedGameProfileName}
                    onChange={(e) => setSelectedGameProfileName(e.target.value)}
                    disabled={isLoadingBinding}
                    style={{
                        width: '100%',
                        padding: '12px',
                        background: '#0a0a0a',
                        border: '1px solid #4b5563',
                        borderRadius: '8px',
                        color: '#ffffff',
                        fontSize: '13px'
                    }}
                >
                    <option value="">-- Select a Profile --</option>
                    {availableProfiles.map(profile => (
                        <option key={profile.value} value={profile.value}>
                            {profile.label}
                        </option>
                    ))}
                </select>
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                <button
                    onClick={handlePreviewGameProfile}
                    disabled={!canPreviewBinding}
                    style={{
                        flex: '1 1 160px',
                        padding: '12px',
                        borderRadius: '8px',
                        border: '1px solid #10b981',
                        background: canPreviewBinding ? '#000000' : '#1b1b1b',
                        color: canPreviewBinding ? '#10b981' : '#6b7280',
                        fontSize: '13px',
                        fontWeight: '600',
                        cursor: canPreviewBinding ? 'pointer' : 'not-allowed'
                    }}
                >
                    {isPreviewingBinding ? 'Previewing…' : 'Preview Binding'}
                </button>
                <button
                    onClick={handleApplyGameProfile}
                    disabled={!canApplyBinding}
                    style={{
                        flex: '1 1 160px',
                        padding: '12px',
                        borderRadius: '8px',
                        border: 'none',
                        background: canApplyBinding ? 'linear-gradient(135deg, #9333ea, #7c3aed)' : '#2d1b3b',
                        color: '#ffffff',
                        fontSize: '13px',
                        fontWeight: '600',
                        cursor: canApplyBinding ? 'pointer' : 'not-allowed'
                    }}
                >
                    {isApplyingBinding ? 'Applying…' : 'Apply to Game'}
                </button>
                <button
                    onClick={handleClearGameProfile}
                    disabled={!canClearBinding}
                    style={{
                        flex: '1 1 160px',
                        padding: '12px',
                        borderRadius: '8px',
                        border: '1px solid #ef4444',
                        background: canClearBinding ? '#1b0b0b' : '#1f1f1f',
                        color: canClearBinding ? '#ef4444' : '#6b7280',
                        fontSize: '13px',
                        fontWeight: '600',
                        cursor: canClearBinding ? 'pointer' : 'not-allowed'
                    }}
                >
                    {isClearingBinding ? 'Clearing…' : 'Clear Binding'}
                </button>
            </div>

            {/* Binding preview */}
            {bindingPreview && (
                <div style={{
                    marginTop: '12px',
                    padding: '16px',
                    background: '#050505',
                    borderRadius: '8px',
                    border: '1px solid #1f2937'
                }}>
                    <div style={{ fontSize: '13px', color: '#d1d5db', marginBottom: '6px' }}>Binding Preview</div>
                    <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '8px' }}>
                        Target file: <code style={{ color: '#a7f3d0' }}>{bindingPreview.target_file}</code>
                    </div>
                    <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '8px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        <span>Scope: {bindingPreview.scope}</span>
                        <span>Total channels: {bindingPreview.total_channels}</span>
                        <span>Missing buttons: {bindingPreview.missing_buttons?.length ? bindingPreview.missing_buttons.join(', ') : 'None'}</span>
                    </div>
                    <div style={{
                        marginBottom: '10px',
                        padding: '10px',
                        background: '#0a0a0a',
                        borderRadius: '6px',
                        border: '1px solid #1f2937'
                    }}>
                        <div style={{ fontSize: '12px', color: '#e5e7eb', marginBottom: '4px' }}>Diff</div>
                        <pre style={{ margin: 0, maxHeight: '120px', overflow: 'auto', fontSize: '12px', color: '#9ca3af' }}>{bindingPreview.diff}</pre>
                    </div>
                    <div style={{
                        padding: '10px',
                        background: '#0a0a0a',
                        borderRadius: '6px',
                        border: '1px solid #1f2937'
                    }}>
                        <div style={{ fontSize: '12px', color: '#e5e7eb', marginBottom: '4px' }}>Resolved Buttons</div>
                        {(bindingPreview.resolved_buttons || []).slice(0, 8).map((button, index) => {
                            const channels = button.channels || []
                            const channelSummary = channels.length
                                ? channels.map(channel => `${channel.device_id}#${channel.channel_index}`).join(', ')
                                : 'No hardware channel resolved'
                            return (
                                <div key={`${button.logical_button}-${index}`} style={{ fontSize: '12px', color: '#9ca3af' }}>
                                    {button.logical_button} → {channelSummary}
                                </div>
                            )
                        })}
                        {bindingPreview.resolved_buttons && bindingPreview.resolved_buttons.length > 8 && (
                            <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
                                +{bindingPreview.resolved_buttons.length - 8} more channels
                            </div>
                        )}
                    </div>
                </div>
            )}

            <div style={{ fontSize: '12px', color: '#6b7280' }}>
                Assignments are stored under <code>configs/ledblinky/game_profiles.json</code> so LaunchBox sessions stay in sync.
            </div>
        </div>
    )
}

/* ------------------------------------------------------------------ */
/*  Sub-section: Profile Library                                       */
/* ------------------------------------------------------------------ */
const ProfileLibrary = ({
    profileSearchTerm,
    setProfileSearchTerm,
    filteredProfiles,
    isLoadingProfiles,
    refreshProfiles,
    selectedProfile,
    canApplyLibraryProfile,
    previewProfileFromLibrary,
    applyProfileFromLibrary,
    editProfileInDesigner
}) => (
    <div style={{
        padding: '24px',
        background: '#000000',
        borderRadius: '12px',
        border: '1px solid #7c3aed',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px'
    }}>
        <div style={{
            fontSize: '18px',
            fontWeight: '700',
            color: '#9333ea',
            display: 'flex',
            alignItems: 'center',
            gap: '10px'
        }}>
            <span>[GP]</span>
            <span>Game Profile Library</span>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center' }}>
            <input
                type="text"
                value={profileSearchTerm}
                onChange={(e) => setProfileSearchTerm(e.target.value)}
                placeholder="Search by game, filename, or scope"
                style={{
                    flex: '1 1 300px',
                    minWidth: '200px',
                    padding: '12px',
                    background: '#0a0a0a',
                    border: '1px solid #4c1d95',
                    borderRadius: '8px',
                    color: '#ffffff',
                    fontSize: '13px'
                }}
            />
            <button
                onClick={refreshProfiles}
                disabled={isLoadingProfiles}
                style={{
                    padding: '12px 18px',
                    background: isLoadingProfiles ? '#312e81' : '#9333ea',
                    border: 'none',
                    borderRadius: '8px',
                    color: '#ffffff',
                    fontWeight: '600',
                    cursor: isLoadingProfiles ? 'not-allowed' : 'pointer',
                    opacity: isLoadingProfiles ? 0.6 : 1
                }}
            >
                {isLoadingProfiles ? 'Refreshing…' : 'Refresh'}
            </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {filteredProfiles.length > 0 ? (
                filteredProfiles.map(profile => {
                    const meta = profile.metadata || {}
                    const isActive = selectedProfile === profile.value
                    const summaryParts = [
                        meta.scope ? `Scope: ${meta.scope}` : null,
                        Array.isArray(meta.mapping_keys) ? `${meta.mapping_keys.length} keys` : null,
                        meta.filename ? `File: ${meta.filename}` : null
                    ].filter(Boolean)
                    const canApplyThisProfile = isActive && canApplyLibraryProfile
                    return (
                        <div
                            key={profile.value}
                            style={{
                                border: `1px solid ${isActive ? '#10b981' : '#4b5563'}`,
                                borderRadius: '10px',
                                padding: '16px',
                                background: '#050505'
                            }}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
                                <div>
                                    <div style={{ fontSize: '15px', fontWeight: '600', color: '#f3f4f6', marginBottom: '4px' }}>
                                        {meta.game || meta.profile_name || profile.label}
                                    </div>
                                    <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                                        {summaryParts.length > 0 ? summaryParts.join(' • ') : 'Unscoped profile'}
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                    <button
                                        onClick={() => previewProfileFromLibrary(profile.value)}
                                        style={{
                                            padding: '10px 14px',
                                            borderRadius: '6px',
                                            border: '1px solid #9333ea',
                                            background: '#000000',
                                            color: '#9333ea',
                                            fontSize: '12px',
                                            fontWeight: '600',
                                            cursor: 'pointer'
                                        }}
                                    >
                                        Preview
                                    </button>
                                    <button
                                        onClick={() => applyProfileFromLibrary(profile.value)}
                                        disabled={!canApplyThisProfile}
                                        style={{
                                            padding: '10px 14px',
                                            borderRadius: '6px',
                                            border: 'none',
                                            background: canApplyThisProfile ? '#10b981' : '#374151',
                                            color: canApplyThisProfile ? '#051b16' : '#9ca3af',
                                            fontSize: '12px',
                                            fontWeight: '600',
                                            cursor: canApplyThisProfile ? 'pointer' : 'not-allowed'
                                        }}
                                    >
                                        Apply
                                    </button>
                                    <button
                                        onClick={() => editProfileInDesigner(profile.value)}
                                        style={{
                                            padding: '10px 14px',
                                            borderRadius: '6px',
                                            border: '1px solid #4b5563',
                                            background: '#111111',
                                            color: '#d1d5db',
                                            fontSize: '12px',
                                            fontWeight: '600',
                                            cursor: 'pointer'
                                        }}
                                    >
                                        Edit in Designer
                                    </button>
                                </div>
                            </div>
                        </div>
                    )
                })
            ) : (
                <div style={{ color: '#9ca3af', fontSize: '13px' }}>
                    {profileSearchTerm.trim()
                        ? 'No profiles match your search.'
                        : 'No LED profiles found in configs/ledblinky/profiles.'}
                </div>
            )}
        </div>

        <div style={{ fontSize: '12px', color: '#6b7280' }}>
            Preview resolves Chuck's logical buttons to LED channels. Apply remains disabled until the latest preview matches the selected profile.
        </div>
    </div>
)

/* ------------------------------------------------------------------ */
/*  Sub-section: Profile Preview Summary                               */
/* ------------------------------------------------------------------ */
const ProfilePreviewSummary = ({ libraryPreviewReady, profilePreview, selectedProfileDisplayName }) => {
    if (!libraryPreviewReady || !profilePreview) return null

    return (
        <div style={{
            padding: '24px',
            background: '#000000',
            borderRadius: '12px',
            border: '1px solid #10b981'
        }}>
            <div style={{
                fontSize: '16px',
                fontWeight: '700',
                color: '#10b981',
                marginBottom: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px'
            }}>
                <span>[PV]</span>
                <span>Preview Summary: {selectedProfileDisplayName}</span>
            </div>
            <div style={{ fontSize: '13px', color: '#d1d5db', marginBottom: '8px' }}>
                Target file: <code style={{ color: '#a7f3d0' }}>{profilePreview.target_file}</code>
            </div>
            <div style={{ fontSize: '12px', color: '#9ca3af', display: 'flex', flexWrap: 'wrap', gap: '12px', marginBottom: '12px' }}>
                <span>Scope: {profilePreview.scope}</span>
                {profilePreview.game && <span>Game: {profilePreview.game}</span>}
                <span>Total channels: {profilePreview.total_channels}</span>
                <span>Missing buttons: {profilePreview.missing_buttons.length ? profilePreview.missing_buttons.join(', ') : 'None'}</span>
            </div>
            <div style={{
                marginBottom: '12px',
                padding: '12px',
                background: '#050505',
                borderRadius: '8px',
                border: '1px solid #1f2937'
            }}>
                <div style={{ fontSize: '12px', color: '#e5e7eb', marginBottom: '6px' }}>Diff</div>
                <pre style={{
                    margin: 0,
                    maxHeight: '140px',
                    overflow: 'auto',
                    fontSize: '12px',
                    color: '#9ca3af'
                }}>
                    {profilePreview.diff}
                </pre>
            </div>
            <div style={{
                padding: '12px',
                background: '#050505',
                borderRadius: '8px',
                border: '1px solid #1f2937'
            }}>
                <div style={{ fontSize: '12px', color: '#e5e7eb', marginBottom: '8px' }}>Resolved Buttons</div>
                {(profilePreview.resolved_buttons || []).slice(0, 8).map((button, index) => {
                    const channels = button.channels || []
                    const channelSummary = channels.length
                        ? channels.map(channel => `${channel.device_id}#${channel.channel_index}`).join(', ')
                        : 'No hardware channel resolved'
                    return (
                        <div key={`${button.logical_button}-${index}`} style={{ fontSize: '12px', color: '#9ca3af' }}>
                            {button.logical_button} → {channelSummary}
                        </div>
                    )
                })}
                {profilePreview.resolved_buttons && profilePreview.resolved_buttons.length > 8 && (
                    <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
                        +{profilePreview.resolved_buttons.length - 8} more channels
                    </div>
                )}
            </div>
        </div>
    )
}

/* ------------------------------------------------------------------ */
/*  Main export: GameProfilesTab                                       */
/* ------------------------------------------------------------------ */
const GameProfilesTab = (props) => {
    const {
        // ArcadePanelPreview component reference
        ArcadePanelPreview,
        // Preview state
        mappingForm,
        currentActiveButtons,
        cabinetPlayerCount,
        wizardState,
        toggleLED,
        handleWizardMapButton,
        // Game search
        gameSearchTerm,
        setGameSearchTerm,
        handleGameSearchKeyDown,
        handleSearchGames,
        isLoadingGames,
        loadGameResults,
        gameResults,
        selectedGame,
        handleSelectGame,
        // Game binding
        selectedGameBinding,
        selectedGameProfileName,
        setSelectedGameProfileName,
        isLoadingBinding,
        availableProfiles,
        canPreviewBinding,
        canApplyBinding,
        canClearBinding,
        isPreviewingBinding,
        isApplyingBinding,
        isClearingBinding,
        handlePreviewGameProfile,
        handleApplyGameProfile,
        handleClearGameProfile,
        bindingPreview,
        // Profile library
        profileSearchTerm,
        setProfileSearchTerm,
        filteredProfiles,
        isLoadingProfiles,
        refreshProfiles,
        selectedProfile,
        canApplyLibraryProfile,
        previewProfileFromLibrary,
        applyProfileFromLibrary,
        editProfileInDesigner,
        // Profile preview summary
        libraryPreviewReady,
        profilePreview,
        selectedProfileDisplayName
    } = props

    return (
        <div style={{ padding: '24px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <LiveLEDPreview
                ArcadePanelPreview={ArcadePanelPreview}
                mappingForm={mappingForm}
                currentActiveButtons={currentActiveButtons}
                cabinetPlayerCount={cabinetPlayerCount}
                wizardState={wizardState}
                toggleLED={toggleLED}
                handleWizardMapButton={handleWizardMapButton}
            />

            <LaunchBoxSearch
                gameSearchTerm={gameSearchTerm}
                setGameSearchTerm={setGameSearchTerm}
                handleGameSearchKeyDown={handleGameSearchKeyDown}
                handleSearchGames={handleSearchGames}
                isLoadingGames={isLoadingGames}
                loadGameResults={loadGameResults}
                gameResults={gameResults}
                selectedGame={selectedGame}
                handleSelectGame={handleSelectGame}
            />

            <SelectedGameBinding
                selectedGame={selectedGame}
                selectedGameBinding={selectedGameBinding}
                selectedGameProfileName={selectedGameProfileName}
                setSelectedGameProfileName={setSelectedGameProfileName}
                isLoadingBinding={isLoadingBinding}
                availableProfiles={availableProfiles}
                canPreviewBinding={canPreviewBinding}
                canApplyBinding={canApplyBinding}
                canClearBinding={canClearBinding}
                isPreviewingBinding={isPreviewingBinding}
                isApplyingBinding={isApplyingBinding}
                isClearingBinding={isClearingBinding}
                handlePreviewGameProfile={handlePreviewGameProfile}
                handleApplyGameProfile={handleApplyGameProfile}
                handleClearGameProfile={handleClearGameProfile}
                bindingPreview={bindingPreview}
            />

            <ProfileLibrary
                profileSearchTerm={profileSearchTerm}
                setProfileSearchTerm={setProfileSearchTerm}
                filteredProfiles={filteredProfiles}
                isLoadingProfiles={isLoadingProfiles}
                refreshProfiles={refreshProfiles}
                selectedProfile={selectedProfile}
                canApplyLibraryProfile={canApplyLibraryProfile}
                previewProfileFromLibrary={previewProfileFromLibrary}
                applyProfileFromLibrary={applyProfileFromLibrary}
                editProfileInDesigner={editProfileInDesigner}
            />

            <ProfilePreviewSummary
                libraryPreviewReady={libraryPreviewReady}
                profilePreview={profilePreview}
                selectedProfileDisplayName={selectedProfileDisplayName}
            />
        </div>
    )
}

export default GameProfilesTab
