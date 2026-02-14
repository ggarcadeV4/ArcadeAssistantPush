// @panel: MarqueeDisplayV2
// @role: Dynamic marquee display with video + image loop
// @data: Receives game info via polling/WebSocket, displays video clip then static marquee art
// @version: 2.0

import React, { useEffect, useState, useRef, useCallback } from 'react';

const API_BASE = window.location.port === '5173'
  ? 'http://localhost:8787'
  : '';

// Display phases
const PHASE = {
  LOADING: 'loading',
  VIDEO: 'video',
  IMAGE: 'image',
  TEXT: 'text',  // Fallback when no media found
  IDLE: 'idle',
  ERROR: 'error',
};

export default function MarqueeDisplayV2() {
  // Current game state
  const [currentGame, setCurrentGame] = useState(null);
  const [media, setMedia] = useState({ videoUrl: null, imageUrl: null });
  const [phase, setPhase] = useState(PHASE.IDLE);
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(null);

  // Refs for video element
  const videoRef = useRef(null);
  const imageTimerRef = useRef(null);

  // Config: timing for display phases
  const VIDEO_START_DELAY = 2000; // 2 seconds before video starts (allows quick scrolling)
  const IMAGE_AFTER_VIDEO_DURATION = 5000; // 5 seconds of image after video ends before looping
  
  // Ref for video start delay timer
  const videoDelayTimerRef = useRef(null);

  // Load marquee config on mount
  useEffect(() => {
    async function loadConfig() {
      try {
        const res = await fetch(`${API_BASE}/api/local/marquee/config`);
        if (res.ok) {
          const data = await res.json();
          setConfig(data);
        }
      } catch (e) {
        console.error('[MarqueeV2] Failed to load config:', e);
      }
    }
    loadConfig();
  }, []);

  // Poll for preview state (supports scroll preview + video on select)
  useEffect(() => {
    let cancelled = false;

    async function pollPreviewState() {
      try {
        const res = await fetch(`${API_BASE}/api/local/marquee/preview`);
        if (res.ok && !cancelled) {
          const data = await res.json();
          // Only update if game changed
          if (data.title !== currentGame?.title || data.mode !== currentGame?.mode) {
            setCurrentGame(data);
          }
        }
      } catch (e) {
        // Silent fail on poll — will retry
      }
    }

    pollPreviewState();
    const interval = setInterval(pollPreviewState, 500); // Faster polling for scroll responsiveness
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [currentGame?.title, currentGame?.mode]);

  // When game changes, fetch media URLs
  useEffect(() => {
    if (!currentGame?.game_id) {
      setPhase(PHASE.IDLE);
      setMedia({ videoUrl: null, imageUrl: null });
      return;
    }

    let cancelled = false;

    async function fetchMedia() {
      setPhase(PHASE.LOADING);
      try {
        // Use title for file matching (files are named by title, not UUID)
        const params = new URLSearchParams({
          game_id: currentGame.title || currentGame.game_id,
          platform: currentGame.platform || 'Arcade',
        });
        const res = await fetch(`${API_BASE}/api/local/marquee/media?${params}`);
        if (res.ok && !cancelled) {
          const data = await res.json();
          // Prepend API_BASE to relative URLs for dev mode
          setMedia({
            videoUrl: data.video_url ? `${API_BASE}${data.video_url}` : null,
            imageUrl: data.image_url ? `${API_BASE}${data.image_url}` : null,
          });
          // Start with IMAGE first (instant feedback while scrolling)
          // Video will start after a delay if user lingers
          if (data.image_url) {
            setPhase(PHASE.IMAGE);
          } else if (data.video_url) {
            // No image available, go straight to video
            setPhase(PHASE.VIDEO);
          } else {
            // No media found - use text fallback (never blank!)
            setPhase(PHASE.TEXT);
          }
        }
      } catch (e) {
        console.error('[MarqueeV2] Failed to fetch media:', e);
        if (!cancelled) {
          // On error, show text fallback instead of error
          setPhase(PHASE.TEXT);
        }
      }
    }

    fetchMedia();
    return () => { cancelled = true; };
  }, [currentGame?.game_id, currentGame?.platform]);

  // Handle video end — transition back to image phase, then loop
  const handleVideoEnded = useCallback(() => {
    if (media.imageUrl) {
      // Show image again after video ends
      setPhase(PHASE.IMAGE);
    } else if (media.videoUrl) {
      // No image, loop video immediately
      if (videoRef.current) {
        videoRef.current.currentTime = 0;
        videoRef.current.play();
      }
    }
  }, [media.imageUrl, media.videoUrl]);

  // Handle video error — fall back to image
  const handleVideoError = useCallback(() => {
    console.warn('[MarqueeV2] Video failed to load, falling back to image');
    if (media.imageUrl) {
      setPhase(PHASE.IMAGE);
    } else {
      setPhase(PHASE.IDLE);
    }
  }, [media.imageUrl]);

  // Image phase timer — after delay, start video (only in "video" mode)
  useEffect(() => {
    // Clear any existing timer when phase or game changes
    if (videoDelayTimerRef.current) {
      clearTimeout(videoDelayTimerRef.current);
      videoDelayTimerRef.current = null;
    }
    if (imageTimerRef.current) {
      clearTimeout(imageTimerRef.current);
      imageTimerRef.current = null;
    }
    
    // Only transition to video if mode is "video" (game selected/launched)
    // In "image" mode (scrolling), stay on image indefinitely
    const isVideoMode = currentGame?.mode === 'video';
    
    if (phase === PHASE.IMAGE && media.videoUrl && isVideoMode) {
      // Determine delay: shorter on first show, longer after video ends
      const isAfterVideo = videoRef.current && videoRef.current.currentTime > 0;
      const delay = isAfterVideo ? IMAGE_AFTER_VIDEO_DURATION : VIDEO_START_DELAY;
      
      imageTimerRef.current = setTimeout(() => {
        setPhase(PHASE.VIDEO);
      }, delay);

      return () => {
        if (imageTimerRef.current) {
          clearTimeout(imageTimerRef.current);
        }
      };
    }
  }, [phase, media.videoUrl, currentGame?.mode]);

  // Auto-play video when phase changes to VIDEO
  useEffect(() => {
    if (phase === PHASE.VIDEO && videoRef.current && media.videoUrl) {
      videoRef.current.currentTime = 0;
      // Use requestAnimationFrame to avoid focus stealing during play()
      requestAnimationFrame(() => {
        if (videoRef.current) {
          videoRef.current.play().catch(e => {
            console.warn('[MarqueeV2] Autoplay blocked:', e);
            // Browser blocked autoplay, fall back to image
            if (media.imageUrl) {
              setPhase(PHASE.IMAGE);
            }
          });
        }
      });
    }
  }, [phase, media.videoUrl, media.imageUrl]);

  // Prevent this window from stealing focus
  useEffect(() => {
    const preventFocusSteal = (e) => {
      // Don't prevent default - just don't request focus
    };
    // Blur this window if it gains focus unexpectedly
    const handleFocus = () => {
      // If a game is active (phase not IDLE), don't let this window steal focus
      if (phase !== PHASE.IDLE && document.hasFocus()) {
        window.blur();
      }
    };
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [phase]);

  // Render idle state
  if (phase === PHASE.IDLE || !currentGame) {
    return (
      <div style={styles.container}>
        <div style={styles.idleContent}>
          <div style={styles.idleTitle}>G&G ARCADE</div>
          <div style={styles.idleSubtitle}>Select a game to begin</div>
        </div>
      </div>
    );
  }

  // Render loading state
  if (phase === PHASE.LOADING) {
    return (
      <div style={styles.container}>
        <div style={styles.loadingContent}>
          <div style={styles.spinner}></div>
          <div style={styles.loadingText}>Loading {currentGame.title}...</div>
        </div>
      </div>
    );
  }

  // Render error state
  if (phase === PHASE.ERROR) {
    return (
      <div style={styles.container}>
        <div style={styles.errorContent}>
          <div style={styles.errorText}>{error || 'Media unavailable'}</div>
          <div style={styles.gameTitle}>{currentGame.title}</div>
        </div>
      </div>
    );
  }

  // Render text fallback state (when no marquee art exists)
  if (phase === PHASE.TEXT) {
    return (
      <div style={styles.container}>
        <div style={styles.textFallback}>
          {/* Animated gradient background */}
          <div style={styles.textGradientBg}></div>
          
          {/* Platform badge */}
          {currentGame.platform && (
            <div style={styles.textPlatformBadge}>{currentGame.platform}</div>
          )}
          
          {/* Game title - large, styled */}
          <div style={styles.textGameTitle}>{currentGame.title}</div>
          
          {/* Decorative line */}
          <div style={styles.textDivider}></div>
          
          {/* Arcade branding */}
          <div style={styles.textBranding}>ARCADE ASSISTANT</div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* Video layer — always mounted but hidden when not in video phase */}
      {media.videoUrl && (
        <video
          ref={videoRef}
          src={media.videoUrl}
          style={{
            ...styles.media,
            opacity: phase === PHASE.VIDEO ? 1 : 0,
            zIndex: phase === PHASE.VIDEO ? 2 : 1,
          }}
          muted
          playsInline
          onEnded={handleVideoEnded}
          onError={handleVideoError}
        />
      )}

      {/* Image layer — always mounted but hidden when not in image phase */}
      {media.imageUrl && (
        <img
          src={media.imageUrl}
          alt={currentGame.title}
          style={{
            ...styles.media,
            opacity: phase === PHASE.IMAGE ? 1 : 0,
            zIndex: phase === PHASE.IMAGE ? 2 : 1,
          }}
        />
      )}

      {/* Game info overlay (subtle, bottom of screen) */}
      <div style={styles.overlay}>
        <div style={styles.overlayTitle}>{currentGame.title}</div>
        {currentGame.platform && (
          <div style={styles.overlayPlatform}>{currentGame.platform}</div>
        )}
      </div>
    </div>
  );
}

// Styles
const styles = {
  container: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100vw',
    height: '100vh',
    backgroundColor: '#000',
    overflow: 'hidden',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  media: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    objectFit: 'contain',
    transition: 'opacity 0.5s ease-in-out',
  },
  overlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    padding: '20px 30px',
    background: 'linear-gradient(transparent, rgba(0,0,0,0.85))',
    zIndex: 10,
  },
  overlayTitle: {
    fontSize: '24px',
    fontWeight: 700,
    color: '#fff',
    textShadow: '0 2px 8px rgba(0,0,0,0.8)',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  overlayPlatform: {
    fontSize: '14px',
    color: 'rgba(255,255,255,0.7)',
    marginTop: '4px',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  idleContent: {
    textAlign: 'center',
  },
  idleTitle: {
    fontSize: '48px',
    fontWeight: 800,
    color: '#6af7ff',
    textShadow: '0 0 30px rgba(106,247,255,0.5)',
    letterSpacing: '8px',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  idleSubtitle: {
    fontSize: '18px',
    color: 'rgba(255,255,255,0.5)',
    marginTop: '16px',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  loadingContent: {
    textAlign: 'center',
  },
  spinner: {
    width: '48px',
    height: '48px',
    border: '4px solid rgba(106,247,255,0.2)',
    borderTopColor: '#6af7ff',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
    margin: '0 auto 20px',
  },
  loadingText: {
    fontSize: '18px',
    color: '#6af7ff',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  errorContent: {
    textAlign: 'center',
  },
  errorText: {
    fontSize: '16px',
    color: '#ff6b6b',
    marginBottom: '12px',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  gameTitle: {
    fontSize: '28px',
    fontWeight: 700,
    color: '#fff',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  // Text fallback styles (when no marquee art exists)
  textFallback: {
    position: 'relative',
    width: '100%',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center',
    padding: '40px',
    overflow: 'hidden',
  },
  textGradientBg: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
    animation: 'gradientShift 8s ease infinite',
    zIndex: 0,
  },
  textPlatformBadge: {
    position: 'relative',
    zIndex: 1,
    fontSize: '14px',
    fontWeight: 600,
    color: '#6af7ff',
    textTransform: 'uppercase',
    letterSpacing: '4px',
    padding: '8px 24px',
    border: '2px solid rgba(106,247,255,0.4)',
    borderRadius: '4px',
    marginBottom: '24px',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  textGameTitle: {
    position: 'relative',
    zIndex: 1,
    fontSize: '56px',
    fontWeight: 800,
    color: '#ffffff',
    textShadow: '0 0 40px rgba(106,247,255,0.6), 0 4px 20px rgba(0,0,0,0.8)',
    letterSpacing: '2px',
    lineHeight: 1.1,
    maxWidth: '90%',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
  textDivider: {
    position: 'relative',
    zIndex: 1,
    width: '120px',
    height: '3px',
    background: 'linear-gradient(90deg, transparent, #6af7ff, transparent)',
    margin: '24px 0',
    borderRadius: '2px',
  },
  textBranding: {
    position: 'relative',
    zIndex: 1,
    fontSize: '12px',
    fontWeight: 500,
    color: 'rgba(255,255,255,0.4)',
    letterSpacing: '6px',
    textTransform: 'uppercase',
    fontFamily: "'Inter', system-ui, sans-serif",
  },
};

// Add keyframes for spinner and gradient (injected once)
if (typeof document !== 'undefined') {
  const styleSheet = document.createElement('style');
  styleSheet.textContent = `
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    @keyframes gradientShift {
      0%, 100% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
    }
  `;
  document.head.appendChild(styleSheet);
}
