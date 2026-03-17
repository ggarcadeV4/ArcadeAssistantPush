import { useState, useCallback } from 'react'
import { chat } from '../../services/aiClient'

let hasWarnedAboutFallbackDeviceId = false

function resolveDeviceId(): string {
  if (typeof window !== 'undefined') {
    const aaDeviceId = typeof window.AA_DEVICE_ID === 'string' ? window.AA_DEVICE_ID.trim() : ''
    if (aaDeviceId) {
      return aaDeviceId
    }
  }

  if (!hasWarnedAboutFallbackDeviceId) {
    console.warn('[useAIAction] window.AA_DEVICE_ID not available, falling back to demo_001. Cabinet identity may not be unique.')
    hasWarnedAboutFallbackDeviceId = true
  }

  return 'demo_001'
}

interface AIActionHookResult {
  // Primary AI execution - flexible signature for panel usage
  executeAction: (actionType: string, data?: any) => Promise<any>

  // Legacy Claude AI method
  askClaude: (envelope: any, messages: any[]) => Promise<any>

  // Config management
  previewConfig: (filePath: string, diff: any[]) => Promise<any>
  applyConfig: (filePath: string, diff: any[]) => Promise<any>
  listBackups: (filePath: string) => Promise<any>
  revert: (filePath: string) => Promise<any>

  // Loading state
  isLoading: boolean
}

export function useAIAction(panel: string = 'default', deviceId = resolveDeviceId()): AIActionHookResult {
  const [isLoading, setIsLoading] = useState(false)

  const askClaude = useCallback(async (envelope: any, messages: any[]) => {
    setIsLoading(true)
    try {
      const result = await chat({
        provider: 'gemini',
        messages,
        metadata: { panel, envelope },
        scope: 'state',
        deviceId
      })
      return result
    } finally {
      setIsLoading(false)
    }
  }, [panel, deviceId])

  // executeAction with flexible signature for panel compatibility
  const executeAction = useCallback(async (actionType: string, data?: any) => {
    setIsLoading(true)
    try {
      // Build messages array with optional system prompt
      const messages: any[] = []

      // Add system prompt if provided in context
      if (data?.context?.systemPrompt) {
        messages.push({
          role: 'system',
          content: data.context.systemPrompt
        })
      }

      // Add user message
      messages.push({
        role: 'user',
        content: data?.message || JSON.stringify(data)
      })

      const result = await chat({
        provider: 'gemini',
        messages,
        metadata: {
          panel,
          actionType,
          context: data?.context || data
        },
        scope: 'state',
        deviceId,
        tools: data?.tools  // Pass tools through if provided
      })
      return result
    } finally {
      setIsLoading(false)
    }
  }, [panel, deviceId])

  const previewConfig = useCallback(async (filePath: string, diff: any[]) => {
    setIsLoading(true)
    try {
      const r = await fetch('/api/local/config/preview', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-scope': 'config', 'x-device-id': deviceId },
        body: JSON.stringify({ panel, filePath, diff })
      })
      const body = await r.json()
      if (!r.ok) throw body
      return body
    } finally {
      setIsLoading(false)
    }
  }, [panel, deviceId])

  const applyConfig = useCallback(async (filePath: string, diff: any[]) => {
    setIsLoading(true)
    try {
      const r = await fetch('/api/local/config/apply', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-scope': 'config', 'x-device-id': deviceId },
        body: JSON.stringify({ panel, filePath, diff })
      })
      const body = await r.json()
      if (!r.ok) throw body
      return body
    } finally {
      setIsLoading(false)
    }
  }, [panel, deviceId])

  const listBackups = useCallback(async (filePath: string) => {
    setIsLoading(true)
    try {
      const u = new URL('/api/local/config/backups', location.origin)
      u.searchParams.set('panel', panel)
      u.searchParams.set('filePath', filePath)
      const r = await fetch(u.toString(), { headers: { 'x-scope': 'config', 'x-device-id': deviceId } })
      const body = await r.json()
      if (!r.ok) throw body
      return body
    } finally {
      setIsLoading(false)
    }
  }, [panel, deviceId])

  const revert = useCallback(async (filePath: string) => {
    setIsLoading(true)
    try {
      const r = await fetch('/api/local/config/revert', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-scope': 'config', 'x-device-id': deviceId },
        body: JSON.stringify({ panel, filePath })
      })
      const body = await r.json()
      if (!r.ok) throw body
      return body
    } finally {
      setIsLoading(false)
    }
  }, [panel, deviceId])

  return {
    executeAction,
    askClaude,
    previewConfig,
    applyConfig,
    listBackups,
    revert,
    isLoading
  }
}

