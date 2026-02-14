// @panel: CabinetHighScoresPanel
// @role: Cabinet-wide lifetime high scores display
// @owner: Scorekeeper Sam (separate from Tournaments)
// @features: filter-by-game, search, sort-toggle
// @data-source: Powered by high_scores_index.json via /api/local/scorekeeper/highscores/cabinet

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

// API base URL - use gateway for consistent routing
const API_BASE = window.location.port === '5173'
    ? 'http://localhost:8787'
    : '';

/**
 * Fetch cabinet high scores from the backend.
 * Returns games array and a flattened scores array.
 */
async function fetchCabinetHighScores() {
    const response = await fetch(`${API_BASE}/api/local/scorekeeper/highscores/cabinet`, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'x-panel': 'scorekeeper'
        }
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || errorData.error || `HTTP ${response.status}`);
    }

    const data = await response.json();

    const flatScores = [];
    let scoreIndex = 0;

    for (const game of (data.games || [])) {
        for (const scoreEntry of (game.top_scores || [])) {
            flatScores.push({
                id: `score-${scoreIndex++}`,
                gameId: game.game_id || game.game_title || `game-${scoreIndex}`,
                gameTitle: game.game_title || 'Unknown',
                system: game.system || null,
                player: scoreEntry.player || 'Unknown',
                score: scoreEntry.score || 0,
                achievedAt: scoreEntry.timestamp || null
            });
        }
    }

    return {
        games: data.games || [],
        scores: flatScores,
        lastUpdated: data.last_updated,
        gameCount: data.game_count || 0
    };
}

export default function CabinetHighScoresPanel() {
    const navigate = useNavigate();
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [scores, setScores] = useState([]);
    const [games, setGames] = useState([]);
    const [lastUpdated, setLastUpdated] = useState(null);
    const [selectedGame, setSelectedGame] = useState('All games');
    const [searchTerm, setSearchTerm] = useState('');
    const [sortMode, setSortMode] = useState('scoreDesc');
    const mountedRef = useRef(true);
    const refreshInFlightRef = useRef(false);

    const refreshScores = async ({ showLoading = false, clearOnError = false } = {}) => {
        if (refreshInFlightRef.current) return;
        refreshInFlightRef.current = true;
        if (showLoading) {
            setLoading(true);
        }
        try {
            const result = await fetchCabinetHighScores();
            if (!mountedRef.current) return;
            setScores(result.scores);
            setGames(result.games);
            setLastUpdated(result.lastUpdated);
            setError(null);
        } catch (err) {
            console.error('[CabinetHighScores] Failed to load:', err);
            if (!mountedRef.current) return;
            setError(err.message || 'Failed to load high scores');
            if (clearOnError) {
                setScores([]);
                setGames([]);
            }
        } finally {
            if (mountedRef.current) {
                setLoading(false);
            }
            refreshInFlightRef.current = false;
        }
    };

    useEffect(() => {
        refreshScores({ showLoading: true, clearOnError: true });
        return () => {
            mountedRef.current = false;
        };
    }, []);

    useEffect(() => {
        const isDev = window.location.port === '5173';
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const wsUrl = isDev
            ? 'ws://localhost:8787/scorekeeper/ws'
            : `${proto}://${window.location.host}/scorekeeper/ws`;

        let ws;
        try {
            ws = new WebSocket(wsUrl);
        } catch (err) {
            console.warn('[CabinetHighScores] WebSocket unavailable:', err);
        }

        if (ws) {
            ws.onmessage = (ev) => {
                try {
                    const msg = JSON.parse(ev.data);
                    if (msg?.type === 'score_record' || msg?.type === 'score_updated') {
                        refreshScores();
                    }
                } catch (err) {
                    console.warn('[CabinetHighScores] WebSocket message parse failed:', err);
                }
            };
        }

        const intervalId = setInterval(() => {
            refreshScores();
        }, 10000);

        return () => {
            clearInterval(intervalId);
            if (ws) {
                try {
                    ws.close();
                } catch { }
            }
        };
    }, []);

    const uniqueGames = useMemo(() => {
        const gameTitles = [...new Set(scores.map(s => s.gameTitle))].sort();
        return ['All games', ...gameTitles];
    }, [scores]);

    const visibleScores = useMemo(() => {
        let filtered = scores;

        if (selectedGame !== 'All games') {
            filtered = filtered.filter(s => s.gameTitle === selectedGame);
        }

        if (searchTerm.trim()) {
            const term = searchTerm.toLowerCase();
            filtered = filtered.filter(s =>
                s.gameTitle.toLowerCase().includes(term) ||
                s.player.toLowerCase().includes(term)
            );
        }

        const sorted = [...filtered];
        if (sortMode === 'scoreDesc') {
            sorted.sort((a, b) => b.score - a.score);
        } else {
            sorted.sort((a, b) => new Date(a.achievedAt || 0) - new Date(b.achievedAt || 0));
        }

        return sorted;
    }, [scores, selectedGame, searchTerm, sortMode]);

    const formatDate = (isoString) => {
        if (!isoString) return '—';
        const d = new Date(isoString);
        return isNaN(d.getTime()) ? '—' : d.toISOString().split('T')[0];
    };

    const formatScore = (score) => {
        return score.toLocaleString();
    };

    const clearFilters = () => {
        setSelectedGame('All games');
        setSearchTerm('');
    };

    const toggleSort = () => {
        setSortMode(prev => prev === 'scoreDesc' ? 'dateAsc' : 'scoreDesc');
    };

    const handleBack = () => {
        navigate('/assistants?agent=scorekeeper');
    };

    // Styles
    const containerStyle = {
        maxWidth: '960px',
        margin: '0 auto',
        padding: '2rem',
        background: 'rgba(10, 15, 35, 0.95)',
        borderRadius: '12px',
        border: '2px solid rgba(0, 230, 255, 0.3)',
        boxShadow: '0 0 20px rgba(0, 230, 255, 0.15)',
        fontFamily: 'system-ui, -apple-system, sans-serif'
    };

    const headerTitleStyle = {
        fontSize: '2.25rem',
        fontWeight: 700,
        color: '#00e6ff',
        textTransform: 'uppercase',
        letterSpacing: '2px',
        margin: '0 0 0.5rem 0',
        textShadow: '0 0 10px rgba(0, 230, 255, 0.6)'
    };

    const backButtonStyle = {
        padding: '0.5rem 1rem',
        background: 'rgba(0, 230, 255, 0.1)',
        border: '1px solid rgba(0, 230, 255, 0.3)',
        borderRadius: '6px',
        color: '#00e6ff',
        fontSize: '0.9rem',
        cursor: 'pointer',
        marginBottom: '1.5rem',
        display: 'inline-block'
    };

    if (loading) {
        return (
            <div style={{ ...containerStyle, minHeight: '400px' }}>
                <button style={backButtonStyle} onClick={handleBack}>← Back to Sam</button>
                <div style={{ textAlign: 'center', padding: '3rem 2rem' }}>
                    <div style={{
                        fontSize: '1.25rem',
                        color: '#00e6ff',
                        marginBottom: '2rem',
                        textShadow: '0 0 10px rgba(0, 230, 255, 0.6)'
                    }}>Loading scores...</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxWidth: '800px', margin: '0 auto' }}>
                        {[1, 2, 3, 4, 5].map(i => (
                            <div key={i} style={{
                                height: '48px',
                                background: 'linear-gradient(90deg, rgba(0, 230, 255, 0.1) 0%, rgba(0, 230, 255, 0.2) 50%, rgba(0, 230, 255, 0.1) 100%)',
                                backgroundSize: '200% 100%',
                                animation: 'shimmer 1.5s infinite',
                                borderRadius: '6px',
                                border: '1px solid rgba(0, 230, 255, 0.15)'
                            }}></div>
                        ))}
                    </div>
                </div>
                <style>{`
          @keyframes shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
          }
        `}</style>
            </div>
        );
    }

    // Error state
    if (error) {
        return (
            <div style={{ ...containerStyle, minHeight: '400px' }}>
                <button style={backButtonStyle} onClick={handleBack}>← Back to Sam</button>
                <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
                    <h2 style={headerTitleStyle}>Cabinet High Scores</h2>
                </div>
                <div style={{ textAlign: 'center', padding: '3rem 2rem' }}>
                    <div style={{
                        fontSize: '3rem',
                        marginBottom: '1rem'
                    }}>⚠️</div>
                    <div style={{
                        fontSize: '1.1rem',
                        color: 'rgba(255, 100, 100, 0.9)',
                        marginBottom: '1.5rem'
                    }}>
                        {error}
                    </div>
                    <button
                        style={{
                            padding: '0.75rem 1.5rem',
                            background: 'rgba(0, 230, 255, 0.15)',
                            border: '1px solid rgba(0, 230, 255, 0.4)',
                            borderRadius: '6px',
                            color: '#00e6ff',
                            fontSize: '1rem',
                            fontWeight: 600,
                            cursor: 'pointer'
                        }}
                        onClick={() => window.location.reload()}
                    >
                        Retry
                    </button>
                </div>
            </div>
        );
    }

    if (scores.length === 0) {
        return (
            <div style={containerStyle}>
                <button style={backButtonStyle} onClick={handleBack}>← Back to Sam</button>
                <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
                    <h2 style={headerTitleStyle}>Cabinet High Scores</h2>
                    <p style={{ fontSize: '1rem', color: 'rgba(255, 255, 255, 0.7)', margin: 0 }}>
                        Best runs across this arcade. Filter by game or player.
                    </p>
                </div>
                <div style={{ textAlign: 'center', padding: '4rem 2rem', color: 'rgba(255, 255, 255, 0.7)', fontSize: '1.1rem' }}>
                    <p>No high scores have been recorded yet. Play some games and Sam will keep track for you.</p>
                </div>
            </div>
        );
    }

    const hasNoMatches = visibleScores.length === 0;

    return (
        <div style={containerStyle}>
            {/* Back Button */}
            <button style={backButtonStyle} onClick={handleBack}>← Back to Sam</button>

            {/* Header */}
            <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
                <h2 style={headerTitleStyle}>Cabinet High Scores</h2>
                <p style={{ fontSize: '1rem', color: 'rgba(255, 255, 255, 0.7)', margin: '0 0 1rem 0' }}>
                    Best runs across this arcade. Filter by game or player.
                </p>
                {!hasNoMatches && (
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '1rem' }}>
                        <span style={{
                            display: 'inline-block',
                            background: 'rgba(0, 230, 255, 0.15)',
                            border: '1px solid rgba(0, 230, 255, 0.4)',
                            color: '#00e6ff',
                            padding: '0.25rem 0.75rem',
                            borderRadius: '16px',
                            fontSize: '0.875rem',
                            fontWeight: 600
                        }}>{visibleScores.length} entries</span>
                    </div>
                )}
            </div>

            {/* Filters */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '1rem',
                marginBottom: '1.5rem',
                flexWrap: 'wrap'
            }}>
                <div style={{ display: 'flex', gap: '1rem', flex: 1, minWidth: '300px' }}>
                    <select
                        style={{
                            padding: '0.625rem 1rem',
                            background: 'rgba(20, 30, 60, 0.8)',
                            border: '1px solid rgba(0, 230, 255, 0.3)',
                            borderRadius: '6px',
                            color: '#fff',
                            fontSize: '0.95rem',
                            minWidth: '200px',
                            cursor: 'pointer'
                        }}
                        value={selectedGame}
                        onChange={(e) => setSelectedGame(e.target.value)}
                    >
                        {uniqueGames.map(game => (
                            <option key={game} value={game}>{game}</option>
                        ))}
                    </select>

                    <input
                        type="text"
                        style={{
                            padding: '0.625rem 1rem',
                            background: 'rgba(20, 30, 60, 0.8)',
                            border: '1px solid rgba(0, 230, 255, 0.3)',
                            borderRadius: '6px',
                            color: '#fff',
                            fontSize: '0.95rem',
                            flex: 1,
                            minWidth: '200px'
                        }}
                        placeholder="Search by game or player"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                </div>

                <button
                    style={{
                        padding: '0.625rem 1.25rem',
                        background: 'rgba(0, 230, 255, 0.15)',
                        border: '1px solid rgba(0, 230, 255, 0.4)',
                        borderRadius: '6px',
                        color: '#00e6ff',
                        fontSize: '0.9rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap'
                    }}
                    onClick={toggleSort}
                >
                    Sort: {sortMode === 'scoreDesc' ? 'Highest score' : 'Oldest first'}
                </button>
            </div>

            {/* Table or Empty */}
            {hasNoMatches ? (
                <div style={{ textAlign: 'center', padding: '4rem 2rem', color: 'rgba(255, 255, 255, 0.7)', fontSize: '1.1rem' }}>
                    <p style={{ margin: '0 0 1.5rem 0' }}>No matches. Try a different game or player name.</p>
                    <button
                        style={{
                            padding: '0.75rem 1.5rem',
                            background: 'rgba(0, 230, 255, 0.15)',
                            border: '1px solid rgba(0, 230, 255, 0.4)',
                            borderRadius: '6px',
                            color: '#00e6ff',
                            fontSize: '1rem',
                            fontWeight: 600,
                            cursor: 'pointer'
                        }}
                        onClick={clearFilters}
                    >
                        Clear filters
                    </button>
                </div>
            ) : (
                <div style={{
                    overflowX: 'auto',
                    borderRadius: '8px',
                    border: '1px solid rgba(0, 230, 255, 0.2)'
                }}>
                    <table style={{
                        width: '100%',
                        borderCollapse: 'collapse',
                        background: 'rgba(15, 20, 40, 0.6)'
                    }}>
                        <thead style={{
                            background: 'rgba(0, 230, 255, 0.1)',
                            borderBottom: '2px solid rgba(0, 230, 255, 0.4)'
                        }}>
                            <tr>
                                <th style={{
                                    padding: '0.875rem 1rem',
                                    textAlign: 'center',
                                    fontSize: '0.85rem',
                                    fontWeight: 700,
                                    color: '#00e6ff',
                                    textTransform: 'uppercase',
                                    letterSpacing: '1px',
                                    width: '60px'
                                }}>#</th>
                                <th style={{
                                    padding: '0.875rem 1rem',
                                    textAlign: 'left',
                                    fontSize: '0.85rem',
                                    fontWeight: 700,
                                    color: '#00e6ff',
                                    textTransform: 'uppercase',
                                    letterSpacing: '1px'
                                }}>Game</th>
                                <th style={{
                                    padding: '0.875rem 1rem',
                                    textAlign: 'left',
                                    fontSize: '0.85rem',
                                    fontWeight: 700,
                                    color: '#00e6ff',
                                    textTransform: 'uppercase',
                                    letterSpacing: '1px'
                                }}>Player</th>
                                <th style={{
                                    padding: '0.875rem 1rem',
                                    textAlign: 'right',
                                    fontSize: '0.85rem',
                                    fontWeight: 700,
                                    color: '#00e6ff',
                                    textTransform: 'uppercase',
                                    letterSpacing: '1px'
                                }}>Score</th>
                                <th style={{
                                    padding: '0.875rem 1rem',
                                    textAlign: 'center',
                                    fontSize: '0.85rem',
                                    fontWeight: 700,
                                    color: '#00e6ff',
                                    textTransform: 'uppercase',
                                    letterSpacing: '1px',
                                    width: '120px'
                                }}>Date</th>
                            </tr>
                        </thead>
                        <tbody>
                            {visibleScores.map((score, index) => (
                                <tr
                                    key={score.id}
                                    style={{
                                        borderBottom: '1px solid rgba(0, 230, 255, 0.1)',
                                        transition: 'all 0.2s ease'
                                    }}
                                    onMouseEnter={(e) => {
                                        e.currentTarget.style.background = 'rgba(0, 230, 255, 0.08)';
                                        e.currentTarget.style.boxShadow = 'inset 0 0 15px rgba(0, 230, 255, 0.1)';
                                    }}
                                    onMouseLeave={(e) => {
                                        e.currentTarget.style.background = 'transparent';
                                        e.currentTarget.style.boxShadow = 'none';
                                    }}
                                >
                                    <td style={{
                                        padding: '0.875rem 1rem',
                                        textAlign: 'center',
                                        fontWeight: 700,
                                        color: 'rgba(0, 230, 255, 0.7)',
                                        fontSize: '0.95rem'
                                    }}>{index + 1}</td>
                                    <td
                                        title={score.gameTitle}
                                        style={{
                                            padding: '0.875rem 1rem',
                                            color: 'rgba(255, 255, 255, 0.9)',
                                            fontSize: '0.95rem',
                                            maxWidth: '300px',
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis',
                                            whiteSpace: 'nowrap'
                                        }}
                                    >{score.gameTitle}</td>
                                    <td style={{
                                        padding: '0.875rem 1rem',
                                        fontWeight: 600,
                                        color: '#fff',
                                        fontSize: '0.95rem'
                                    }}>{score.player}</td>
                                    <td style={{
                                        padding: '0.875rem 1rem',
                                        textAlign: 'right',
                                        fontWeight: 700,
                                        color: '#00e6ff',
                                        fontFamily: "'Courier New', monospace",
                                        fontSize: '0.95rem'
                                    }}>{formatScore(score.score)}</td>
                                    <td style={{
                                        padding: '0.875rem 1rem',
                                        textAlign: 'center',
                                        color: 'rgba(255, 255, 255, 0.6)',
                                        fontSize: '0.9rem'
                                    }}>{formatDate(score.achievedAt)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
