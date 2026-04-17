import { useState, useCallback } from 'react'
import { chat } from '../../services/aiClient'
import { buildStandardHeaders, resolveDeviceId } from '../../utils/identity'

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

  // If a caller explicitly overrides the device id (non-default), forward it
  // through extraHeaders so buildStandardHeaders still owns the base contract.
  const deviceIdOverride =
    deviceId && deviceId !== resolveDeviceId() ? { 'x-device-id': deviceId } : {}

  const askClaude = useCallback(async (envelope: any, messages: any[]) => {
    setIsLoading(true)
    try {
      const result = await chat({
        provider: 'gemini',
        messages,
        metadata: { panel, envelope },
        scope: 'state',
        deviceId,
        panel
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
        panel,
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
        headers: buildStandardHeaders({
          panel,
          scope: 'config',
          extraHeaders: { 'content-type': 'application/json', ...deviceIdOverride }
        }),
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
        headers: buildStandardHeaders({
          panel,
          scope: 'config',
          extraHeaders: { 'content-type': 'application/json', ...deviceIdOverride }
        }),
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
      const r = await fetch(u.toString(), {
        headers: buildStandardHeaders({
          panel,
          scope: 'config',
          extraHeaders: deviceIdOverride,
        })
      })
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
        headers: buildStandardHeaders({
          panel,
          scope: 'config',
          extraHeaders: { 'content-type': 'application/json', ...deviceIdOverride }
        }),
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

