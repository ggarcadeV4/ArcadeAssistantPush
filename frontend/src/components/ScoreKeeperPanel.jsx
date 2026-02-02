// frontend/src/components/ScoreKeeperPanel.jsx
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import PropTypes from 'prop-types';
import PanelShell from '../panels/_kit/PanelShell';
import './ScoreKeeperPanel.css';

// WebSocket manager extracted outside component for persistence
class ScoreKeeperWebSocket {
  constructor() {
    this.ws = null;
    this.listeners = new Set();
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    try {
      this.ws = new WebSocket('ws://localhost:8787/scorekeeper/ws');

      this.ws.onopen = () => {
        console.log('ScoreKeeper WebSocket connected');
        this.notifyListeners({ type: 'connected' });
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.notifyListeners(data);
        } catch (err) {
          console.error('WebSocket message parse error:', err);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.notifyListeners({ type: 'error', message: 'Connection error' });
      };

      this.ws.onclose = () => {
        console.log('ScoreKeeper WebSocket closed');
        this.notifyListeners({ type: 'disconnected' });
        setTimeout(() => this.connect(), 3000); // Auto-reconnect
      };
    } catch (err) {
      console.error('WebSocket connection failed:', err);
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(data) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  addListener(callback) {
    this.listeners.add(callback);
  }

  removeListener(callback) {
    this.listeners.delete(callback);
  }

  notifyListeners(data) {
    this.listeners.forEach(callback => callback(data));
  }
}

const wsManager = new ScoreKeeperWebSocket();

// Memoized bracket match component for performance
const BracketMatch = React.memo(({ match, onAdvanceWinner }) => {
  return (
    <div className={`bracket-match ${match.isActive ? 'active' : ''}`}>
      <div
        className={`bracket-player ${match.winner === match.player1 ? 'winner' : ''}`}
        onClick={() => match.isActive && onAdvanceWinner(match.id, match.player1)}
      >
        <span className="player-name">{match.player1 || 'TBD'}</span>
        {match.score1 && <span className="player-score">{match.score1}</span>}
      </div>
      <div
        className={`bracket-player ${match.winner === match.player2 ? 'winner' : ''}`}
        onClick={() => match.isActive && onAdvanceWinner(match.id, match.player2)}
      >
        <span className="player-name">{match.player2 || 'TBD'}</span>
        {match.score2 && <span className="player-score">{match.score2}</span>}
      </div>
    </div>
  );
});

BracketMatch.propTypes = {
  match: PropTypes.shape({
    id: PropTypes.string.isRequired,
    player1: PropTypes.string,
    player2: PropTypes.string,
    score1: PropTypes.number,
    score2: PropTypes.number,
    winner: PropTypes.string,
    isActive: PropTypes.bool
  }).isRequired,
  onAdvanceWinner: PropTypes.func.isRequired
};

function ScoreKeeperPanel() {
  // State management
  const [bracket, setBracket] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [currentGame, setCurrentGame] = useState('');
  const [playerName, setPlayerName] = useState('');
  const [playerScore, setPlayerScore] = useState('');
  const [tournamentPlayers, setTournamentPlayers] = useState('');
  const [selectedGame, setSelectedGame] = useState('pacman');
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [currentRound, setCurrentRound] = useState(1);
  const [totalRounds, setTotalRounds] = useState(3);

  const voiceInputRef = useRef(null);

  // WebSocket message handler
  const handleWebSocketMessage = useCallback((data) => {
    switch (data.type) {
      case 'connected':
        setIsConnected(true);
        break;
      case 'disconnected':
        setIsConnected(false);
        break;
      case 'bracket_update':
        setBracket(data.bracket);
        if (data.currentRound) setCurrentRound(data.currentRound);
        if (data.totalRounds) setTotalRounds(data.totalRounds);
        break;
      case 'score_updated':
        fetchLeaderboard(selectedGame);
        showSuccess('Score updated successfully!');
        break;
      case 'error':
        showError(data.message || 'WebSocket error occurred');
        break;
      default:
        break;
    }
  }, [selectedGame]);

  // Initialize WebSocket connection
  useEffect(() => {
    wsManager.connect();
    wsManager.addListener(handleWebSocketMessage);

    return () => {
      wsManager.removeListener(handleWebSocketMessage);
    };
  }, [handleWebSocketMessage]);

  // Fetch leaderboard data
  const fetchLeaderboard = useCallback(async (game) => {
    try {
      const response = await fetch(`/api/scorekeeper/leaderboard/${game}`);
      if (response.ok) {
        const data = await response.json();
        setLeaderboard(data.scores || []);
      }
    } catch (err) {
      console.error('Failed to fetch leaderboard:', err);
    }
  }, []);

  // Load initial leaderboard
  useEffect(() => {
    fetchLeaderboard(selectedGame);
  }, [selectedGame, fetchLeaderboard]);

  // Submit score handler with flash feedback
  const handleSubmitScore = useCallback(async () => {
    if (!currentGame || !playerName || !playerScore) {
      showError('Please fill in all fields');
      return;
    }

    try {
      // Send via WebSocket for real-time update
      wsManager.send({
        type: 'score_update',
        game: currentGame,
        player: playerName,
        score: parseInt(playerScore)
      });

      // Also POST to REST endpoint for persistence
      const response = await fetch('/api/scorekeeper/score/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          game: currentGame,
          player: playerName,
          score: parseInt(playerScore)
        })
      });

      if (response.ok) {
        showSuccess('Score submitted successfully!');
        setCurrentGame('');
        setPlayerName('');
        setPlayerScore('');
        fetchLeaderboard(selectedGame);
      } else {
        throw new Error('Failed to submit score');
      }
    } catch (err) {
      showError('Failed to submit score');
    }
  }, [currentGame, playerName, playerScore, selectedGame, fetchLeaderboard]);

  // Start tournament handler
  const handleStartTournament = useCallback(async () => {
    if (!tournamentPlayers.trim()) {
      showError('Please enter player names');
      return;
    }

    const players = tournamentPlayers.split(',').map(p => p.trim()).filter(Boolean);
    const validCounts = [4, 8, 16, 32];

    if (!validCounts.includes(players.length)) {
      showError(`Tournament requires ${validCounts.join(', ')} players (you have ${players.length})`);
      return;
    }

    try {
      const response = await fetch('/api/scorekeeper/tournament/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ players, game: selectedGame })
      });

      if (response.ok) {
        const data = await response.json();
        setBracket(data.bracket);
        showSuccess('Tournament started!');
        setTournamentPlayers('');
      } else {
        throw new Error('Failed to start tournament');
      }
    } catch (err) {
      showError('Failed to start tournament');
    }
  }, [tournamentPlayers, selectedGame]);

  // Advance winner in bracket
  const handleAdvanceWinner = useCallback((matchId, winner) => {
    wsManager.send({
      type: 'advance_winner',
      matchId,
      winner
    });
  }, []);

  // Voice input handler (F9 focus)
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (e.key === 'F9') {
        e.preventDefault();
        voiceInputRef.current?.focus();
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, []);

  // Flash message handlers
  const showError = (message) => {
    setError(message);
    setTimeout(() => setError(''), 3000);
  };

  const showSuccess = (message) => {
    setSuccess(message);
    setTimeout(() => setSuccess(''), 3000);
  };

  // Memoized leaderboard display
  const leaderboardDisplay = useMemo(() => (
    <div className="leaderboard-section">
      <h3>Leaderboard - {selectedGame.toUpperCase()}</h3>
      <table className="leaderboard-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Player</th>
            <th>Score</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody>
          {leaderboard.map((entry, index) => (
            <tr key={`${entry.player}-${entry.score}-${index}`}>
              <td className="rank">{index + 1}</td>
              <td className="player">{entry.player}</td>
              <td className="score">{entry.score.toLocaleString()}</td>
              <td className="date">{new Date(entry.date).toLocaleDateString()}</td>
            </tr>
          ))}
          {leaderboard.length === 0 && (
            <tr>
              <td colSpan="4" className="empty">No scores yet</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  ), [leaderboard, selectedGame]);

  // Render bracket visualization
  const renderBracket = () => {
    if (!bracket) return null;

    return (
      <div className="bracket-visualization">
        <h3>Tournament Bracket</h3>
        <div className="bracket-rounds">
          {bracket.rounds?.map((round, roundIndex) => (
            <div key={roundIndex} className={`bracket-round round-${roundIndex + 1}`}>
              <h4>Round {roundIndex + 1}</h4>
              {round.matches.map((match) => (
                <BracketMatch
                  key={match.id}
                  match={match}
                  onAdvanceWinner={handleAdvanceWinner}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // Header actions with voice button
  const headerActions = (
    <div className="header-actions">
      <button
        className="voice-button-header"
        onClick={() => voiceInputRef.current?.focus()}
        title="Press F9 to focus score entry"
      >
        🎤
      </button>
    </div>
  );

  return (
    <PanelShell
      title="ScoreKeeper Sam - Tournaments & High Scores"
      icon={<img src="/sam-avatar.jpeg" alt="Sam" className="panel-avatar" />}
      subtitle="Manage tournaments and track high scores"
      status={isConnected ? 'online' : 'offline'}
      headerActions={headerActions}
    >
      <div className="scorekeeper-panel">
        {/* Status bar */}
        <div className="status-bar">
          <span className="round-status">Round {currentRound} of {totalRounds}</span>
          <span className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
          </span>
        </div>

        {/* Flash messages */}
        {error && <div className="flash-message error">{error}</div>}
        {success && <div className="flash-message success">{success}</div>}

        {/* Score entry section */}
        <div className="score-entry-section">
          <h3>Submit Score</h3>
          <div className="score-form">
            <input
              type="text"
              placeholder="Game name"
              value={currentGame}
              onChange={(e) => setCurrentGame(e.target.value)}
              className="score-input"
            />
            <input
              type="text"
              placeholder="Player name"
              value={playerName}
              onChange={(e) => setPlayerName(e.target.value)}
              className="score-input"
            />
            <input
              type="number"
              placeholder="Score"
              value={playerScore}
              onChange={(e) => setPlayerScore(e.target.value)}
              className="score-input"
            />
            <button
              onClick={handleSubmitScore}
              className="submit-button"
            >
              Submit Score
            </button>
            <button
              ref={voiceInputRef}
              className="voice-button"
              title="Press F9 to focus"
            >
              🎤 Voice
            </button>
          </div>
        </div>

        {/* Tournament setup */}
        <div className="tournament-section">
          <h3>Start Tournament</h3>
          <div className="tournament-form">
            <input
              type="text"
              placeholder="Player names (comma-separated)"
              value={tournamentPlayers}
              onChange={(e) => setTournamentPlayers(e.target.value)}
              className="players-input"
            />
            <select
              value={selectedGame}
              onChange={(e) => setSelectedGame(e.target.value)}
              className="game-select"
            >
              <option value="pacman">Pac-Man</option>
              <option value="galaga">Galaga</option>
              <option value="donkeykong">Donkey Kong</option>
              <option value="streetfighter">Street Fighter</option>
            </select>
            <button
              onClick={handleStartTournament}
              className="start-button"
            >
              Start Tournament
            </button>
          </div>
        </div>

        {/* Bracket visualization */}
        {renderBracket()}

        {/* Leaderboard display */}
        {leaderboardDisplay}
      </div>
    </PanelShell>
  );
}

ScoreKeeperPanel.propTypes = {};

export default ScoreKeeperPanel;