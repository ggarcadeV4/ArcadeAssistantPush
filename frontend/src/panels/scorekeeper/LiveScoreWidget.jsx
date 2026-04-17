/**
 * LiveScoreWidget — Real-time MAME score display
 *
 * Receives score_updated events via the gateway WebSocket at /scorekeeper/ws.
 * Shows current ROM, live score, and freshness indicator.
 * Collapses to a compact strip when no game is running.
 */
import { useState, useEffect } from 'react'
import { buildGatewayWsIdentityUrl, generateCorrelationId } from '../../utils/network'

export default function LiveScoreWidget() {
    const [data, setData] = useState(null)

    useEffect(() => {
        const wsUrl = buildGatewayWsIdentityUrl('/scorekeeper/ws', {
            panel: 'live-score-widget',
            corrId: generateCorrelationId('live-score-widget')
        })

        let ws
        try {
            ws = new WebSocket(wsUrl)
        } catch (err) {
            console.warn('[LiveScoreWidget] WebSocket unavailable:', err)
        }

        if (ws) {
            ws.onmessage = (ev) => {
                try {
                    const msg = JSON.parse(ev.data)
                    if (msg?.type === 'score_updated') {
                        // Map backend broadcast shape to the render contract:
                        // {"type": "score_updated", "game": "...", "entry": {score, player, ...}}
                        setData({
                            status: 'live',
                            score: msg.entry?.score || 0,
                            player: msg.entry?.player || 'P1',
                            rom: msg.game || 'Unknown',
                            age_seconds: 0,
                        })
                    }
                } catch (err) {
                    console.warn('[LiveScoreWidget] WebSocket message parse failed:', err)
                }
            }
        }

        return () => {
            if (ws) {
                ws.close()
            }
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
