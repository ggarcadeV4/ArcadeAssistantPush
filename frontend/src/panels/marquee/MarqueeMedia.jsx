// @panel: MarqueeMedia
// @role: Media player for marquee display with still→video→still cycling
// @data: Polls /api/local/marquee/now-playing, resolves media via /api/local/marquee/resolve
// @version: 1.0

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { getGatewayUrl } from '../../services/gateway'
import { buildStandardHeaders } from '../../utils/identity'

const MARQUEE_PANEL = 'marquee-media'

const API_BASE = window.location.port === '5173'
    ? getGatewayUrl()
    : '';

// Poll interval for now-playing (300ms as per spec)
const POLL_INTERVAL = 300;

// Default cycle time: show still for 5 seconds before video
const DEFAULT_CYCLE_MS = 5000;

export default function MarqueeMedia() {
    const [nowPlaying, setNowPlaying] = useState(null);
    const [mediaData, setMediaData] = useState(null);
    const [settings, setSettings] = useState(null);
    const [phase, setPhase] = useState('still'); // 'still' | 'video' | 'idle'
    const [isOffline, setIsOffline] = useState(false);
    const [noMedia, setNoMedia] = useState(false);
    const [showSettings, setShowSettings] = useState(false);
    const [testResult, setTestResult] = useState(null);

    const pollRef = useRef(null);
    const lastGameRef = useRef(null);
    const videoRef = useRef(null);
    const stillTimerRef = useRef(null);

    // Fetch now-playing state
    const fetchNowPlaying = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/local/marquee/now-playing`);
            if (res.ok) {
                const data = await res.json();
                setIsOffline(false);
                if (data.now_playing) {
                    setNowPlaying(data.now_playing);
                    // If game changed, resolve new media
                    if (lastGameRef.current !== data.now_playing.game_title) {
                        lastGameRef.current = data.now_playing.game_title;
                        await resolveMedia(data.now_playing);
                    }
                } else {
                    setNowPlaying(null);
                    setNoMedia(true);
                }
            } else {
                setIsOffline(true);
            }
        } catch (e) {
            console.warn('[MarqueeMedia] Failed to fetch now-playing:', e);
            setIsOffline(true);
        }
    }, []);

    // Resolve media for a game
    const resolveMedia = async (game) => {
        try {
            const res = await fetch(`${API_BASE}/api/local/marquee/resolve`, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: MARQUEE_PANEL,
                    scope: 'state',
                    extraHeaders: { 'Content-Type': 'application/json' },
                }),
                body: JSON.stringify({
                    game_id: game.game_id,
                    title: game.game_title,
                    platform: game.platform || 'Arcade',
                    prefer_video: true
                })
            });

            if (res.ok) {
                const data = await res.json();
                setMediaData(data);
                setNoMedia(!data.ok || data.fallback_used === 'no_media_found');

                // Start media cycle
                if (data.all_urls?.game_image && data.all_urls?.game_video) {
                    // Have both: start with still, then video
                    setPhase('still');
                    startStillTimer();
                } else if (data.primary_type === 'video') {
                    setPhase('video');
                } else if (data.primary_type) {
                    setPhase('still');
                } else {
                    setPhase('idle');
                }
            }
        } catch (e) {
            console.warn('[MarqueeMedia] Failed to resolve media:', e);
            setNoMedia(true);
        }
    };

    // Fetch settings on mount
    const fetchSettings = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/local/marquee/media-settings`);
            if (res.ok) {
                const data = await res.json();
                setSettings(data.settings);
            }
        } catch (e) {
            console.warn('[MarqueeMedia] Failed to fetch settings:', e);
        }
    }, []);

    // Start still timer (show image for X seconds, then switch to video)
    const startStillTimer = useCallback(() => {
        if (stillTimerRef.current) {
            clearTimeout(stillTimerRef.current);
        }
        const cycleMs = settings?.cycle_ms || DEFAULT_CYCLE_MS;
        stillTimerRef.current = setTimeout(() => {
            if (mediaData?.all_urls?.game_video) {
                setPhase('video');
            }
        }, cycleMs);
    }, [settings, mediaData]);

    // When video ends, go back to still
    const handleVideoEnded = useCallback(() => {
        if (mediaData?.all_urls?.game_image) {
            setPhase('still');
            startStillTimer();
        }
    }, [mediaData, startStillTimer]);

    // Initial load and polling
    useEffect(() => {
        fetchSettings();
        fetchNowPlaying();

        pollRef.current = setInterval(() => {
            fetchNowPlaying();
        }, POLL_INTERVAL);

        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
            if (stillTimerRef.current) clearTimeout(stillTimerRef.current);
        };
    }, [fetchNowPlaying, fetchSettings]);

    // Update video ref when phase changes
    useEffect(() => {
        if (phase === 'video' && videoRef.current) {
            videoRef.current.play().catch(console.warn);
        }
    }, [phase]);

    // Save settings
    const saveSettings = async (newSettings) => {
        try {
            const res = await fetch(`${API_BASE}/api/local/marquee/media-settings`, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: MARQUEE_PANEL,
                    scope: 'config',
                    extraHeaders: { 'Content-Type': 'application/json' },
                }),
                body: JSON.stringify(newSettings)
            });
            if (res.ok) {
                const data = await res.json();
                setSettings(data.settings);
                return true;
            }
        } catch (e) {
            console.error('[MarqueeMedia] Failed to save settings:', e);
        }
        return false;
    };

    // Test resolve
    const testResolve = async () => {
        const testGame = prompt('Enter game title to test:', 'Pac-Man');
        if (!testGame) return;

        try {
            const res = await fetch(`${API_BASE}/api/local/marquee/resolve`, {
                method: 'POST',
                headers: buildStandardHeaders({
                    panel: MARQUEE_PANEL,
                    scope: 'state',
                    extraHeaders: { 'Content-Type': 'application/json' },
                }),
                body: JSON.stringify({
                    title: testGame,
                    platform: 'Arcade',
                    prefer_video: true
                })
            });
            if (res.ok) {
                const data = await res.json();
                setTestResult(data);
            }
        } catch (e) {
            setTestResult({ error: e.message });
        }
    };

    // Offline state
    if (isOffline) {
        return (
            <div style={styles.container}>
                <div style={styles.noMediaCard}>
                    <div style={styles.noMediaIcon}>⚡</div>
                    <div style={styles.noMediaText}>Marquee Offline</div>
                    <div style={styles.noMediaSubtext}>Reconnecting...</div>
                </div>
                <button style={styles.settingsButton} onClick={() => setShowSettings(true)}>⚙️</button>
            </div>
        );
    }

    // No media found state
    if (noMedia || !mediaData?.primary_url) {
        return (
            <div style={styles.container}>
                <div style={styles.noMediaCard}>
                    <div style={styles.noMediaIcon}>🎮</div>
                    <div style={styles.noMediaText}>NO MEDIA FOUND</div>
                    <div style={styles.noMediaSubtext}>
                        {nowPlaying?.game_title || 'Select a game'}
                    </div>
                </div>
                <button style={styles.settingsButton} onClick={() => setShowSettings(true)}>⚙️</button>
                {showSettings && (
                    <SettingsModal
                        settings={settings}
                        onSave={saveSettings}
                        onClose={() => setShowSettings(false)}
                        onTest={testResolve}
                        testResult={testResult}
                    />
                )}
            </div>
        );
    }

    // Get URLs
    const imageUrl = mediaData.all_urls?.game_image;
    const videoUrl = mediaData.all_urls?.game_video;
    const currentUrl = phase === 'video' ? videoUrl : (imageUrl || mediaData.primary_url);

    return (
        <div style={styles.container}>
            {/* Media Display */}
            <div style={styles.mediaWrapper}>
                {phase === 'video' && videoUrl ? (
                    <video
                        ref={videoRef}
                        key={videoUrl}
                        src={`${API_BASE}${videoUrl}`}
                        style={styles.media}
                        autoPlay
                        muted
                        onEnded={handleVideoEnded}
                        onError={() => setPhase('still')}
                    />
                ) : (
                    <img
                        key={currentUrl}
                        src={`${API_BASE}${currentUrl}`}
                        style={styles.media}
                        alt={nowPlaying?.game_title || 'Marquee'}
                        onError={() => setNoMedia(true)}
                    />
                )}

                {/* Game title overlay */}
                <div style={styles.titleOverlay}>
                    <div style={styles.nowPlayingLabel}>NOW PLAYING</div>
                    <div style={styles.gameTitle}>{nowPlaying?.game_title}</div>
                    {nowPlaying?.platform && (
                        <div style={styles.platform}>{nowPlaying.platform}</div>
                    )}
                </div>
            </div>

            {/* Settings button */}
            <button style={styles.settingsButton} onClick={() => setShowSettings(true)}>⚙️</button>

            {/* Settings modal */}
            {showSettings && (
                <SettingsModal
                    settings={settings}
                    onSave={saveSettings}
                    onClose={() => setShowSettings(false)}
                    onTest={testResolve}
                    testResult={testResult}
                />
            )}
        </div>
    );
}

// Settings Modal Component
function SettingsModal({ settings, onSave, onClose, onTest, testResult }) {
    const [imageDir, setImageDir] = useState(settings?.image_dir || '');
    const [videoDir, setVideoDir] = useState(settings?.video_dir || '');
    const [idleImage, setIdleImage] = useState(settings?.idle_image || '');
    const [idleVideo, setIdleVideo] = useState(settings?.idle_video || '');
    const [cycleMs, setCycleMs] = useState(settings?.cycle_ms || 5000);
    const [preferVideo, setPreferVideo] = useState(settings?.prefer_video ?? true);
    const [saving, setSaving] = useState(false);

    const handleSave = async () => {
        setSaving(true);
        await onSave({
            image_dir: imageDir || null,
            video_dir: videoDir || null,
            idle_image: idleImage || null,
            idle_video: idleVideo || null,
            cycle_ms: cycleMs,
            prefer_video: preferVideo
        });
        setSaving(false);
        onClose();
    };

    return (
        <div style={styles.modalOverlay}>
            <div style={styles.modalContent}>
                <h2 style={styles.modalTitle}>Marquee Media Settings</h2>

                <div style={styles.formGroup}>
                    <label style={styles.label}>Image Directory</label>
                    <input
                        type="text"
                        style={styles.input}
                        value={imageDir}
                        onChange={(e) => setImageDir(e.target.value)}
                        placeholder="e.g., <drive>\\LaunchBox\\Images\\Arcade\\Marquee"
                    />
                </div>

                <div style={styles.formGroup}>
                    <label style={styles.label}>Video Directory</label>
                    <input
                        type="text"
                        style={styles.input}
                        value={videoDir}
                        onChange={(e) => setVideoDir(e.target.value)}
                        placeholder="e.g., <drive>\\LaunchBox\\Videos\\Arcade"
                    />
                </div>

                <div style={styles.formGroup}>
                    <label style={styles.label}>Idle Image Path</label>
                    <input
                        type="text"
                        style={styles.input}
                        value={idleImage}
                        onChange={(e) => setIdleImage(e.target.value)}
                        placeholder="Path to default/idle image"
                    />
                </div>

                <div style={styles.formGroup}>
                    <label style={styles.label}>Idle Video Path</label>
                    <input
                        type="text"
                        style={styles.input}
                        value={idleVideo}
                        onChange={(e) => setIdleVideo(e.target.value)}
                        placeholder="Path to default/idle video"
                    />
                </div>

                <div style={styles.formRow}>
                    <div style={styles.formGroup}>
                        <label style={styles.label}>Still Display Time (ms)</label>
                        <input
                            type="number"
                            style={styles.input}
                            value={cycleMs}
                            onChange={(e) => setCycleMs(parseInt(e.target.value) || 5000)}
                            min={1000}
                            max={60000}
                        />
                    </div>
                    <div style={styles.formGroup}>
                        <label style={styles.label}>
                            <input
                                type="checkbox"
                                checked={preferVideo}
                                onChange={(e) => setPreferVideo(e.target.checked)}
                            />
                            {' '}Prefer Video
                        </label>
                    </div>
                </div>

                <div style={styles.buttonRow}>
                    <button style={styles.testButton} onClick={onTest}>🔍 Test Resolve</button>
                    <button style={styles.cancelButton} onClick={onClose}>Cancel</button>
                    <button style={styles.saveButton} onClick={handleSave} disabled={saving}>
                        {saving ? 'Saving...' : 'Save Settings'}
                    </button>
                </div>

                {testResult && (
                    <div style={styles.testResultBox}>
                        <h4>Test Result:</h4>
                        <pre style={styles.testResultPre}>
                            {JSON.stringify(testResult, null, 2)}
                        </pre>
                    </div>
                )}
            </div>
        </div>
    );
}

// Styles
const styles = {
    container: {
        width: '100%',
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#000',
        position: 'relative',
        overflow: 'hidden',
    },
    mediaWrapper: {
        width: '100%',
        height: '100%',
        position: 'relative',
    },
    media: {
        width: '100%',
        height: '100%',
        objectFit: 'contain',
        background: '#000',
    },
    titleOverlay: {
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        padding: '20px 40px',
        background: 'linear-gradient(transparent, rgba(0,0,0,0.9))',
        color: '#fff',
        textAlign: 'center',
    },
    nowPlayingLabel: {
        fontSize: '12px',
        letterSpacing: '3px',
        color: '#6af7ff',
        marginBottom: '8px',
    },
    gameTitle: {
        fontSize: '28px',
        fontWeight: 800,
        textShadow: '0 2px 10px rgba(0,0,0,0.8)',
    },
    platform: {
        fontSize: '14px',
        color: 'rgba(255,255,255,0.6)',
        marginTop: '6px',
    },
    noMediaCard: {
        padding: '40px 60px',
        borderRadius: '16px',
        background: 'linear-gradient(135deg, rgba(30,30,40,0.95), rgba(50,50,70,0.95))',
        border: '2px dashed rgba(255,255,255,0.2)',
        textAlign: 'center',
    },
    noMediaIcon: {
        fontSize: '64px',
        marginBottom: '16px',
    },
    noMediaText: {
        fontSize: '24px',
        fontWeight: 700,
        color: '#ff6b6b',
    },
    noMediaSubtext: {
        fontSize: '16px',
        color: 'rgba(255,255,255,0.5)',
        marginTop: '12px',
    },
    settingsButton: {
        position: 'absolute',
        top: '16px',
        right: '16px',
        width: '40px',
        height: '40px',
        borderRadius: '50%',
        border: 'none',
        background: 'rgba(255,255,255,0.1)',
        color: '#fff',
        fontSize: '20px',
        cursor: 'pointer',
        opacity: 0.5,
        transition: 'opacity 0.2s',
    },
    modalOverlay: {
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.85)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
    },
    modalContent: {
        background: '#1a1a2e',
        borderRadius: '16px',
        padding: '32px',
        width: '500px',
        maxWidth: '90vw',
        maxHeight: '80vh',
        overflow: 'auto',
        color: '#fff',
    },
    modalTitle: {
        fontSize: '24px',
        fontWeight: 700,
        marginBottom: '24px',
        color: '#6af7ff',
    },
    formGroup: {
        marginBottom: '16px',
    },
    formRow: {
        display: 'flex',
        gap: '16px',
    },
    label: {
        display: 'block',
        fontSize: '13px',
        color: 'rgba(255,255,255,0.7)',
        marginBottom: '6px',
    },
    input: {
        width: '100%',
        padding: '10px 14px',
        borderRadius: '8px',
        border: '1px solid rgba(255,255,255,0.2)',
        background: 'rgba(0,0,0,0.3)',
        color: '#fff',
        fontSize: '14px',
    },
    buttonRow: {
        display: 'flex',
        gap: '12px',
        marginTop: '24px',
    },
    testButton: {
        flex: 1,
        padding: '12px',
        borderRadius: '8px',
        border: 'none',
        background: '#2a2a4e',
        color: '#6af7ff',
        fontSize: '14px',
        fontWeight: 600,
        cursor: 'pointer',
    },
    cancelButton: {
        flex: 1,
        padding: '12px',
        borderRadius: '8px',
        border: '1px solid rgba(255,255,255,0.2)',
        background: 'transparent',
        color: '#fff',
        fontSize: '14px',
        cursor: 'pointer',
    },
    saveButton: {
        flex: 2,
        padding: '12px',
        borderRadius: '8px',
        border: 'none',
        background: 'linear-gradient(135deg, #00d9ff, #0099ff)',
        color: '#000',
        fontSize: '14px',
        fontWeight: 700,
        cursor: 'pointer',
    },
    testResultBox: {
        marginTop: '20px',
        padding: '16px',
        background: 'rgba(0,0,0,0.4)',
        borderRadius: '8px',
    },
    testResultPre: {
        fontSize: '11px',
        color: '#aaa',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
    },
};
