// @panel: MarqueeText
// @role: MVP scrolling text marquee with messages and alerts
// @data: Polls /api/local/marquee/messages for queue, falls back to current-game
// @version: 1.0

import React, { useEffect, useState, useCallback, useRef } from 'react';

const API_BASE = window.location.port === '5173'
    ? 'http://localhost:8787'
    : '';

// Poll interval in milliseconds
const POLL_INTERVAL = 1500;

// Severity colors
const SEVERITY_STYLES = {
    error: {
        background: 'linear-gradient(135deg, rgba(255,50,50,0.95), rgba(180,30,30,0.95))',
        border: '2px solid #ff4444',
        textShadow: '0 0 20px rgba(255,100,100,0.8)',
        animation: 'pulse-error 1s ease-in-out infinite',
    },
    warn: {
        background: 'linear-gradient(135deg, rgba(255,180,0,0.95), rgba(200,140,0,0.95))',
        border: '2px solid #ffaa00',
        textShadow: '0 0 15px rgba(255,200,100,0.6)',
    },
    info: {
        background: 'linear-gradient(135deg, rgba(0,150,255,0.9), rgba(0,100,200,0.9))',
        border: '2px solid #00aaff',
        textShadow: '0 0 12px rgba(100,200,255,0.5)',
    },
};

export default function MarqueeText() {
    const [messages, setMessages] = useState([]);
    const [priorityAlert, setPriorityAlert] = useState(null);
    const [currentGame, setCurrentGame] = useState(null);
    const [isOffline, setIsOffline] = useState(false);
    const [displayIndex, setDisplayIndex] = useState(0);
    const pollRef = useRef(null);

    // Fetch messages from backend
    const fetchMessages = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/local/marquee/messages?limit=10`);
            if (res.ok) {
                const data = await res.json();
                setMessages(data.messages || []);
                // Priority alert is the first error/warn alert
                setPriorityAlert(data.priority_alerts?.[0] || null);
                setIsOffline(false);
            } else {
                setIsOffline(true);
            }
        } catch (e) {
            console.warn('[MarqueeText] Failed to fetch messages:', e);
            setIsOffline(true);
        }
    }, []);

    // Fetch current game as fallback
    const fetchCurrentGame = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/local/marquee/current-game`);
            if (res.ok) {
                const data = await res.json();
                setCurrentGame(data);
            }
        } catch (e) {
            console.warn('[MarqueeText] Failed to fetch current game:', e);
        }
    }, []);

    // Initial load and polling
    useEffect(() => {
        fetchMessages();
        fetchCurrentGame();

        pollRef.current = setInterval(() => {
            fetchMessages();
            fetchCurrentGame();
        }, POLL_INTERVAL);

        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, [fetchMessages, fetchCurrentGame]);

    // Rotate through messages
    useEffect(() => {
        if (messages.length > 1) {
            const rotateTimer = setInterval(() => {
                setDisplayIndex((prev) => (prev + 1) % messages.length);
            }, 5000);
            return () => clearInterval(rotateTimer);
        } else {
            setDisplayIndex(0);
        }
    }, [messages.length]);

    // Determine what to display
    const activeMessage = messages[displayIndex];
    const hasMessages = messages.length > 0;

    // Offline state
    if (isOffline) {
        return (
            <div style={styles.container}>
                <div style={styles.offlineCard}>
                    <div style={styles.offlineText}>⚡ Marquee Offline</div>
                    <div style={styles.offlineSubtext}>Reconnecting...</div>
                </div>
            </div>
        );
    }

    // Priority alert display (overrides everything)
    if (priorityAlert) {
        const severityStyle = SEVERITY_STYLES[priorityAlert.severity] || SEVERITY_STYLES.info;
        return (
            <div style={styles.container}>
                <div style={{ ...styles.alertCard, ...severityStyle }}>
                    <div style={styles.alertIcon}>
                        {priorityAlert.severity === 'error' ? '🚨' : '⚠️'}
                    </div>
                    <div style={styles.alertText}>{priorityAlert.text}</div>
                    {priorityAlert.source && (
                        <div style={styles.alertSource}>Source: {priorityAlert.source}</div>
                    )}
                </div>
            </div>
        );
    }

    // Messages display
    if (hasMessages && activeMessage) {
        const isAlert = activeMessage.type === 'alert';
        const severityStyle = isAlert && activeMessage.severity
            ? SEVERITY_STYLES[activeMessage.severity]
            : null;

        return (
            <div style={styles.container}>
                <div style={{ ...styles.messageCard, ...(severityStyle || {}) }}>
                    <div style={styles.scrollingWrapper}>
                        <div style={styles.scrollingText}>
                            {activeMessage.text}
                        </div>
                    </div>
                    {messages.length > 1 && (
                        <div style={styles.messageCounter}>
                            {displayIndex + 1} / {messages.length}
                        </div>
                    )}
                </div>
            </div>
        );
    }

    // Fallback: Show current game (Now Playing)
    const gameTitle = currentGame?.title || 'G&G Arcade';
    const isIdle = !currentGame?.game_id;

    return (
        <div style={styles.container}>
            <div style={styles.nowPlayingCard}>
                <div style={styles.nowPlayingLabel}>
                    {isIdle ? 'WELCOME TO' : 'NOW PLAYING'}
                </div>
                <div style={styles.nowPlayingTitle}>{gameTitle}</div>
                {currentGame?.platform && !isIdle && (
                    <div style={styles.nowPlayingPlatform}>{currentGame.platform}</div>
                )}
            </div>
        </div>
    );
}

// Styles
const styles = {
    container: {
        minHeight: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        background: 'transparent',
        fontFamily: "'Inter', system-ui, sans-serif",
    },

    // Offline state
    offlineCard: {
        padding: '24px 40px',
        borderRadius: '12px',
        background: 'rgba(60,60,80,0.9)',
        border: '1px solid rgba(255,255,255,0.1)',
        textAlign: 'center',
    },
    offlineText: {
        fontSize: '20px',
        fontWeight: 700,
        color: '#aaa',
    },
    offlineSubtext: {
        fontSize: '14px',
        color: '#666',
        marginTop: '8px',
    },

    // Alert card
    alertCard: {
        padding: '24px 40px',
        borderRadius: '16px',
        textAlign: 'center',
        minWidth: '400px',
        maxWidth: '80vw',
        boxShadow: '0 10px 50px rgba(0,0,0,0.5)',
    },
    alertIcon: {
        fontSize: '48px',
        marginBottom: '12px',
    },
    alertText: {
        fontSize: '28px',
        fontWeight: 800,
        color: '#fff',
        lineHeight: 1.3,
    },
    alertSource: {
        fontSize: '12px',
        color: 'rgba(255,255,255,0.7)',
        marginTop: '12px',
        textTransform: 'uppercase',
        letterSpacing: '1px',
    },

    // Message card
    messageCard: {
        padding: '20px 40px',
        borderRadius: '12px',
        background: 'linear-gradient(135deg, rgba(10,20,40,0.95), rgba(20,30,60,0.95))',
        border: '1px solid rgba(0,255,255,0.3)',
        boxShadow: '0 8px 40px rgba(0,0,0,0.4), 0 0 20px rgba(0,255,255,0.1)',
        minWidth: '400px',
        maxWidth: '90vw',
        position: 'relative',
        overflow: 'hidden',
    },
    scrollingWrapper: {
        overflow: 'hidden',
    },
    scrollingText: {
        fontSize: '24px',
        fontWeight: 600,
        color: '#e8f7ff',
        textAlign: 'center',
        whiteSpace: 'nowrap',
        animation: 'scroll-text 15s linear infinite',
    },
    messageCounter: {
        position: 'absolute',
        bottom: '8px',
        right: '12px',
        fontSize: '11px',
        color: 'rgba(255,255,255,0.4)',
    },

    // Now Playing card
    nowPlayingCard: {
        padding: '28px 48px',
        borderRadius: '16px',
        background: 'linear-gradient(135deg, rgba(10,12,20,0.95), rgba(20,25,40,0.95))',
        border: '1px solid rgba(0,255,255,0.25)',
        boxShadow: '0 12px 50px rgba(0,0,0,0.5), 0 0 30px rgba(0,255,255,0.08)',
        textAlign: 'center',
        minWidth: '400px',
    },
    nowPlayingLabel: {
        fontSize: '13px',
        letterSpacing: '4px',
        color: '#6af7ff',
        marginBottom: '12px',
        fontWeight: 600,
    },
    nowPlayingTitle: {
        fontSize: '32px',
        fontWeight: 800,
        color: '#ffffff',
        textShadow: '0 0 20px rgba(0,255,255,0.3)',
    },
    nowPlayingPlatform: {
        fontSize: '14px',
        color: 'rgba(232,247,255,0.6)',
        marginTop: '10px',
    },
};

// Inject keyframe animations
if (typeof document !== 'undefined') {
    const styleSheet = document.createElement('style');
    styleSheet.textContent = `
    @keyframes pulse-error {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.02); }
    }
    @keyframes scroll-text {
      0% { transform: translateX(100%); }
      100% { transform: translateX(-100%); }
    }
  `;
    document.head.appendChild(styleSheet);
}
