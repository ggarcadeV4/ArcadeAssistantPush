import { useCallback, useState } from 'react'

const DEFAULT_PLUGIN_STATUS = {
  available: false,
  url: 'http://127.0.0.1:9999',
  message: 'Plugin offline',
  port: 9999
}

export default function usePluginHealth({ gateway = '', cacheMs = 30000 } = {}) {
  const [lastPluginCheck, setLastPluginCheck] = useState(0)
  const [checkingPlugin, setCheckingPlugin] = useState(false)
  const [pluginStatus, setPluginStatus] = useState(null)
  const [pluginAvailable, setPluginAvailable] = useState(false)

  const checkPluginHealth = useCallback(async (forceCheck = false) => {
    const now = Date.now()
    if (!forceCheck && (now - lastPluginCheck) < cacheMs) {
      return
    }

    setCheckingPlugin(true)
    try {
      const response = await fetch(`${gateway}/api/launchbox/plugin-status`, {
        method: 'GET',
        headers: {
          'x-panel': 'launchbox',
          'Cache-Control': 'no-cache'
        },
        signal: AbortSignal.timeout(3000)
      })

      if (!response.ok) {
        throw new Error(`Plugin check failed: ${response.status}`)
      }

      const status = await response.json()
      setPluginStatus(status)
      setPluginAvailable(Boolean(status.available))
      setLastPluginCheck(now)
      console.log('[Plugin Health]', status.available ? 'Online' : 'Offline', status.message)
    } catch (error) {
      console.error('[Plugin Health] Check failed:', error)
      setPluginAvailable(false)
      setPluginStatus({
        ...DEFAULT_PLUGIN_STATUS,
        message: error?.message || DEFAULT_PLUGIN_STATUS.message
      })
      setLastPluginCheck(now)
    } finally {
      setCheckingPlugin(false)
    }
  }, [cacheMs, gateway, lastPluginCheck])

  return {
    checkingPlugin,
    pluginStatus,
    pluginAvailable,
    checkPluginHealth
  }
}