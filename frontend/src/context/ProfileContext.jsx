import React, { createContext, useContext, useCallback, useEffect, useMemo, useState, useRef } from 'react'
import { getProfile, getPrimaryProfile } from '../services/profileClient'
import { getGatewayHost } from '../services/gateway'

const ProfileContext = createContext({
  profile: null,
  currentUser: 'Guest',
  loading: true,
  error: null,
  refreshProfile: async () => { },
  setProfileSnapshot: () => { }
})

export function ProfileProvider({ children }) {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const wsRef = useRef(null)
  const reconnectRef = useRef(null)

  const refreshProfile = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const [response, primaryResponse] = await Promise.all([
        getProfile().catch(() => null),
        getPrimaryProfile().catch(() => null)
      ])
      const profileData = response?.profile || null
      const primaryData = primaryResponse?.profile || null
      if (profileData && Object.keys(profileData).length > 0) {
        const merged = { ...profileData }
        if (primaryData) {
          if (!merged.displayName && primaryData.display_name) merged.displayName = primaryData.display_name
          if (!merged.initials && primaryData.initials) merged.initials = primaryData.initials
          if (!merged.userId && primaryData.user_id) merged.userId = primaryData.user_id
          if (typeof merged.consent !== 'boolean' && typeof primaryData.consent === 'boolean') merged.consent = primaryData.consent
          if (!merged.preferences) merged.preferences = {}
          if (!merged.preferences.playerPosition && primaryData.player_position) {
            merged.preferences.playerPosition = primaryData.player_position
          }
        }
        setProfile(merged)
      } else if (primaryData && Object.keys(primaryData).length > 0) {
        setProfile({
          displayName: primaryData.display_name || 'Guest',
          initials: primaryData.initials || '',
          userId: primaryData.user_id || 'guest',
          consent: typeof primaryData.consent === 'boolean' ? primaryData.consent : !!primaryData.consent_active,
          avatar: '',
          favoriteColor: null,
          preferences: {
            voiceAssignments: primaryData.voice_prefs || {},
            vocabulary: Array.isArray(primaryData.vocabulary) ? primaryData.vocabulary.join('\n') : '',
            players: [],
            playerPosition: primaryData.player_position || null
          },
          lastUpdated: primaryData.last_updated || null
        })
      } else {
        setProfile(null)
      }
    } catch (err) {
      console.error('[ProfileContext] Failed to refresh profile', err)
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshProfile()
  }, [refreshProfile])

  useEffect(() => {
    if (typeof window === 'undefined') return () => { }

    // Dynamic URL: use window.location.host to avoid 127.0.0.1 vs localhost mismatch
    const isSecure = window.location.protocol === 'https:'
    const host = getGatewayHost()
    const scheme = isSecure ? 'wss' : 'ws'
    const wsUrl = `${scheme}://${host}/ws/session`

    let alive = true
    let backoff = 2000
    const MAX_BACKOFF = 30000

    const connect = () => {
      if (!alive) return
      try {
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => {
          backoff = 2000
        }

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data || '{}')
            if (msg.type === 'profile_updated' || msg.type === 'session_started' || msg.type === 'session_ended') {
              refreshProfile()
            }
          } catch { }
        }

        ws.onclose = () => {
          if (!alive) return
          reconnectRef.current = setTimeout(connect, backoff)
          backoff = Math.min(backoff * 2, MAX_BACKOFF)
        }

        ws.onerror = () => {
          // Silently close — onclose handles reconnect
          try { ws.close() } catch { }
        }
      } catch {
        reconnectRef.current = setTimeout(connect, backoff)
        backoff = Math.min(backoff * 2, MAX_BACKOFF)
      }
    }

    connect()

    return () => {
      alive = false
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current)
        reconnectRef.current = null
      }
      if (wsRef.current) {
        try { wsRef.current.close() } catch { }
        wsRef.current = null
      }
    }
  }, [refreshProfile])

  const currentUser = useMemo(() => (profile?.displayName || 'Guest'), [profile])

  const value = useMemo(() => ({
    profile,
    currentUser,
    loading,
    error,
    refreshProfile,
    setProfileSnapshot: setProfile
  }), [profile, currentUser, loading, error, refreshProfile])

  return (
    <ProfileContext.Provider value={value}>
      {children}
    </ProfileContext.Provider>
  )
}

export function useProfileContext() {
  return useContext(ProfileContext)
}
