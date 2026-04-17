// @panel: ContentDisplayManager
// @role: Content path management, RetroFE collections, and marquee configuration
// @owner: LoRa (Content & Display subsystem)
// @linked: backend/routers/content_manager.py
// @features: path-management, retrofe-collections, marquee-configuration

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import './contentDisplayManager.css';
import { getGatewayUrl } from '../../services/gateway'
import { buildStandardHeaders } from '../../utils/identity'

const CDM_PANEL = 'content-display-manager'

const GATEWAY = (typeof window !== 'undefined' && window.location && window.location.port === '5173')
    ? getGatewayUrl()
    : '';

const ContentDisplayManager = () => {
    const navigate = useNavigate();
    const isDev = import.meta?.env?.DEV ?? false;

    // Core paths state
    const [corePaths, setCorePaths] = useState({
        launchboxRoot: '',
        retrofeRoot: '',
        romRoot: '',
    });

    // Path validation status
    const [pathStatus, setPathStatus] = useState({
        launchboxRoot: 'unknown',
        retrofeRoot: 'unknown',
        romRoot: 'unknown',
    });

    // Local state for dynamic system paths
    const [systemPaths, setSystemPaths] = useState([
        { id: 1, system: 'Arcade / MAME', path: '' },
        { id: 2, system: 'SNES', path: '' },
    ]);

    // Artwork paths state
    const [artworkPaths, setArtworkPaths] = useState({
        splashScreens: '',
        marqueeImages: '',
        marqueeVideos: '',
        bezels: '',
        manuals: '',
    });

    // State for marquee configuration
    const [marqueeConfig, setMarqueeConfig] = useState({
        target_monitor_index: 1,
        safeArea: { x: 0, y: 0, width: 1920, height: 360 },
        images_root: '',
        videos_root: '',
        use_video_if_available: true,
        fallback_mode: 'system',
    });

    // Pegasus platforms state (replaces RetroFE collections)
    const [pegasusStatus, setPegasusStatus] = useState({
        installed: false,
        platform_count: 0,
        total_games: 0,
        platforms: [],
    });
    const [platformFilter, setPlatformFilter] = useState('');

    // Available displays for marquee
    const [availableDisplays, setAvailableDisplays] = useState([
        'Display 1 – Main',
        'Display 2 – Marquee',
        'Display 3 – Auxiliary',
    ]);

    // Loading/saving state
    const [isLoading, setIsLoading] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [toast, setToast] = useState('');

    // Preview modal state
    const [previewModal, setPreviewModal] = useState({ open: false, system: '', content: '' });

    // Generation progress state
    const [isGenerating, setIsGenerating] = useState(false);
    const [generatingSystem, setGeneratingSystem] = useState('');

    // Toast timer ref to prevent race conditions
    const toastTimerRef = useRef(null);

    // Show toast message (clears previous timer to prevent stuck toasts)
    const showToast = useCallback((msg) => {
        if (toastTimerRef.current) {
            clearTimeout(toastTimerRef.current);
        }
        setToast(msg);
        toastTimerRef.current = setTimeout(() => setToast(''), 3000);
    }, []);

    // Load configuration on mount
    useEffect(() => {
        const loadConfig = async () => {
            setIsLoading(true);
            const cdmGetHeaders = buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' });
            try {
                const [pathsRes, marqueeRes, pegasusRes] = await Promise.all([
                    fetch(`${GATEWAY}/api/content/paths`, { headers: cdmGetHeaders }).catch(() => null),
                    fetch(`${GATEWAY}/api/local/marquee/config`, { headers: cdmGetHeaders }).catch(() => null),
                    fetch(`${GATEWAY}/api/pegasus/status`, { headers: cdmGetHeaders }).catch(() => null),
                ]);

                if (pathsRes?.ok) {
                    const data = await pathsRes.json();
                    if (data.core) setCorePaths(data.core);
                    if (data.systems) setSystemPaths(data.systems);
                    if (data.artwork) setArtworkPaths(data.artwork);
                    if (data.status) setPathStatus(data.status);
                }

                if (marqueeRes?.ok) {
                    const data = await marqueeRes.json();
                    setMarqueeConfig(prev => ({
                        ...prev,
                        target_monitor_index: data.target_monitor_index ?? data.display?.target_monitor_index ?? prev.target_monitor_index,
                        safeArea: data.safe_area ?? data.display?.safe_area ?? prev.safeArea,
                        images_root: data.images_root ?? data.paths?.images_root ?? prev.images_root,
                        videos_root: data.videos_root ?? data.paths?.videos_root ?? prev.videos_root,
                        use_video_if_available: data.use_video_if_available ?? data.behavior?.use_video_if_available ?? prev.use_video_if_available,
                        fallback_mode: data.fallback_mode ?? data.behavior?.fallback_mode ?? prev.fallback_mode,
                    }));
                    if (data.displays) setAvailableDisplays(data.displays);
                }

                if (pegasusRes?.ok) {
                    const data = await pegasusRes.json();
                    setPegasusStatus(data);
                }
            } catch (err) {
                console.error('[ContentDisplayManager] Failed to load config:', err);
            } finally {
                setIsLoading(false);
            }
        };

        loadConfig();
    }, []);

    // Handler to add new system path
    const addSystemPath = () => {
        const newId = Math.max(...systemPaths.map(s => s.id), 0) + 1;
        setSystemPaths([...systemPaths, { id: newId, system: '', path: '' }]);
    };

    // Handler to update system path
    const updateSystemPath = (id, field, value) => {
        setSystemPaths(systemPaths.map(sp =>
            sp.id === id ? { ...sp, [field]: value } : sp
        ));
    };

    // Handler to remove system path
    const removeSystemPath = (id) => {
        setSystemPaths(systemPaths.filter(sp => sp.id !== id));
    };

    // Validate all paths
    const handleValidatePaths = async () => {
        showToast('Validating paths...');
        try {
            const res = await fetch(`${GATEWAY}/api/content/paths/validate`, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: CDM_PANEL,
                    scope: 'config',
                    extraHeaders: { 'Content-Type': 'application/json' },
                }),
                body: JSON.stringify({
                    core: corePaths,
                    systems: systemPaths,
                    artwork: artworkPaths,
                }),
            });

            if (res.ok) {
                const data = await res.json();
                setPathStatus(data.status || {});
                showToast(data.valid ? '✅ All paths valid!' : '⚠️ Some paths invalid');
            } else {
                showToast('❌ Validation failed');
            }
        } catch (err) {
            console.error('[ContentDisplayManager] Validate failed:', err);
            showToast('❌ Validation error');
        }
    };

    // Dev-only hook to inspect registries
    const handleShowRegistry = async () => {
        try {
            const cdmGetHeaders = buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' });
            const [aaRes, rfeRes] = await Promise.all([
                fetch(`${GATEWAY}/api/local/registry/aa`, { headers: cdmGetHeaders }).catch(() => null),
                fetch(`${GATEWAY}/api/local/registry/retrofe`, { headers: cdmGetHeaders }).catch(() => null),
            ]);
            const aaData = aaRes && aaRes.ok ? await aaRes.json() : null;
            const rfeData = rfeRes && rfeRes.ok ? await rfeRes.json() : null;
            console.log('[CDM] AA Registry', aaData);
            console.log('[CDM] RetroFE Registry', rfeData);
            showToast('Registry logged to console');
        } catch (err) {
            console.error('[ContentDisplayManager] Registry fetch failed', err);
            showToast('Registry fetch failed');
        }
    };

    // Sync Pegasus metadata for specific platform
    const handleSyncPlatform = async (platformId) => {
        setIsGenerating(true);
        setGeneratingSystem(platformId);
        showToast(`Syncing ${platformId}...`);
        try {
            const res = await fetch(`${GATEWAY}/api/pegasus/sync/${encodeURIComponent(platformId)}`, {
                method: 'POST',
                headers: buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' }),
            });

            if (res.ok) {
                const data = await res.json();
                showToast(`✅ ${data.message}`);
                // Refresh status
                const statusRes = await fetch(`${GATEWAY}/api/pegasus/status`, {
                    headers: buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' }),
                });
                if (statusRes.ok) {
                    setPegasusStatus(await statusRes.json());
                }
            } else {
                const err = await res.json().catch(() => ({}));
                showToast(`❌ Sync failed: ${err.detail || 'Unknown error'}`);
            }
        } catch (err) {
            console.error('[ContentDisplayManager] Sync failed:', err);
            showToast('❌ Sync error: ' + err.message);
        } finally {
            setIsGenerating(false);
            setGeneratingSystem('');
        }
    };

    // Sync all Pegasus platforms
    const handleSyncAllPlatforms = async () => {
        setIsGenerating(true);
        setGeneratingSystem('all');
        showToast('Syncing all platforms... This may take a minute.');
        try {
            const res = await fetch(`${GATEWAY}/api/pegasus/sync-all`, {
                method: 'POST',
                headers: buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' }),
            });

            if (res.ok) {
                const data = await res.json();
                showToast(`✅ ${data.message}`);
                // Refresh status
                const statusRes = await fetch(`${GATEWAY}/api/pegasus/status`, {
                    headers: buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' }),
                });
                if (statusRes.ok) {
                    setPegasusStatus(await statusRes.json());
                }
            } else {
                const err = await res.json().catch(() => ({}));
                showToast(`❌ Sync failed: ${err.detail || 'Unknown error'}`);
            }
        } catch (err) {
            console.error('[ContentDisplayManager] Sync all failed:', err);
            showToast('❌ Sync error: ' + err.message);
        } finally {
            setIsGenerating(false);
            setGeneratingSystem('');
        }
    };

    // Refresh Pegasus status
    const handleRefreshPegasusStatus = async () => {
        showToast('Refreshing Pegasus status...');
        try {
            const res = await fetch(`${GATEWAY}/api/pegasus/status`, {
                headers: buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' }),
            });
            if (res.ok) {
                setPegasusStatus(await res.json());
                showToast('✅ Status refreshed');
            } else {
                showToast('❌ Failed to refresh status');
            }
        } catch (err) {
            showToast('❌ Refresh error');
        }
    };

    // Get sync status badge class
    const getSyncStatusClass = (status) => {
        switch (status) {
            case 'synced': return 'cdm-status-badge cdm-status-valid';
            case 'outdated': return 'cdm-status-badge cdm-status-warning';
            case 'missing': return 'cdm-status-badge cdm-status-invalid';
            case 'no_source': return 'cdm-status-badge cdm-status-unknown';
            default: return 'cdm-status-badge cdm-status-unknown';
        }
    };

    // Filter platforms by search term
    const filteredPlatforms = pegasusStatus.platforms.filter(p =>
        p.display_name.toLowerCase().includes(platformFilter.toLowerCase()) ||
        p.id.toLowerCase().includes(platformFilter.toLowerCase())
    );

    // Rebuild meta.db
    const handleRebuildMetaDB = async () => {
        setIsGenerating(true);
        setGeneratingSystem('meta');
        showToast('Rebuilding meta.db... This may take a minute.');
        try {
            const res = await fetch(`${GATEWAY}/api/content/retrofe/rebuild-meta`, {
                method: 'POST',
                headers: buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' })
            });

            if (res.ok) {
                const data = await res.json();
                showToast(`✅ ${data.message || 'meta.db rebuilt'}`);
            } else {
                const err = await res.json().catch(() => ({}));
                showToast(`❌ Rebuild failed: ${err.detail || 'Unknown error'}`);
            }
        } catch (err) {
            console.error('[ContentDisplayManager] Rebuild failed:', err);
            showToast('❌ Rebuild error: ' + err.message);
        } finally {
            setIsGenerating(false);
            setGeneratingSystem('');
        }
    };

    // Marquee test handlers
    const handleTestImage = async () => {
        showToast('Showing test image...');
        try {
            await fetch(`${GATEWAY}/api/content/marquee/test/image`, {
                method: 'POST',
                headers: buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' }),
            });
            showToast('✅ Test image displayed');
        } catch (err) {
            showToast('❌ Test failed');
        }
    };

    const handleTestVideo = async () => {
        showToast('Showing test video...');
        try {
            await fetch(`${GATEWAY}/api/content/marquee/test/video`, {
                method: 'POST',
                headers: buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' }),
            });
            showToast('✅ Test video displayed');
        } catch (err) {
            showToast('❌ Test failed');
        }
    };

    const handleSimulateBrowse = async () => {
        showToast('Simulating game browse...');
        try {
            await fetch(`${GATEWAY}/api/content/marquee/test/browse`, {
                method: 'POST',
                headers: buildStandardHeaders({ panel: CDM_PANEL, scope: 'state' }),
            });
            showToast('✅ Browse simulation started');
        } catch (err) {
            showToast('❌ Simulation failed');
        }
    };

    // Save configuration
    const handleSave = async () => {
        setIsSaving(true);
        showToast('Saving configuration...');
        try {
            const [pathsRes, marqueeRes] = await Promise.all([
                fetch(`${GATEWAY}/api/content/paths`, {
                    method: 'POST',
                    headers: buildStandardHeaders({
                        panel: CDM_PANEL,
                        scope: 'config',
                        extraHeaders: { 'Content-Type': 'application/json' },
                    }),
                    body: JSON.stringify({
                        core: corePaths,
                        systems: systemPaths,
                        artwork: artworkPaths,
                    }),
                }),
                fetch(`${GATEWAY}/api/local/marquee/config`, {
                    method: 'POST',
                    headers: buildStandardHeaders({
                        panel: CDM_PANEL,
                        scope: 'config',
                        extraHeaders: { 'Content-Type': 'application/json' },
                    }),
                    body: JSON.stringify({
                        version: 1,
                        target_monitor_index: marqueeConfig.target_monitor_index,
                        safe_area: marqueeConfig.safeArea,
                        images_root: marqueeConfig.images_root || null,
                        videos_root: marqueeConfig.videos_root || null,
                        use_video_if_available: marqueeConfig.use_video_if_available,
                        fallback_mode: marqueeConfig.fallback_mode,
                    }),
                }),
            ]);

            if (pathsRes.ok && marqueeRes.ok) {
                showToast('✅ Configuration saved!');
            } else {
                showToast('⚠️ Some settings failed to save');
            }
        } catch (err) {
            console.error('[ContentDisplayManager] Save failed:', err);
            showToast('❌ Save error');
        } finally {
            setIsSaving(false);
        }
    };

    // Cancel and go back
    const handleCancel = () => {
        navigate('/assistants?agent=launchbox');
    };

    // Validate and save
    const handleValidateAndSave = async () => {
        await handleValidatePaths();
        await handleSave();
    };

    // Get status badge class
    const getStatusBadgeClass = (status) => {
        switch (status) {
            case 'valid': return 'cdm-status-badge cdm-status-valid';
            case 'invalid': return 'cdm-status-badge cdm-status-invalid';
            default: return 'cdm-status-badge cdm-status-unknown';
        }
    };

    return (
        <div className="cdm-container">
            {/* Toast notification */}
            {toast && <div className="cdm-toast">{toast}</div>}

            {/* Initial loading state */}
            {isLoading && (
                <div className="cdm-loading-overlay">
                    <div className="cdm-loading-spinner"></div>
                    <div className="cdm-loading-text">Loading configuration...</div>
                </div>
            )}

            {/* Generation loading overlay */}
            {isGenerating && (
                <div className="cdm-loading-overlay">
                    <div className="cdm-loading-spinner"></div>
                    <div className="cdm-loading-text">
                        {generatingSystem === 'all' && 'Generating all collections...'}
                        {generatingSystem === 'meta' && 'Rebuilding meta.db...'}
                        {generatingSystem && generatingSystem !== 'all' && generatingSystem !== 'meta' && `Generating ${generatingSystem}...`}
                    </div>
                </div>
            )}

            {/* Preview Modal */}
            {previewModal.open && (
                <div className="cdm-modal-backdrop" onClick={() => setPreviewModal({ open: false, system: '', content: '' })}>
                    <div className="cdm-modal" onClick={e => e.stopPropagation()}>
                        <div className="cdm-modal-header">
                            <h3>settings.conf for {previewModal.system}</h3>
                            <button
                                className="cdm-modal-close"
                                onClick={() => setPreviewModal({ open: false, system: '', content: '' })}
                            >
                                ×
                            </button>
                        </div>
                        <div className="cdm-modal-body">
                            <pre className="cdm-code-preview">{previewModal.content}</pre>
                        </div>
                        <div className="cdm-modal-footer">
                            <button
                                className="cdm-btn-secondary"
                                onClick={() => setPreviewModal({ open: false, system: '', content: '' })}
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Header */}
            <div className="cdm-header">
                <h1 className="cdm-title">Content & Display Manager</h1>
                <p className="cdm-subtitle">Configure ROM paths, Pegasus platforms, and marquee displays</p>
            </div>

            {/* Main Grid */}
            <div className="cdm-main-grid">
                {/* Section 1: ROM & Asset Paths */}
                <div className="cdm-section-card">
                    <h2 className="cdm-section-header">ROM & Asset Paths</h2>

                    {/* Core Paths */}
                    <h3 className="cdm-subsection-header">Core Paths</h3>
                    <div className="cdm-input-group">
                        <label className="cdm-label">LaunchBox Root Path</label>
                        <input
                            type="text"
                            className="cdm-input cdm-input-with-badge"
                            placeholder="e.g., <AA_DRIVE_ROOT>\LaunchBox"
                            value={corePaths.launchboxRoot}
                            onChange={(e) => setCorePaths(prev => ({ ...prev, launchboxRoot: e.target.value }))}
                        />
                        <span className={getStatusBadgeClass(pathStatus.launchboxRoot)}>
                            {pathStatus.launchboxRoot || 'Unknown'}
                        </span>
                    </div>

                    <div className="cdm-input-group">
                        <label className="cdm-label">RetroFE Root Path</label>
                        <input
                            type="text"
                            className="cdm-input cdm-input-with-badge"
                            placeholder="e.g., <AA_DRIVE_ROOT>\Tools\RetroFE"
                            value={corePaths.retrofeRoot}
                            onChange={(e) => setCorePaths(prev => ({ ...prev, retrofeRoot: e.target.value }))}
                        />
                        <span className={getStatusBadgeClass(pathStatus.retrofeRoot)}>
                            {pathStatus.retrofeRoot || 'Unknown'}
                        </span>
                    </div>

                    {/* ROM Paths */}
                    <h3 className="cdm-subsection-header">ROM Paths</h3>
                    <div className="cdm-input-group">
                        <label className="cdm-label">ROM Root Path</label>
                        <input
                            type="text"
                            className="cdm-input cdm-input-with-badge"
                            placeholder="e.g., <AA_DRIVE_ROOT>\Roms"
                            value={corePaths.romRoot}
                            onChange={(e) => setCorePaths(prev => ({ ...prev, romRoot: e.target.value }))}
                        />
                        <span className={getStatusBadgeClass(pathStatus.romRoot)}>
                            {pathStatus.romRoot || 'Unknown'}
                        </span>
                    </div>

                    <label className="cdm-label">Per-System Paths</label>
                    {systemPaths.map(sp => (
                        <div key={sp.id} className="cdm-system-path-row">
                            <input
                                type="text"
                                className="cdm-input"
                                placeholder="System Name"
                                value={sp.system}
                                onChange={(e) => updateSystemPath(sp.id, 'system', e.target.value)}
                            />
                            <input
                                type="text"
                                className="cdm-input"
                                placeholder="ROM Path"
                                value={sp.path}
                                onChange={(e) => updateSystemPath(sp.id, 'path', e.target.value)}
                            />
                            <button
                                className="cdm-btn-remove"
                                onClick={() => removeSystemPath(sp.id)}
                                title="Remove"
                            >
                                ×
                            </button>
                        </div>
                    ))}
                    <button className="cdm-btn-add" onClick={addSystemPath}>
                        + Add System Path
                    </button>

                    {/* Artwork / Asset Paths */}
                    <h3 className="cdm-subsection-header">Artwork / Asset Paths</h3>
                    <div className="cdm-input-group">
                        <label className="cdm-label">Splash Screens Path</label>
                        <input
                            type="text"
                            className="cdm-input"
                            placeholder="e.g., <AA_DRIVE_ROOT>\LaunchBox\Images\Splash"
                            value={artworkPaths.splashScreens}
                            onChange={(e) => setArtworkPaths(prev => ({ ...prev, splashScreens: e.target.value }))}
                        />
                    </div>

                    <div className="cdm-input-group">
                        <label className="cdm-label">Marquee Images Path</label>
                        <input
                            type="text"
                            className="cdm-input"
                            placeholder="e.g., <AA_DRIVE_ROOT>\LaunchBox\Images\Arcade - Marquee"
                            value={artworkPaths.marqueeImages}
                            onChange={(e) => setArtworkPaths(prev => ({ ...prev, marqueeImages: e.target.value }))}
                        />
                    </div>

                    <div className="cdm-input-group">
                        <label className="cdm-label">Marquee Videos Path</label>
                        <input
                            type="text"
                            className="cdm-input"
                            placeholder="e.g., <AA_DRIVE_ROOT>\LaunchBox\Videos\Arcade - Marquee"
                            value={artworkPaths.marqueeVideos}
                            onChange={(e) => setArtworkPaths(prev => ({ ...prev, marqueeVideos: e.target.value }))}
                        />
                    </div>

                    <div className="cdm-input-group">
                        <label className="cdm-label">Bezels / Overlays Path</label>
                        <input
                            type="text"
                            className="cdm-input"
                            placeholder="e.g., <AA_DRIVE_ROOT>\LaunchBox\Images\Bezels"
                            value={artworkPaths.bezels}
                            onChange={(e) => setArtworkPaths(prev => ({ ...prev, bezels: e.target.value }))}
                        />
                    </div>

                    <div className="cdm-input-group">
                        <label className="cdm-label">Manuals Path (Optional)</label>
                        <input
                            type="text"
                            className="cdm-input"
                            placeholder="e.g., <AA_DRIVE_ROOT>\LaunchBox\Manuals"
                            value={artworkPaths.manuals}
                            onChange={(e) => setArtworkPaths(prev => ({ ...prev, manuals: e.target.value }))}
                        />
                    </div>

                    <button className="cdm-btn-primary" onClick={handleValidatePaths}>
                        Validate Paths
                    </button>
                </div>

                {/* Section 2: Pegasus Platforms */}
                <div className="cdm-section-card">
                    <h2 className="cdm-section-header">Pegasus Platforms</h2>

                    {/* Status Summary */}
                    <div className="cdm-pegasus-summary">
                        <div className="cdm-stat-row">
                            <span className="cdm-stat-label">Status:</span>
                            <span className={pegasusStatus.installed ? 'cdm-status-valid' : 'cdm-status-invalid'}>
                                {pegasusStatus.installed ? '✓ Installed' : '✗ Not Found'}
                            </span>
                        </div>
                        <div className="cdm-stat-row">
                            <span className="cdm-stat-label">Platforms:</span>
                            <span className="cdm-stat-value">{pegasusStatus.platform_count}</span>
                        </div>
                        <div className="cdm-stat-row">
                            <span className="cdm-stat-label">Total Games:</span>
                            <span className="cdm-stat-value">{pegasusStatus.total_games.toLocaleString()}</span>
                        </div>
                    </div>

                    {/* Search/Filter */}
                    <div className="cdm-input-group">
                        <label className="cdm-label">Filter Platforms</label>
                        <input
                            type="text"
                            className="cdm-input"
                            placeholder="Search platforms..."
                            value={platformFilter}
                            onChange={(e) => setPlatformFilter(e.target.value)}
                        />
                    </div>

                    {/* Platform Table */}
                    <div className="cdm-table-scroll">
                        <table className="cdm-table">
                            <thead className="cdm-table-header">
                                <tr>
                                    <th className="cdm-th">Platform</th>
                                    <th className="cdm-th">Games</th>
                                    <th className="cdm-th">Status</th>
                                    <th className="cdm-th">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredPlatforms.map((platform) => (
                                    <tr key={platform.id}>
                                        <td className="cdm-td cdm-td-platform">
                                            <span className="cdm-platform-name">{platform.display_name}</span>
                                        </td>
                                        <td className="cdm-td cdm-td-games">
                                            <span className="cdm-game-count">{platform.game_count}</span>
                                            {platform.launchbox_count && platform.launchbox_count !== platform.game_count && (
                                                <span className="cdm-lb-count"> / {platform.launchbox_count} LB</span>
                                            )}
                                        </td>
                                        <td className="cdm-td">
                                            <span className={getSyncStatusClass(platform.sync_status)}>
                                                {platform.sync_status === 'synced' && '✓ Synced'}
                                                {platform.sync_status === 'outdated' && '⚠ Outdated'}
                                                {platform.sync_status === 'missing' && '✗ Missing'}
                                                {platform.sync_status === 'no_source' && '— No LB'}
                                                {!['synced', 'outdated', 'missing', 'no_source'].includes(platform.sync_status) && platform.sync_status}
                                            </span>
                                        </td>
                                        <td className="cdm-td">
                                            <button
                                                className="cdm-btn-small"
                                                onClick={() => handleSyncPlatform(platform.id)}
                                                disabled={isGenerating}
                                            >
                                                {generatingSystem === platform.id ? '...' : 'Sync'}
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* Action Buttons */}
                    <div className="cdm-button-row">
                        <button className="cdm-btn-primary" onClick={handleSyncAllPlatforms} disabled={isGenerating}>
                            {isGenerating && generatingSystem === 'all' ? 'Syncing...' : 'Sync All Platforms'}
                        </button>
                        <button className="cdm-btn-secondary" onClick={handleRefreshPegasusStatus}>
                            Refresh Status
                        </button>
                    </div>
                </div>

                {/* Section 3: Marquee Configuration */}
                <div className="cdm-section-card">
                    <h2 className="cdm-section-header">Marquee Configuration</h2>

                    {/* Display / Monitor */}
                    <h3 className="cdm-subsection-header">Display / Monitor</h3>
                    <div className="cdm-input-group">
                        <label className="cdm-label">Target Display</label>
                        <select
                            className="cdm-select"
                            value={marqueeConfig.targetDisplay}
                            onChange={(e) => setMarqueeConfig(prev => ({ ...prev, targetDisplay: e.target.value }))}
                        >
                            {availableDisplays.map((display, idx) => (
                                <option key={idx} value={display}>{display}</option>
                            ))}
                        </select>
                    </div>

                    <div className="cdm-input-group">
                        <label className="cdm-label">Marquee Resolution</label>
                        <input
                            type="text"
                            className="cdm-input"
                            value={marqueeConfig.resolution}
                            readOnly
                        />
                    </div>

                    <label className="cdm-label">Safe Area</label>
                    <div className="cdm-safe-area-grid">
                        <div>
                            <label className="cdm-label-small">X Position</label>
                            <input
                                type="number"
                                className="cdm-input-small"
                                value={marqueeConfig.safeArea.x}
                                onChange={(e) => setMarqueeConfig(prev => ({
                                    ...prev,
                                    safeArea: { ...prev.safeArea, x: parseInt(e.target.value) || 0 }
                                }))}
                            />
                        </div>
                        <div>
                            <label className="cdm-label-small">Y Position</label>
                            <input
                                type="number"
                                className="cdm-input-small"
                                value={marqueeConfig.safeArea.y}
                                onChange={(e) => setMarqueeConfig(prev => ({
                                    ...prev,
                                    safeArea: { ...prev.safeArea, y: parseInt(e.target.value) || 0 }
                                }))}
                            />
                        </div>
                        <div>
                            <label className="cdm-label-small">Width</label>
                            <input
                                type="number"
                                className="cdm-input-small"
                                value={marqueeConfig.safeArea.width}
                                onChange={(e) => setMarqueeConfig(prev => ({
                                    ...prev,
                                    safeArea: { ...prev.safeArea, width: parseInt(e.target.value) || 0 }
                                }))}
                            />
                        </div>
                        <div>
                            <label className="cdm-label-small">Height</label>
                            <input
                                type="number"
                                className="cdm-input-small"
                                value={marqueeConfig.safeArea.height}
                                onChange={(e) => setMarqueeConfig(prev => ({
                                    ...prev,
                                    safeArea: { ...prev.safeArea, height: parseInt(e.target.value) || 0 }
                                }))}
                            />
                        </div>
                    </div>

                    {/* Media Paths - Marquee-specific overrides */}
                    <h3 className="cdm-subsection-header">Media Paths (override or leave blank to use ROM &amp; Asset Paths)</h3>
                    <div className="cdm-input-group">
                        <label className="cdm-label">Marquee Images Path</label>
                        <input
                            type="text"
                            className="cdm-input"
                            placeholder={artworkPaths.marqueeImages || '<AA_DRIVE_ROOT>\\LaunchBox\\Images\\Arcade - Marquee'}
                            value={marqueeConfig.imagePath || ''}
                            onChange={(e) => setMarqueeConfig(prev => ({ ...prev, imagePath: e.target.value }))}
                        />
                        <small className="cdm-input-hint">
                            {marqueeConfig.imagePath ? 'Using custom path' : `Inheriting: ${artworkPaths.marqueeImages || '(not set)'}`}
                        </small>
                    </div>

                    <div className="cdm-input-group">
                        <label className="cdm-label">Marquee Videos Path</label>
                        <input
                            type="text"
                            className="cdm-input"
                            placeholder={artworkPaths.marqueeVideos || '<AA_DRIVE_ROOT>\\LaunchBox\\Videos\\Arcade - Marquee'}
                            value={marqueeConfig.videoPath || ''}
                            onChange={(e) => setMarqueeConfig(prev => ({ ...prev, videoPath: e.target.value }))}
                        />
                        <small className="cdm-input-hint">
                            {marqueeConfig.videoPath ? 'Using custom path' : `Inheriting: ${artworkPaths.marqueeVideos || '(not set)'}`}
                        </small>
                    </div>

                    {/* Behavior */}
                    <h3 className="cdm-subsection-header">Behavior</h3>
                    <div className="cdm-checkbox-container">
                        <input
                            type="checkbox"
                            id="useVideo"
                            className="cdm-checkbox"
                            checked={marqueeConfig.useVideo}
                            onChange={(e) => setMarqueeConfig(prev => ({ ...prev, useVideo: e.target.checked }))}
                        />
                        <label htmlFor="useVideo" className="cdm-checkbox-label">
                            Use video if available
                        </label>
                    </div>

                    <div className="cdm-checkbox-container">
                        <input
                            type="checkbox"
                            id="useFallback"
                            className="cdm-checkbox"
                            checked={marqueeConfig.useFallback}
                            onChange={(e) => setMarqueeConfig(prev => ({ ...prev, useFallback: e.target.checked }))}
                        />
                        <label htmlFor="useFallback" className="cdm-checkbox-label">
                            Fallback to system image when game asset is missing
                        </label>
                    </div>

                    {/* Testing */}
                    <h3 className="cdm-subsection-header">Testing</h3>
                    <div className="cdm-test-buttons-row">
                        <button className="cdm-btn-small" onClick={handleTestImage}>
                            Show Test Image
                        </button>
                        <button className="cdm-btn-small" onClick={handleTestVideo}>
                            Show Test Video
                        </button>
                        <button className="cdm-btn-small" onClick={handleSimulateBrowse}>
                            Simulate Game Browse
                        </button>
                    </div>

                    {/* Launch Marquee Display */}
                    <h3 className="cdm-subsection-header">Launch Display</h3>
                    <p className="cdm-hint-text">
                        Open the marquee display in a new window. Drag it to your marquee monitor and press F11 for fullscreen.
                    </p>
                    <div className="cdm-test-buttons-row">
                        <button
                            className="cdm-btn-primary"
                            onClick={() => window.open('/marquee-v2', 'marquee', 'width=1920,height=360')}
                        >
                            🖥️ Launch Marquee Display
                        </button>
                        <button
                            className="cdm-btn-small cdm-btn-outline"
                            onClick={() => window.open('/marquee', 'marquee-legacy', 'width=800,height=400')}
                        >
                            Launch Legacy (Text Only)
                        </button>
                    </div>
                </div>
            </div>

            {/* Action Bar */}
            <div className="cdm-action-bar">
                {isDev && (
                    <button className="cdm-btn-secondary" onClick={handleShowRegistry} disabled={isSaving}>
                        Show Registry (console)
                    </button>
                )}
                <button className="cdm-btn-secondary" onClick={handleCancel} disabled={isSaving}>
                    Cancel
                </button>
                <button className="cdm-btn-secondary" onClick={handleValidateAndSave} disabled={isSaving}>
                    Validate & Save
                </button>
                <button className="cdm-btn-primary" onClick={handleSave} disabled={isSaving}>
                    {isSaving ? 'Saving...' : 'Save Configuration'}
                </button>
            </div>
        </div>
    );
};

export default ContentDisplayManager;
