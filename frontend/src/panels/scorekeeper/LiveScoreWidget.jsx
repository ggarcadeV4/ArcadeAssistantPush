/**
 * LiveScoreWidget — Real-time MAME score display
 *
 * Polls GET /api/scores/live every 3 seconds.
 * Shows current ROM, live score, and freshness indicator.
 * Collapses to a compact strip when no game is running.
 */
import { useState, useEffect, useRef } from 'react'
import { getLiveScore } from '../../services/scorekeeperClient'

export default function LiveScoreWidget() {
    const [data, setData] = useState(null)
    const timerRef = useRef(null)

    useEffect(() => {
        let mounted = true

        const poll = async () => {
            try {
                const result = await getLiveScore()
                if (mounted) setData(result)
            } catch {
                if (mounted) setData(null)
            }
        }

        poll()
        timerRef.current = setInterval(poll, 3000)
        return () => {
            mounted = false
            clearInterval(timerRef.current)
        }
    }, [])

    const isLive = data?.status === 'live'
    const isStale = data?.status === 'stale'
    const hasScore = isLive || isStale

    const formatScore = (val) => {
        if (val == null) return '--'
        return Number(val).toLocaleString()
    }

    return (
        <div className={`live-score-widget ${isLive ? 'live' : isStale ? 'stale' : 'idle'}`}>
            <div className="live-score-header">
                <span className={`live-dot ${isLive ? 'active' : ''}`} />
                <span className="live-label">
                    {isLive ? 'LIVE SCORE' : isStale ? 'LAST SCORE' : 'AWAITING GAME'}
                </span>
            </div>
            {hasScore ? (
                <div className="live-score-body">
                    <div className="live-rom">{data.rom || 'Unknown'}</div>
                    <div className="live-score-value">{formatScore(data.score)}</div>
                    <div className="live-meta">
                        Player {data.player || 1}
                        {data.age_seconds != null && (
                            <span className="live-age"> · {data.age_seconds < 60 ? `${Math.round(data.age_seconds)}s ago` : `${Math.round(data.age_seconds / 60)}m ago`}</span>
                        )}
                    </div>
                </div>
            ) : (
                <div className="live-score-empty">
                    <span className="material-symbols-outlined" style={{ fontSize: '1.5rem', opacity: 0.3 }}>sports_esports</span>
                    <span>Start a MAME game to see live scores</span>
                </div>
            )}
        </div>
    )
}
