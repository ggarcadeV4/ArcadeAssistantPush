import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { PanelShell } from '../_kit'
import DocVoiceControls from './DocVoiceControls'
import {
  getHealthSummary,
  getHealthPerformance,
  getHealthPerformanceTimeseries,
  getHealthProcesses,
  getHealthHardware,
  getHealthAlertsActive,
  getHealthAlertsHistory,
  dismissHealthAlert,
  runOptimizeAction
} from '../../services/systemHealthApi'
import { chat as aiChat } from '../../services/aiClient'
import { speakAsDoc, stopSpeaking } from '../../services/ttsClient'
import './system-health.css'

const createAsyncState = () => ({ data: null, loading: true, error: null })
const QUICK_PROMPTS = [
  { label: 'CPU review', text: 'Doc, explain why CPU usage is elevated right now.' },
  { label: 'Hardware summary', text: 'Summarize any connected hardware issues I should know about.' },
  { label: 'Alert triage', text: 'Are there any alerts I should fix immediately?' }
]
const PROCESS_PREVIEW_LIMIT = 5

export default function SystemHealthPanel() {
  const docDeviceId = useMemo(() => {
    if (typeof window !== 'undefined' && window.AA_DEVICE_ID) return window.AA_DEVICE_ID
    return 'doc-panel'
  }, [])

  const [activeTab, setActiveTab] = useState('performance')
  const [chatOpen, setChatOpen] = useState(false)

  // Stop any ongoing TTS when this panel unmounts
  useEffect(() => () => { try { stopSpeaking() } catch { } }, [])
  const [chatInput, setChatInput] = useState('')
  const [chatMessages, setChatMessages] = useState(() => {
    // Don't show default greeting if coming from Dewey handoff
    const urlParams = new URLSearchParams(window.location.search)
    const hasHandoff = urlParams.get('context')
    if (hasHandoff) return []
    return [
      createChatMessage(
        'ai',
        "Hi! I'm Doc, your arcade health specialist. Ask me about performance, hardware, or diagnostics whenever you need help."
      )
    ]
  })
  const chatMessagesRef = useRef(chatMessages)
  const perfRequestRef = useRef(false)
  const perfTimeseriesRef = useRef(false)
  const processRequestRef = useRef(false)
  const pendingDocMessageRef = useRef(null)
  const handoffProcessedRef = useRef(null)
  useEffect(() => {
    chatMessagesRef.current = chatMessages
  }, [chatMessages])
  const [isTyping, setIsTyping] = useState(false)
  const [chatError, setChatError] = useState(null)

  const [summaryState, setSummaryState] = useState(createAsyncState)
  const [performanceState, setPerformanceState] = useState(createAsyncState)
  const [timeseriesState, setTimeseriesState] = useState(createAsyncState)
  const [processState, setProcessState] = useState(createAsyncState)
  const [hardwareData, setHardwareData] = useState(null)
  const [loadingHardware, setLoadingHardware] = useState(true)
  const [errorHardware, setErrorHardware] = useState(null)
  const [activeAlerts, setActiveAlerts] = useState(null)
  const [alertHistory, setAlertHistory] = useState(null)
  const [loadingAlerts, setLoadingAlerts] = useState(true)
  const [errorAlerts, setErrorAlerts] = useState(null)
  const [dismissingAlertId, setDismissingAlertId] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [optimizeState, setOptimizeState] = useState({
    pending: false,
    message: null,
    error: null,
    lastRun: null
  })
  const [expandedCategories, setExpandedCategories] = useState({})
  const [autoRefreshPerformance, setAutoRefreshPerformance] = useState(true)
  const [autoRefreshProcesses, setAutoRefreshProcesses] = useState(false)
  const [processFilter, setProcessFilter] = useState('')
  const [processSortBy, setProcessSortBy] = useState('cpu')
  const [showResourceHogs, setShowResourceHogs] = useState(false)
  const [hardwareFilter, setHardwareFilter] = useState('all')
  const [hardwareSearch, setHardwareSearch] = useState('')
  const [localAlertNotes, setLocalAlertNotes] = useState([])
  const [hardwareErrorDismissed, setHardwareErrorDismissed] = useState(false)
  const [expandedProcessGroups, setExpandedProcessGroups] = useState(() => ({ gaming: true }))

  // Ref to ensure greeting/handoff TTS only fires once per panel entry
  const hasGreetedRef = useRef(false)

  const hasMeaningfulChange = useCallback((prev, next) => {
    try {
      return JSON.stringify(prev) !== JSON.stringify(next)
    } catch (err) {
      return true
    }
  }, [])

  const runFetch = useCallback(async (fetcher, setState, errorMessage, shouldUpdate = () => true) => {
    setState(prev => ({ ...prev, loading: !prev.data, error: null }))
    try {
      const data = await fetcher()
      let resolvedData = data
      setState(prev => {
        const nextState = { ...prev, loading: false, error: null }
        if (!prev.data || shouldUpdate(prev.data, data)) {
          return { ...nextState, data }
        }
        resolvedData = prev.data
        return { ...nextState, data: prev.data }
      })
      return resolvedData
    } catch (err) {
      const message = err?.message || errorMessage || 'Request failed'
      setState(prev => ({ ...prev, loading: false, error: message }))
      return null
    }
  }, [])

  const loadSummary = useCallback(
    () => runFetch(() => getHealthSummary(), setSummaryState, 'Failed to load summary', hasMeaningfulChange),
    [hasMeaningfulChange, runFetch]
  )
  const loadPerformance = useCallback(async () => {
    if (perfRequestRef.current) return performanceState.data
    perfRequestRef.current = true
    try {
      return await runFetch(
        () => getHealthPerformance(),
        setPerformanceState,
        'Failed to load performance',
        hasMeaningfulChange
      )
    } finally {
      perfRequestRef.current = false
    }
  }, [hasMeaningfulChange, performanceState.data, runFetch])
  const loadPerformanceSeries = useCallback(async () => {
    if (perfTimeseriesRef.current) return timeseriesState.data
    perfTimeseriesRef.current = true
    try {
      return await runFetch(
        () => getHealthPerformanceTimeseries(),
        setTimeseriesState,
        'Failed to load timeseries',
        hasMeaningfulChange
      )
    } finally {
      perfTimeseriesRef.current = false
    }
  }, [hasMeaningfulChange, runFetch, timeseriesState.data])
  const loadProcesses = useCallback(async () => {
    if (processRequestRef.current) return processState.data
    processRequestRef.current = true
    try {
      return await runFetch(
        () => getHealthProcesses(),
        setProcessState,
        'Failed to load processes',
        hasMeaningfulChange
      )
    } finally {
      processRequestRef.current = false
    }
  }, [hasMeaningfulChange, processState.data, runFetch])
  const loadHardware = useCallback(async () => {
    setLoadingHardware(true)
    setErrorHardware(null)
    try {
      const data = await getHealthHardware()
      setHardwareData(data)
      return data
    } catch (err) {
      const message = err?.message || 'Failed to load hardware'
      setErrorHardware(message)
      return null
    } finally {
      setLoadingHardware(false)
    }
  }, [])
  const loadAlerts = useCallback(async () => {
    setLoadingAlerts(true)
    setErrorAlerts(null)
    try {
      const [activeResponse, historyResponse] = await Promise.all([
        getHealthAlertsActive(),
        getHealthAlertsHistory()
      ])
      setActiveAlerts(activeResponse?.alerts || [])
      setAlertHistory(historyResponse?.alerts || [])
      return { active: activeResponse, history: historyResponse }
    } catch (err) {
      const message = err?.message || 'Failed to load alerts'
      setErrorAlerts(message)
      return null
    } finally {
      setLoadingAlerts(false)
    }
  }, [])

  const handleRefreshAll = useCallback(async () => {
    setRefreshing(true)
    await Promise.all([
      loadSummary(),
      loadPerformance(),
      loadPerformanceSeries(),
      loadProcesses(),
      loadHardware(),
      loadAlerts()
    ])
    setRefreshing(false)
  }, [
    loadSummary,
    loadPerformance,
    loadPerformanceSeries,
    loadProcesses,
    loadHardware,
    loadAlerts
  ])

  // Effect 1: Initial data load on mount (user can manually refresh via button)
  useEffect(() => {
    handleRefreshAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Mount-only: handleRefreshAll identity changes as data loads, so we cannot depend on it

  // Effect 2: Greeting/handoff TTS - runs ONCE on mount only (prevents echo from re-fires)
  useEffect(() => {
    // Guard: only greet once per panel entry
    if (hasGreetedRef.current) return

    // Check for handoff context from Dewey (URL-based)
    const urlParams = new URLSearchParams(window.location.search)
    const handoffContext = urlParams.get('context')
    const hasHandoff = Boolean((handoffContext || '').trim())
    const noHandoff = urlParams.has('nohandoff')
    const shouldHandoff = hasHandoff && !noHandoff

    if (shouldHandoff && handoffContext !== handoffProcessedRef.current) {
      hasGreetedRef.current = true
      const welcomeMsg = `Hi! Dewey told me you said: "${handoffContext}"\n\nI'm Doc, your system health specialist. I can help diagnose performance issues, check temperatures, and monitor system resources. What would you like me to check?`
      handoffProcessedRef.current = handoffContext
      setChatMessages([createChatMessage('ai', welcomeMsg)])
      setChatOpen(true)
      speakAsDoc(welcomeMsg).catch(err => {
        console.warn('[Doc] URL handoff TTS failed:', err)
      })
    } else if (!hasHandoff && chatMessages.length === 1 && chatMessages[0].sender === 'ai') {
      // Speak default greeting if present and no handoff
      hasGreetedRef.current = true
      speakAsDoc(chatMessages[0].text).catch(err => {
        console.warn('[Doc] Default greeting TTS failed:', err)
      })
    }

    // Check for JSON handoff from Dewey (only when arriving via Dewey URL context)
    if (shouldHandoff) (async () => {
      try {
        const response = await fetch('/api/local/dewey/handoff/system-health', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
            'x-panel': 'system-health',
            'x-scope': 'state'
          }
        })
        const text = await response.text()
        let data = null
        if (text) {
          try {
            data = JSON.parse(text)
          } catch {
            data = text
          }
        }

        if (data && data.handoff) {
          const rawSummary = typeof data.handoff.summary === 'string'
            ? data.handoff.summary
            : JSON.stringify(data.handoff)

          const summaryText = (rawSummary || '').trim()
          if (summaryText && summaryText !== handoffProcessedRef.current) {
            hasGreetedRef.current = true
            handoffProcessedRef.current = summaryText
            const welcomeMsg = `Dewey briefed me: "${summaryText}". I'm Doc, ready to diagnose your system health!`

            setChatMessages([createChatMessage('ai', welcomeMsg)])
            setChatOpen(true)
            speakAsDoc(welcomeMsg).catch(err => {
              console.warn('[Doc] JSON handoff TTS failed:', err)
            })
          }
        }
      } catch (err) {
        console.warn('[Doc] Handoff fetch failed:', err)
      }
    })()
  }, []) // Empty deps: mount-only, greeting logic does not need to re-run

  // Auto-refresh performance snapshot when enabled (staggered cadence)
  useEffect(() => {
    if (!autoRefreshPerformance) return
    const snapshotInterval = setInterval(() => {
      loadPerformance()
    }, 20000)
    return () => clearInterval(snapshotInterval)
  }, [autoRefreshPerformance, loadPerformance])

  // Auto-refresh performance timeseries less frequently to avoid UI churn
  useEffect(() => {
    if (!autoRefreshPerformance) return
    const seriesInterval = setInterval(() => {
      loadPerformanceSeries()
    }, 35000)
    return () => clearInterval(seriesInterval)
  }, [autoRefreshPerformance, loadPerformanceSeries])

  const shouldAutoRefreshProcesses = autoRefreshProcesses && activeTab === 'processes'

  // Auto-refresh process list only when enabled + tab focused, with longer spacing
  useEffect(() => {
    if (!shouldAutoRefreshProcesses) return
    const interval = setInterval(() => {
      loadProcesses()
    }, 45000)
    return () => clearInterval(interval)
  }, [shouldAutoRefreshProcesses, loadProcesses])

  // When user lands on Processes tab, ensure we have at least one fresh snapshot
  useEffect(() => {
    if (activeTab !== 'processes') return
    if (!processState.data && !processState.loading) {
      loadProcesses()
    }
  }, [activeTab, loadProcesses, processState.data, processState.loading])

  const toggleProcessGroup = useCallback(groupId => {
    setExpandedProcessGroups(prev => ({
      ...prev,
      [groupId]: !prev[groupId]
    }))
  }, [])

  // Baseline poll for summary + alerts regardless of tab
  useEffect(() => {
    const interval = setInterval(() => {
      loadSummary()
      loadAlerts()
    }, 30000)
    return () => clearInterval(interval)
  }, [loadSummary, loadAlerts])

  useEffect(() => {
    const categories = hardwareData?.categories || []
    if (!categories.length) return
    setExpandedCategories(prev => {
      const next = { ...prev }
      categories.forEach(cat => {
        if (typeof next[cat.id] === 'undefined') {
          next[cat.id] = true
        }
      })
      return next
    })
  }, [hardwareData])

  useEffect(() => {
    setHardwareErrorDismissed(false)
  }, [hardwareData?.error])

  const docPrompt = useMemo(() => {
    const lines = [
      'You are Doc, the arcade system health assistant.',
      'Use the telemetry provided to offer concrete troubleshooting steps.',
      'If data is missing, explain what the user can do to collect it.'
    ]
    const summary = summaryState.data
    if (summary) {
      lines.push(
        `System summary: manifest ${summary.manifest_exists ? 'present' : 'missing'}, sanctioned paths ${summary.sanctioned_paths_count}, USB backend ${summary.hardware_status?.usb_backend || summary.usb_backend}, LLM provider ${summary.llm_provider}, STT provider ${summary.stt_provider}.`
      )
    }
    const performance = performanceState.data
    if (performance) {
      lines.push(
        `Performance snapshot: CPU ${formatNumber(performance.cpu?.percent)}%, Memory ${formatNumber(
          performance.memory?.percent
        )}%, FPS ${formatNumber(performance.fps)}, latency ${formatNumber(performance.latency_ms)}ms.`
      )
    }
    const hardware = hardwareData
    if (hardware?.categories?.length) {
      lines.push(
        `Hardware categories: ${hardware.categories
          .map(cat => `${cat.title} (${cat.devices.length} devices)`)
          .join(', ')}.`
      )
    }
    return lines.join('\n')
  }, [summaryState.data, performanceState.data, hardwareData])

  const handleDismissAlert = useCallback(
    async alertId => {
      setDismissingAlertId(alertId)
      try {
        await dismissHealthAlert(alertId)
        await loadAlerts()
      } catch (err) {
        setErrorAlerts(err?.message || 'Failed to dismiss alert')
      } finally {
        setDismissingAlertId(null)
      }
    },
    [loadAlerts]
  )

  const handleOptimize = useCallback(async () => {
    setOptimizeState(prev => ({ ...prev, pending: true, message: null, error: null }))
    try {
      const response = await runOptimizeAction()
      setOptimizeState(prev => ({
        ...prev,
        pending: false,
        message: response?.message || 'Optimization request queued.',
        error: null,
        lastRun: new Date()
      }))
      setLocalAlertNotes(prev => [
        {
          id: `opt-${Date.now()}`,
          title: 'Optimization request logged',
          message: 'Doc will run the queued safe checks next time it can.',
          severity: 'info',
          detected_at: new Date().toISOString(),
          source: 'maintenance'
        },
        ...prev
      ])
    } catch (err) {
      setOptimizeState(prev => ({
        ...prev,
        pending: false,
        message: null,
        error: err?.message || 'Failed to queue optimization request'
      }))
    }
  }, [])

  const headerActions = useMemo(
    () => (
      <div className="sh-header-actions">
        <button className="chat-with-ai-btn refresh" onClick={handleRefreshAll} disabled={refreshing}>
          {refreshing ? 'Refreshing...' : 'Refresh Data'}
        </button>
        <button className="chat-with-ai-btn" onClick={() => setChatOpen(true)}>
          Ask Doc
        </button>
      </div>
    ),
    [handleRefreshAll, refreshing]
  )

  const panelIcon = useMemo(
    () => <img src="/doc-avatar.jpeg" alt="Doc" className="panel-icon-avatar" />,
    []
  )

  const performanceInsights = useMemo(() => {
    const insights = []
    const perf = performanceState.data
    if (!perf) return insights
    if (typeof perf.cpu?.percent === 'number') {
      if (perf.cpu.percent >= 80) {
        insights.push({
          title: 'CPU nearing capacity',
          description: 'Close background tasks or schedule heavy workloads outside play sessions.'
        })
      } else {
        insights.push({
          title: 'CPU load nominal',
          description: 'No throttling observed; continue monitoring during long sessions.'
        })
      }
    }
    if (typeof perf.memory?.percent === 'number') {
      if (perf.memory.percent >= 85) {
        insights.push({
          title: 'High memory usage',
          description: 'Consider reducing simultaneous applications or expanding RAM.'
        })
      }
    }
    const alerts = activeAlerts || []
    alerts.forEach(alert => {
      insights.push({ title: alert.title, description: alert.message })
    })
    if (!insights.length) {
      insights.push({
        title: 'All systems stable',
        description: 'Doc did not detect any actionable performance issues.'
      })
    }
    return insights
  }, [performanceState.data, activeAlerts])

  const summaryCards = useMemo(() => {
    const data = summaryState.data
    return [
      {
        label: 'Manifest',
        value: data ? (data.manifest_exists ? 'Present' : 'Missing') : '--',
        status: data ? (data.manifest_exists ? 'ok' : 'warn') : null,
        description: data ? `Sanctioned paths: ${data.sanctioned_paths_count}` : ''
      },
      {
        label: 'USB backend',
        value: data?.hardware_status?.usb_backend || '--',
        status:
          data?.hardware_status?.status === 'healthy'
            ? 'ok'
            : data?.hardware_status?.status === 'degraded'
              ? 'warn'
              : null,
        description: data?.hardware_status?.error || ''
      },
      {
        label: 'LLM provider',
        value: data?.llm_provider || '--',
        status: data?.llm_provider && data.llm_provider !== 'unconfigured' ? 'ok' : 'warn',
        description: data?.llm_provider === 'unconfigured' ? 'Configure an AI key' : ''
      },
      {
        label: 'STT provider',
        value: data?.stt_provider || '--',
        status: data?.stt_provider && data.stt_provider !== 'unconfigured' ? 'ok' : 'warn',
        description: data?.stt_provider === 'unconfigured' ? 'Configure speech-to-text' : ''
      }
    ]
  }, [summaryState.data])

  const performanceMetrics = useMemo(() => {
    const perf = performanceState.data
    return [
      {
        label: 'FPS average',
        value: formatNumber(perf?.fps),
        sublabel: 'Target: 60 FPS'
      },
      {
        label: 'Input latency',
        value: perf?.latency_ms != null ? `${perf.latency_ms.toFixed(1)} ms` : '--',
        sublabel: 'Lower is better'
      },
      {
        label: 'CPU gaming load',
        value: formatPercent(perf?.cpu?.percent),
        sublabel: 'Realtime utilization'
      },
      {
        label: 'Gaming memory',
        value: formatMemory(perf?.memory),
        sublabel: 'Used / Total'
      },
      {
        label: 'GPU temperature',
        value:
          typeof perf?.gpu_temp_c === 'number' ? `${perf.gpu_temp_c.toFixed(1)} C` : 'Sensor unavailable',
        sublabel: 'Estimated core temp'
      },
      {
        label: 'Frame consistency',
        value: perf?.frame_consistency ? `${perf.frame_consistency.toFixed(1)}%` : '--',
        sublabel: 'Stability over 1 min'
      }
    ]
  }, [performanceState.data])

  const timeseriesSamples = (timeseriesState.data?.samples || []).slice(-6).reverse()
  const activeAlertsList = activeAlerts || []

  // docTelemetry must be defined after activeAlertsList but before sendDocMessage
  const docTelemetry = useMemo(
    () => ({
      summary: summaryState.data,
      performance: performanceState.data,
      hardware: hardwareData,
      alerts: activeAlertsList
    }),
    [summaryState.data, performanceState.data, hardwareData, activeAlertsList]
  )

  // sendDocMessage moved here after docTelemetry to avoid circular dependency
  const sendDocMessage = useCallback(
    async messageText => {
      const trimmed = messageText.trim()
      if (!trimmed) return
      if (isTyping) {
        pendingDocMessageRef.current = trimmed
        return
      }
      const userMessage = createChatMessage('user', trimmed)
      setChatMessages(prev => [...prev, userMessage])
      setChatInput('')
      setIsTyping(true)
      setChatError(null)

      try {
        const history = [...chatMessagesRef.current, userMessage].slice(-10).map(msg => ({
          role: msg.sender === 'ai' ? 'assistant' : msg.sender === 'system' ? 'system' : 'user',
          content: msg.text
        }))
        const response = await aiChat({
          messages: [{ role: 'system', content: docPrompt }, ...history],
          scope: 'state',
          panel: 'doc',
          deviceId: docDeviceId,
          metadata: { panel: 'doc' }
        })
        const rawReply = response?.message?.content || response?.response || 'Let me take a closer look.'
        const reply = `Here's what I'm seeing:\n${rawReply}`.trim()
        setChatMessages(prev => [...prev, createChatMessage('ai', reply)])
        speakAsDoc(reply).catch(err => {
          console.error('[Doc TTS] Playback failed', err)
        })
      } catch (err) {
        const offlineReason = getDocOfflineReason(err)
        if (offlineReason) {
          const offlineReply =
            offlineReason === 'not_configured'
              ? 'AI service not configured. You can still check health cards and alerts manually.'
              : buildDocOfflineResponse(docTelemetry)
          setChatMessages(prev => [...prev, createChatMessage('ai', offlineReply)])
          speakAsDoc(offlineReply).catch(ttsErr => {
            console.error('[Doc TTS] Playback failed', ttsErr)
          })
          setChatError(null)
        } else {
          const message =
            err?.code === 'NOT_CONFIGURED' || /not configured/i.test(err?.detail || err?.message || '')
              ? "Doc's AI connection is not configured. Add an Anthropic or OpenAI key and refresh."
              : err?.message || 'Doc encountered an error while replying.'
          setChatError(message)
          setChatMessages(prev => [...prev, createChatMessage('system', message, true)])
        }
      } finally {
        setIsTyping(false)
        if (pendingDocMessageRef.current) {
          const queued = pendingDocMessageRef.current
          pendingDocMessageRef.current = null
          setTimeout(() => sendDocMessage(queued), 0)
        }
      }
    },
    [docDeviceId, docPrompt, docTelemetry, isTyping]
  )

  const alertHistoryList = useMemo(
    () => [...localAlertNotes, ...(alertHistory || [])],
    [alertHistory, localAlertNotes]
  )
  const processGroups = processState.data?.groups || []
  const hardwareCategories = hardwareData?.categories || []
  const filteredHardwareCategories = useMemo(() => {
    const term = hardwareSearch.trim().toLowerCase()
    return hardwareCategories
      .map(category => {
        const devices = (category.devices || []).filter(device => {
          const status = (device.status || '').toLowerCase()
          const matchesStatus = hardwareFilter === 'all' || status === hardwareFilter
          if (!matchesStatus) return false
          if (!term) return true
          return (
            (device.name || '').toLowerCase().includes(term) ||
            String(device.id || '').toLowerCase().includes(term)
          )
        })
        return { ...category, devices }
      })
      .filter(category => category.devices.length > 0)
  }, [hardwareCategories, hardwareFilter, hardwareSearch])
  const hardwareStats = useMemo(() => {
    const stats = { connected: 0, warning: 0, disconnected: 0 }
    hardwareCategories.forEach(category => {
      ; (category.devices || []).forEach(device => {
        const status = (device.status || '').toLowerCase()
        if (status === 'connected') stats.connected += 1
        else if (status === 'warning') stats.warning += 1
        else if (status === 'disconnected') stats.disconnected += 1
      })
    })
    return stats
  }, [hardwareCategories])
  const hardwareStatus = (hardwareData?.status || 'unknown').toLowerCase()
  const hardwareStatusLabel = hardwareStatus ? hardwareStatus.toUpperCase() : 'UNKNOWN'
  const hardwareUsbBackend = hardwareData?.usb_backend
  // docTelemetry moved earlier to avoid circular dependency
  const docQuickDiagnosis = useMemo(() => buildDocQuickDiagnosis(docTelemetry), [docTelemetry])

  const processOverview = useMemo(() => {
    const totals = {
      total: 0,
      heavy: 0,
      timestamp: processState.data?.timestamp || null
    }
    processGroups.forEach(group => {
      totals.total += group.processes.length
      group.processes.forEach(proc => {
        if ((proc.cpu_percent || 0) >= 70 || (proc.memory_bytes || 0) >= 0.5 * 1024 * 1024 * 1024) {
          totals.heavy += 1
        }
      })
    })
    return totals
  }, [processGroups, processState.data])
  const filteredProcessGroups = useMemo(() => {
    const term = processFilter.trim().toLowerCase()
    return processGroups
      .map(group => {
        const processes = group.processes
          .slice()
          .sort((a, b) =>
            processSortBy === 'memory'
              ? (b.memory_bytes || 0) - (a.memory_bytes || 0)
              : (b.cpu_percent || 0) - (a.cpu_percent || 0)
          )
          .filter(proc => {
            const cpu = proc.cpu_percent || 0
            const mem = proc.memory_bytes || 0
            if (showResourceHogs && cpu < 50 && mem < 500 * 1024 * 1024) {
              return false
            }
            if (!term) return true
            const pidString = String(proc.pid || '')
            const path = (proc.path || '').toLowerCase()
            return (
              (proc.name || '').toLowerCase().includes(term) ||
              pidString.includes(term) ||
              path.includes(term)
            )
          })
        return { ...group, processes }
      })
      .filter(group => group.processes.length > 0)
  }, [processGroups, processFilter, processSortBy, showResourceHogs])
  const processesUnavailable = processState.data?.psutil_available === false
  const performanceUpdatedAt = performanceState.data?.timestamp || summaryState.data?.timestamp || null
  const processesUpdatedAt = processState.data?.timestamp || null
  return (
    <div className="eb-layout">
      <div className="eb-layout__main">
        <PanelShell
          title="System Health Panel"
          subtitle="Live telemetry for Doc"
          icon={panelIcon}
          headerActions={headerActions}
          status="online"
          className="system-health"
          bodyClassName="system-health-body"
        >
          <div className="system-health-content">
            <div className="sh-summary-grid">
              {summaryState.loading && !summaryState.data && <div className="sh-summary-card">Loading summary...</div>}
              {summaryState.error && !summaryState.data && (
                <div className="sh-summary-card sh-summary-error">Error: {summaryState.error}</div>
              )}
              {summaryState.data &&
                summaryCards.map(card => (
                  <div
                    key={card.label}
                    className={`sh-summary-card ${card.status === 'warn' ? 'warn' : 'ok'}`}
                    aria-label={`${card.label} status`}
                  >
                    <div className="sh-summary-label">{card.label}</div>
                    <div className="sh-summary-value">{card.value}</div>
                    {card.description && <div className="sh-summary-description">{card.description}</div>}
                  </div>
                ))}
            </div>
            <div className="sh-diagnosis-section">
              <div className="sh-diagnosis-header">
                <div>
                  <h3>Doc Quick Diagnosis</h3>
                  <p>Live summary of the most actionable health findings.</p>
                </div>
              </div>
              <div className="sh-diagnosis-grid">
                {docQuickDiagnosis.lines.map((line, index) => (
                  <div key={`diag-${index}`} className="sh-diagnosis-card">
                    <div className="sh-diagnosis-detail">{line}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick diagnosis gives Doc-style summary using current telemetry */}
            <div className={`sh-quick-card status-${docQuickDiagnosis.overallStatus || 'healthy'}`}>
              <div className="sh-quick-header">
                <div>
                  <h3>Doc's Quick Diagnosis</h3>
                  <p>Top-level summary of hardware, performance, and alert posture.</p>
                </div>
                <span className={`sh-quick-badge status-${docQuickDiagnosis.overallStatus || 'healthy'}`}>
                  {docQuickDiagnosis.overallStatus
                    ? docQuickDiagnosis.overallStatus.toUpperCase()
                    : 'HEALTHY'}
                </span>
              </div>
              {docQuickDiagnosis.lines.length ? (
                <ul className="sh-quick-lines">
                  {docQuickDiagnosis.lines.map((line, index) => (
                    <li key={`${line}-${index}`}>{line}</li>
                  ))}
                </ul>
              ) : (
                <div className="sh-quick-loading">Gathering telemetry...</div>
              )}
            </div>

            <div className="sh-tab-bar">
              {['performance', 'processes', 'hardware', 'alerts'].map(tab => (
                <button
                  key={tab}
                  className={`sh-tab ${activeTab === tab ? 'active' : ''}`}
                  onClick={() => setActiveTab(tab)}
                >
                  {tab === 'performance' && 'Performance'}
                  {tab === 'processes' && 'Processes'}
                  {tab === 'hardware' && 'Hardware'}
                  {tab === 'alerts' && 'Alerts'}
                </button>
              ))}
            </div>

            {activeTab === 'performance' && (
              <div className="sh-tab-content">
                <div className="sh-performance-header">
                  <div className="sh-perf-title">
                    <h2>Gaming Performance Monitor</h2>
                    <div className="sh-perf-status">
                      <span className="sh-status-dot optimal"></span>
                      <span>
                        Last updated:{' '}
                        {performanceUpdatedAt ? formatTimeOfDay(performanceUpdatedAt) : 'calibrating...'}
                      </span>
                    </div>
                  </div>
                  <div className="sh-perf-controls">
                    <label className={`sh-toggle ${autoRefreshPerformance ? 'active' : ''}`}>
                      <input
                        type="checkbox"
                        checked={autoRefreshPerformance}
                        onChange={e => setAutoRefreshPerformance(e.target.checked)}
                      />
                      Auto-refresh
                    </label>
                    <span className="sh-last-updated">
                      Samples: {timeseriesSamples.length.toString().padStart(1, '0')}
                    </span>
                  </div>
                </div>
                {/* Safe no-op optimize button logs intent via backend */}
                <div className="sh-optimize-card">
                  <div className="sh-optimize-copy">
                    <h4>Doc Auto Optimize</h4>
                    <p>Queues a safe tune-up via the backend (cache cleanup, telemetry recalibration, USB sanity checks).</p>
                    <div className="sh-optimize-meta">
                      <span>
                        Last request:{' '}
                        {optimizeState.lastRun ? formatTimestamp(optimizeState.lastRun) : 'Not requested yet'}
                      </span>
                      {optimizeState.message && <span className="sh-optimize-hint">{optimizeState.message}</span>}
                      {optimizeState.error && (
                        <span className="sh-optimize-error">Error: {optimizeState.error}</span>
                      )}
                    </div>
                  </div>
                  <button
                    className="sh-auto-optimize-btn"
                    onClick={handleOptimize}
                    disabled={optimizeState.pending}
                    title="Doc will log an optimization request for later processing."
                  >
                    {optimizeState.pending ? 'Queuing...' : 'Run Quick Optimization'}
                  </button>
                </div>

                <div className="sh-metrics-grid">
                  {performanceState.loading && !performanceState.data && (
                    <div className="sh-metric-card">Loading performance...</div>
                  )}
                  {performanceState.error && !performanceState.data && (
                    <div className="sh-metric-card sh-summary-error">{performanceState.error}</div>
                  )}
                  {performanceState.data &&
                    performanceMetrics.map(metric => (
                      <div key={metric.label} className="sh-metric-card">
                        <div className="sh-metric-value">{metric.value}</div>
                        <div className="sh-metric-label">{metric.label}</div>
                        <div className="sh-metric-sublabel">{metric.sublabel}</div>
                      </div>
                    ))}
                </div>

                <div className="sh-chart-container">
                  <div className="sh-chart-header">
                    <h3>Recent Samples (last 5 entries)</h3>
                  </div>
                  <div className="sh-chart-placeholder">
                    {timeseriesState.loading && !timeseriesSamples.length && <div>Loading samples...</div>}
                    {timeseriesState.error && !timeseriesSamples.length && (
                      <div>Error: {timeseriesState.error}</div>
                    )}
                    {timeseriesSamples.length > 0 && (
                      <table className="sh-samples-table">
                        <thead>
                          <tr>
                            <th>Timestamp</th>
                            <th>CPU</th>
                            <th>Memory</th>
                            <th>FPS</th>
                            <th>Latency</th>
                          </tr>
                        </thead>
                        <tbody>
                          {timeseriesSamples.map(sample => (
                            <tr key={sample.timestamp}>
                              <td>{formatTimestamp(sample.timestamp)}</td>
                              <td>{formatPercent(sample.cpu_percent)}</td>
                              <td>{formatPercent(sample.memory_percent)}</td>
                              <td>{sample.fps != null ? sample.fps.toFixed(1) : '--'}</td>
                              <td>{sample.latency_ms != null ? `${sample.latency_ms.toFixed(1)} ms` : '--'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>

                <div className="sh-suggestions-panel">
                  <h3>Performance Insights</h3>
                  <div className="sh-suggestions-list">
                    {performanceInsights.map(insight => (
                      <div key={insight.title} className="sh-suggestion-item">
                        <div className="sh-suggestion-content">
                          <div className="sh-suggestion-title">{insight.title}</div>
                          <div className="sh-suggestion-desc">{insight.description}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'processes' && (
              <div className="sh-tab-content">
                <div className="sh-process-header">
                  <div>
                    <h2>Arcade Process Management</h2>
                    <p>Doc tracks emulator cores, assistants, and helper daemons.</p>
                    <div className="sh-process-stats">
                      <span>Total tracked: {processOverview.total}</span>
                      <span>High usage: {processOverview.heavy}</span>
                      {processOverview.timestamp && (
                        <span>Updated {formatTimestamp(processOverview.timestamp)}</span>
                      )}
                    </div>
                  </div>
                  <div className="sh-process-actions">
                    <label className={`sh-toggle ${autoRefreshProcesses ? 'active' : ''}`}>
                      <input
                        type="checkbox"
                        checked={autoRefreshProcesses}
                        onChange={e => setAutoRefreshProcesses(e.target.checked)}
                      />
                      Auto-refresh
                    </label>
                    <span className="sh-last-updated">
                      Last updated: {processesUpdatedAt ? formatTimeOfDay(processesUpdatedAt) : 'pending'}
                    </span>
                    <button className="chat-with-ai-btn refresh" onClick={loadProcesses} disabled={processState.loading}>
                      {processState.loading ? 'Refreshing...' : 'Refresh'}
                    </button>
                  </div>
                </div>
                {processesUnavailable && (
                  <div className="sh-summary-error">Process metrics unavailable on this platform.</div>
                )}
                {processState.error && (
                  <div className="sh-summary-error">Error: {processState.error}</div>
                )}
                <div className="sh-process-controls">
                  <input
                    type="text"
                    value={processFilter}
                    onChange={e => setProcessFilter(e.target.value)}
                    placeholder="Filter by name, PID, or path"
                  />
                  <label className="sh-sort-select">
                    Sort by
                    <select value={processSortBy} onChange={e => setProcessSortBy(e.target.value)}>
                      <option value="cpu">CPU</option>
                      <option value="memory">Memory</option>
                    </select>
                  </label>
                  <label className={`sh-toggle ${showResourceHogs ? 'active' : ''}`}>
                    <input
                      type="checkbox"
                      checked={showResourceHogs}
                      onChange={e => setShowResourceHogs(e.target.checked)}
                    />
                    Show only heavy usage
                  </label>
                </div>

                <div className="sh-process-groups">
                  {filteredProcessGroups.length === 0 && !processState.loading && (
                    <div className="sh-empty">No processes match the current filters.</div>
                  )}
                  {filteredProcessGroups.map(group => {
                    const isExpanded = expandedProcessGroups[group.id] || false
                    const visibleProcesses = isExpanded
                      ? group.processes
                      : group.processes.slice(0, PROCESS_PREVIEW_LIMIT)
                    const hiddenCount = group.processes.length - visibleProcesses.length
                    return (
                      <div className="sh-process-group" key={group.id}>
                        <div className={`sh-group-header ${isExpanded ? 'expanded' : ''}`}>
                          <div className="sh-group-title">
                            <span>{group.title}</span>
                            <span className="sh-group-count">{group.processes.length}</span>
                          </div>
                          <div className="sh-group-actions">
                            <span className="sh-group-status healthy">MONITORED</span>
                            {group.processes.length > PROCESS_PREVIEW_LIMIT && (
                              <button
                                className="sh-group-toggle-btn"
                                onClick={() => toggleProcessGroup(group.id)}
                              >
                                {isExpanded ? 'Collapse' : `Show all (${group.processes.length})`}
                              </button>
                            )}
                          </div>
                        </div>
                        <div className="sh-group-content">
                          {group.processes.length === 0 && <div className="sh-empty">No processes detected</div>}
                          {visibleProcesses.map(process => (
                            <ProcessItem key={`${group.id}-${process.pid}-${process.name}`} process={process} />
                          ))}
                          {!isExpanded && hiddenCount > 0 && (
                            <button
                              className="sh-group-showmore"
                              onClick={() => toggleProcessGroup(group.id)}
                            >
                              Show {hiddenCount} more
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {activeTab === 'hardware' && (
              <div className="sh-tab-content">
                <div className="sh-process-header">
                  <div>
                    <h2>Hardware & Devices</h2>
                    {hardwareData && (
                      <div className="sh-hardware-meta">
                        <span className={`sh-status-pill status-${hardwareStatus}`}>{hardwareStatusLabel}</span>
                        <span className="sh-hardware-usb">
                          USB backend: {hardwareUsbBackend ? formatMetricLabel(hardwareUsbBackend) : 'Unknown'}
                        </span>
                        {hardwareData.timestamp && (
                          <span className="sh-hardware-timestamp">
                            Updated {formatTimestamp(hardwareData.timestamp)}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="sh-hardware-actions">
                    <button className="chat-with-ai-btn refresh" onClick={loadHardware} disabled={loadingHardware}>
                      {loadingHardware ? 'Refreshing...' : 'Refresh'}
                    </button>
                  </div>
                </div>
                {hardwareData?.error && !hardwareErrorDismissed && (
                  <div className="sh-banner warn">
                    <span>Hardware subsystem reported: {hardwareData.error}</span>
                    <button onClick={() => setHardwareErrorDismissed(true)}>Dismiss</button>
                  </div>
                )}
                <div className="sh-hardware-stats">
                  <span>Connected: {hardwareStats.connected}</span>
                  <span>Warnings: {hardwareStats.warning}</span>
                  <span>Disconnected: {hardwareStats.disconnected}</span>
                </div>
                <div className="sh-hardware-controls">
                  <label>
                    Status filter
                    <select value={hardwareFilter} onChange={e => setHardwareFilter(e.target.value)}>
                      <option value="all">All</option>
                      <option value="connected">Connected</option>
                      <option value="warning">Warning</option>
                      <option value="disconnected">Disconnected</option>
                    </select>
                  </label>
                  <input
                    type="text"
                    value={hardwareSearch}
                    onChange={e => setHardwareSearch(e.target.value)}
                    placeholder="Search by name or device ID"
                  />
                </div>
                {loadingHardware && !hardwareCategories.length && <div>Loading hardware...</div>}
                {errorHardware && !hardwareCategories.length && (
                  <div className="sh-summary-error">Error: {errorHardware}</div>
                )}
                <div className="sh-hardware-grid">
                  {filteredHardwareCategories.length === 0 && !loadingHardware && (
                    <div className="sh-empty">No devices match the selected filters.</div>
                  )}
                  {filteredHardwareCategories.map(category => {
                    const issueDevices = (category.devices || []).filter(device => {
                      const status = (device.status || '').toLowerCase()
                      return status === 'warning' || status === 'disconnected'
                    })
                    const issueNames = issueDevices.slice(0, 2).map(device => device.name || device.id || 'Device')
                    return (
                      <div className="sh-hardware-category" key={category.id}>
                        <div
                          className="sh-category-header"
                          onClick={() =>
                            setExpandedCategories(prev => ({
                              ...prev,
                              [category.id]: !prev[category.id]
                            }))
                          }
                        >
                          <div className="sh-category-title">
                            <span>{category.title}</span>
                            {issueNames.length > 0 && (
                              <span className="sh-category-note">
                                Issues: {issueNames.join(', ')}
                                {issueDevices.length > issueNames.length
                                  ? ` +${issueDevices.length - issueNames.length}`
                                  : ''}
                              </span>
                            )}
                          </div>
                          <div className="sh-category-meta">
                            <span className="sh-category-status">{category.devices.length} devices</span>
                            <span
                              className={`sh-category-pill ${issueDevices.length ? 'status-issues' : 'status-ok'}`}
                            >
                              {issueDevices.length ? 'Issues detected' : 'All clear'}
                            </span>
                          </div>
                        </div>
                        {expandedCategories[category.id] && (
                          <div className="sh-category-content">
                            {category.devices.map(device => (
                              <HardwareDevice key={device.id || device.name} device={device} />
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {activeTab === 'alerts' && (
              <div className="sh-tab-content">
                <div className="sh-alerts-toolbar">
                  <button className="chat-with-ai-btn refresh" onClick={loadAlerts} disabled={loadingAlerts}>
                    {loadingAlerts ? 'Refreshing...' : 'Refresh Alerts'}
                  </button>
                </div>
                {errorAlerts && <div className="sh-summary-error">Error: {errorAlerts}</div>}
                <div className="sh-alerts-layout">
                  <div className="sh-alert-section">
                    <div className="sh-alert-header">
                      <h3>Active Alerts</h3>
                      <span className="sh-alert-count">{activeAlertsList.length}</span>
                    </div>
                    {loadingAlerts && !activeAlertsList.length && <div>Loading alerts...</div>}
                    <div className="sh-alerts-list">
                      {!loadingAlerts && !errorAlerts && activeAlertsList.length === 0 && (
                        <div className="sh-empty">No active alerts</div>
                      )}
                      {activeAlertsList.map(alert => (
                        <AlertItem
                          key={alert.id}
                          alert={alert}
                          onDismiss={() => handleDismissAlert(alert.id)}
                          dismissing={dismissingAlertId === alert.id}
                          showActions
                        />
                      ))}
                    </div>
                  </div>
                  <div className="sh-alert-section">
                    <div className="sh-alert-header">
                      <h3>Alert History</h3>
                      <span className="sh-alert-count">{alertHistoryList.length}</span>
                    </div>
                    {loadingAlerts && !alertHistoryList.length && <div>Loading history...</div>}
                    <div className="sh-alerts-list">
                      {!loadingAlerts && !errorAlerts && alertHistoryList.length === 0 && (
                        <div className="sh-empty">No historical alerts logged</div>
                      )}
                      {alertHistoryList.map(alert => (
                        <AlertItem key={`${alert.id}-${alert.dismissed_at || alert.detected_at}`} alert={alert} compact />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </PanelShell>
      </div>

      {/* Doc AI Chat Sidebar — permanent sticky panel */}
      <div className="panel-chat-sidebar"
        role="complementary"
        aria-label="Chat with Doc"
        style={{
          height: '100vh', position: 'sticky', top: 0, overflowY: 'hidden',
          flexShrink: 0, width: '320px', display: 'flex', flexDirection: 'column',
          background: '#0a0702', borderLeft: '1px solid rgba(249,115,22,0.25)'
        }}>
        <div className="chat-header">
          <img src="/doc-avatar.jpeg" alt="Doc" className="chat-avatar" />
          <div className="chat-header-info">
            <h3>Doc</h3>
            <p>Health Monitoring Specialist</p>
          </div>
          <div className="chat-header-actions">
            <DocVoiceControls
              onTranscript={sendDocMessage}
              ensureChatOpen={() => setChatOpen(true)}
            />
            <button className="chat-close-btn" onClick={() => setChatOpen(false)} aria-label="Close chat">
              x
            </button>
          </div>
        </div>

        <div className="chat-messages">
          {chatMessages.map(message => (
            <div key={message.id} className={`chat-message ${message.sender}`}>
              <div className="chat-message-content">
                <div
                  className={`chat-message-text ${message.isError ? 'error' : ''}`}
                  dangerouslySetInnerHTML={{ __html: formatAssistantResponse(message.text) }}
                />
                <div className="chat-message-time">
                  {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
            </div>
          ))}
          {isTyping && (
            <div className="chat-typing-indicator">
              <span>Doc is thinking...</span>
              <div className="chat-typing-dots">
                <div className="chat-typing-dot"></div>
                <div className="chat-typing-dot"></div>
                <div className="chat-typing-dot"></div>
              </div>
            </div>
          )}
        </div>

        {chatError && <div className="chat-error">{chatError}</div>}

        <div className="chat-quick-actions">
          {QUICK_PROMPTS.map(prompt => (
            <button
              key={prompt.label}
              className="quick-action-btn"
              onClick={() => sendDocMessage(prompt.text)}
              disabled={isTyping}
            >
              {prompt.label}
            </button>
          ))}
        </div>

        <div className="chat-input-container">
          <textarea
            className="chat-input"
            value={chatInput}
            onChange={e => setChatInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                sendDocMessage(chatInput)
              }
            }}
            placeholder="Ask Doc about performance, hardware, or diagnostics..."
            rows={1}
          />
          <button
            className="chat-send-btn"
            onClick={() => sendDocMessage(chatInput)}
            disabled={!chatInput.trim() || isTyping}
            aria-label="Send message"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
function ProcessItem({ process }) {
  const cpu = typeof process.cpu_percent === 'number' ? process.cpu_percent : 0
  const memory = typeof process.memory_bytes === 'number' ? formatBytes(process.memory_bytes) : '--'
  const status = (process.status || 'unknown').toLowerCase()
  const healthPercent = Math.round((process.health ?? 0) * 100)
  const isHot = cpu >= 50 || (process.memory_bytes || 0) >= 512 * 1024 * 1024
  return (
    <div className={`sh-process-item ${isHot ? 'hot' : ''}`}>
      <div className="sh-process-info">
        <div className="sh-process-name">
          <span>{process.name || 'Unknown Process'}</span>
          <span className="sh-process-path">{process.path || 'n/a'}</span>
        </div>
        <div className="sh-resource-usage">
          <span className="sh-resource-label">CPU: {cpu.toFixed(1)}%</span>
          <div className="sh-resource-bar">
            <div
              className="sh-resource-fill"
              style={{
                width: `${Math.min(100, cpu)}%`,
                '--usage-color': cpu > 60 ? '#f59e0b' : '#22c55e'
              }}
            />
          </div>
        </div>
        <div className="sh-resource-usage">
          <span className="sh-resource-label">RAM: {memory}</span>
        </div>
        <span className={`sh-status-pill status-${status}`}>{status.toUpperCase()}</span>
        <span className={`sh-health-score ${healthPercent > 90 ? 'excellent' : healthPercent > 75 ? 'good' : 'warning'}`}>
          {healthPercent}%
        </span>
      </div>
    </div>
  )
}

function HardwareDevice({ device }) {
  const status = (device.status || '').toLowerCase()
  const healthPercent = device.health != null ? Math.round(device.health * 100) : null
  const healthColor = healthPercent != null ? (healthPercent > 85 ? '#22c55e' : healthPercent > 70 ? '#f59e0b' : '#ef4444') : '#22c55e'
  const statusColor =
    status === 'connected' ? '#22c55e' : status === 'warning' ? '#f59e0b' : status === 'disconnected' ? '#ef4444' : '#6b7280'
  const metrics = device.metrics
    ? Object.entries(device.metrics).map(([key, value]) => ({
      label: formatMetricLabel(key),
      value: typeof value === 'number' ? value : String(value)
    }))
    : []
  return (
    <div className="sh-device-item" style={{ '--device-color': healthColor }}>
      <div className="sh-device-header">
        <div className="sh-device-name">{device.name || 'Device'}</div>
        <span className={`sh-device-status ${status}`} style={{ color: statusColor }}>
          {status ? status.toUpperCase() : 'UNKNOWN'}
        </span>
      </div>
      {metrics.length > 0 && (
        <div className="sh-device-specs">
          {metrics.map(metric => (
            <div key={metric.label} className="sh-spec-item">
              <span className="sh-spec-label">{metric.label}:</span>
              <span className="sh-spec-value">{metric.value}</span>
            </div>
          ))}
        </div>
      )}
      {healthPercent != null && (
        <div className="sh-device-health">
          <div className="sh-health-bar">
            <div className="sh-health-fill" style={{ width: `${Math.min(100, healthPercent)}%`, '--health-color': healthColor }} />
          </div>
          <span className="sh-health-percentage" style={{ '--health-color': healthColor }}>
            {healthPercent}%
          </span>
        </div>
      )}
    </div>
  )
}

function AlertItem({ alert, onDismiss, dismissing, showActions, compact }) {
  const severity = (alert.severity || 'info').toLowerCase()
  const timestamp = alert.detected_at || alert.dismissed_at
  const sourceLabel = alert.source ? formatMetricLabel(alert.source) : null
  return (
    <div className={`sh-alert-item severity-${severity}`}>
      <div className="sh-alert-item-header">
        <div className="sh-alert-item-title">
          <span>{alert.title}</span>
          {sourceLabel && <span> ({sourceLabel})</span>}
        </div>
        <div className="sh-alert-time">{formatTimestamp(timestamp)}</div>
      </div>
      <div className="sh-alert-details">{alert.message}</div>
      {showActions && (
        <div className="sh-alert-actions">
          <button className="sh-alert-btn" onClick={() => onDismiss(alert.id)} disabled={dismissing}>
            {dismissing ? 'Dismissing...' : 'Dismiss'}
          </button>
        </div>
      )}
      {compact && (
        <div className="sh-alert-meta">
          {alert.dismissed_at && <div>Dismissed {formatTimestamp(alert.dismissed_at)}</div>}
          {alert.reason && <div>Reason: {alert.reason}</div>}
        </div>
      )}
    </div>
  )
}

function formatNumber(value) {
  if (typeof value === 'number') return value.toFixed(1)
  return '--'
}

function formatPercent(value) {
  if (typeof value === 'number') return `${value.toFixed(1)}%`
  return '--'
}

function formatMemory(memory) {
  if (!memory) return '--'
  const used = typeof memory.used_gb === 'number' ? memory.used_gb.toFixed(1) : null
  const total = typeof memory.total_gb === 'number' ? memory.total_gb.toFixed(1) : null
  if (used && total) return `${used} / ${total} GB`
  if (memory.used_bytes != null) return formatBytes(memory.used_bytes)
  return '--'
}

function formatBytes(bytes) {
  if (typeof bytes !== 'number') return '--'
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(2)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

function formatTimestamp(value) {
  if (!value) return 'n/a'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

function formatMetricLabel(label) {
  return label
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function formatAssistantResponse(value = '') {
  return value.replace(/\n/g, '<br />')
}

function createChatMessage(sender, text, isError = false) {
  return {
    id: `${Date.now()}-${Math.random()}`,
    sender,
    text,
    timestamp: new Date(),
    isError
  }
}

function getDocOfflineReason(error) {
  if (!error) return null
  if (error.code === 'NOT_CONFIGURED') return 'not_configured'
  if (error.status === 501 || error.status === 502) return 'offline'
  const detail = (error.detail || error.message || '').toLowerCase()
  if (detail.includes('not configured')) return 'not_configured'
  if (/provider unavailable|upstream/i.test(detail)) return 'offline'
  return null
}

function buildDocOfflineResponse({ summary, performance, hardware, alerts = [] } = {}) {
  const sentences = [
    "Doc's AI uplink is offline, but here's what local telemetry shows."
  ]
  if (summary) {
    if (typeof summary.manifest_exists === 'boolean') {
      sentences.push(`Manifest is ${summary.manifest_exists ? 'present' : 'missing'}.`)
    }
    if (typeof summary.sanctioned_paths_count === 'number') {
      sentences.push(`Tracked sanctioned paths: ${summary.sanctioned_paths_count}.`)
    }
  }
  if (performance) {
    if (typeof performance.cpu?.percent === 'number') {
      sentences.push(`CPU load is roughly ${performance.cpu.percent.toFixed(1)}%.`)
    }
    if (performance.memory) {
      const memoryText = formatMemory(performance.memory)
      if (memoryText !== '--') {
        sentences.push(`RAM usage is ${memoryText}.`)
      }
    }
    if (typeof performance.latency_ms === 'number') {
      sentences.push(`Input latency is about ${performance.latency_ms.toFixed(1)} ms.`)
    }
    if (typeof performance.fps === 'number') {
      sentences.push(`Average frame rate is ${formatNumber(performance.fps)} FPS.`)
    }
  }
  if (hardware) {
    if (hardware.status) {
      sentences.push(`Hardware status reports ${formatMetricLabel(hardware.status)}.`)
    }
    if (hardware.usb_backend) {
      sentences.push(`USB backend: ${formatMetricLabel(hardware.usb_backend)}.`)
    }
  }
  if (alerts.length > 0) {
    const alertSnippets = alerts.slice(0, 2).map(alert => `${alert.title}: ${alert.message}`)
    sentences.push(`Active alerts: ${alertSnippets.join(' | ')}.`)
  } else {
    sentences.push('No active alerts are currently logged.')
  }
  sentences.push('Once the AI link returns, try again for deeper guidance.')
  return sentences.join(' ')
}

// Condense hardware/performance/alert context into Doc-style bullet lines
function buildDocQuickDiagnosis({ summary = {}, performance = {}, hardware = {}, alerts = [] } = {}) {
  const summaryData = summary || {}
  const performanceData = performance || {}
  const hardwareData = hardware || {}
  const alertsList = Array.isArray(alerts) ? alerts : []
  const lines = []
  const hardwareStatus =
    (hardwareData.status || summaryData?.hardware_status?.status || 'healthy').toLowerCase()
  let overallStatus = 'healthy'
  if (hardwareStatus === 'degraded') overallStatus = 'degraded'
  if (hardwareStatus === 'critical' || alertsList.length > 0) {
    overallStatus = 'attention'
  }

  const hasTelemetry =
    (summaryData && Object.keys(summaryData).length > 0) ||
    (performanceData && Object.keys(performanceData).length > 0) ||
    (hardwareData && Object.keys(hardwareData).length > 0)
  if (!hasTelemetry && alertsList.length === 0) {
    return { overallStatus, lines: [] }
  }

  const alertCount = alertsList.length
  const severityWeight = sev => {
    const map = { critical: 3, high: 2, warning: 1, warn: 1 }
    return map[(sev || '').toLowerCase()] || 0
  }
  const severeAlert =
    alertCount > 0
      ? alertsList
        .slice()
        .sort((a, b) => severityWeight(b.severity) - severityWeight(a.severity))[0]
      : null

  const cpuPercent = performanceData?.cpu?.percent
  const cpuBucket =
    typeof cpuPercent === 'number'
      ? cpuPercent >= 85
        ? 'high'
        : cpuPercent >= 60
          ? 'moderate'
          : 'low'
      : 'unknown'
  const memoryPercent = performanceData?.memory?.percent
  const memoryDescriptor =
    typeof memoryPercent === 'number'
      ? `${memoryPercent.toFixed(0)}%`
      : performanceData?.memory
        ? formatMemory(performanceData.memory)
        : 'n/a'
  const usbBackend =
    hardwareData.usb_backend || summaryData?.hardware_status?.usb_backend || summaryData?.usb_backend

  lines.push(
    `Overall: ${hardwareStatus ? formatMetricLabel(hardwareStatus) : 'Unknown'} hardware, ${alertCount} active alert${alertCount === 1 ? '' : 's'
    }.`
  )
  lines.push(
    `Performance: CPU load ${cpuBucket}${typeof cpuPercent === 'number' ? ` (${cpuPercent.toFixed(0)}%)` : ''
    }, memory ${memoryDescriptor}.`
  )
  lines.push(
    alertCount
      ? `Alerts: ${severeAlert?.title || 'Review active alerts'}${severeAlert?.message ? ` – ${severeAlert.message}` : ''
      }`
      : 'Alerts: No active alerts detected.'
  )
  lines.push(`USB backend: ${usbBackend ? formatMetricLabel(usbBackend) : 'Unknown state'}.`)

  return { overallStatus, lines }
}

function formatTimeOfDay(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return value
  }
}
