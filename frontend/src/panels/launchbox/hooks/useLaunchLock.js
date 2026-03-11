import { useCallback, useState } from 'react'

const DEFAULT_LOCK_KEY = 'launchbox:lock'
const DEFAULT_LOCK_MS = 5000

const readStoredLock = (storageKey) => {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return 0
    const raw = window.localStorage.getItem(storageKey)
    const until = Number(raw || 0)
    return Number.isFinite(until) ? until : 0
  } catch {
    return 0
  }
}

export default function useLaunchLock({ storageKey = DEFAULT_LOCK_KEY, lockMs = DEFAULT_LOCK_MS } = {}) {
  const [lockUntil, setLockUntil] = useState(() => readStoredLock(storageKey))

  const acquireLock = useCallback(() => {
    const until = Date.now() + lockMs
    setLockUntil(until)
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(storageKey, until.toString())
      }
    } catch { }
  }, [lockMs, storageKey])

  const releaseLock = useCallback(() => {
    setLockUntil(0)
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.removeItem(storageKey)
      }
    } catch { }
  }, [storageKey])

  return {
    lockUntil,
    isLockActive: Date.now() < lockUntil,
    acquireLock,
    releaseLock
  }
}