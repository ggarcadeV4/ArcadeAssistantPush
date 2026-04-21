/**
 * SystemHealthPanel.jsx
 * Doc — System Health & Diagnostics Panel
 *
 * Redesigned to match Stitch mockup with deep navy telemetry aesthetic.
 * Chat handled by shared EngineeringBaySidebar (drawer overlay pattern).
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import EngineeringBaySidebar from '../_kit/EngineeringBaySidebar'
import { stopSpeaking } from '../../services/ttsClient'
import {
  fetchHealthSummary,
  fetchGatewayHealth,
  fetchHealthPerformance,
  fetchHealthProcesses,
  fetchHealthHardware,
  fetchHealthAlertsActive,
  fetchHealthAlertsHistory,
  runOptimizeAction,
  dismissHealthAlert
} from '../../services/systemHealthApi'
import './system-health.css'
import { docContextAssembler } from './docContextAssembler'

/* ═══════════════════════════════════════════════════════════════════════
   DOC PERSONA CONFIG
   ═══════════════════════════════════════════════════════════════════════ */

const DOC_PERSONA = {
  id: 'doc',
  name: 'Doc',
  chatEndpoint: '/api/local/doc/chat',
  icon: '🩺',
  avatar: '/doc-avatar.jpeg',
  accentColor: '#ec4899',
  accentGlow: 'rgba(236,72,153,0.35)',
  voiceProfile: 'doc',
  chips: [
    { label: '🔍 CPU Review', text: 'Give me a detailed CPU usage breakdown.' },
    { label: '🖥️ Hardware Check', text: 'What is the current status of all connected hardware?' },
    { label: '⚠️ Alert Triage', text: 'Summarize all active alerts and their severity.' },
    { label: '⚡ Optimize', text: 'Run a quick system optimization and report results.' }
  ],
  emptyHint: 'Ask Doc about performance, hardware, or diagnostics...'
}

/* ═══════════════════════════════════════════════════════════════════════
   SVG ICON HELPERS
   ═══════════════════════════════════════════════════════════════════════ */

const IconRefresh = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
  </svg>
)

const IconChat = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
  </svg>
)

const IconBolt = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M13 10V3L4 14h7v7l9-11h-7z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
  </svg>
)

const IconGrid = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
  </svg>
)

const IconChip = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m14-6h2m-2 6h2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
  </svg>
)

const IconAlert = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
  </svg>
)

const IconChevron = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M19 9l-7 7-7-7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
  </svg>
)

const IconSearch = () => (
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
  </svg>
)

const IconHeart = () => (
  <svg fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

/* ═══════════════════════════════════════════════════════════════════════
   CONSTANTS
   ═══════════════════════════════════════════════════════════════════════ */

const PERF_INTERVAL = 15_000
const PROCESS_INTERVAL = 30_000
const PROCESS_PREVIEW_LIMIT = 3
const TAB_ICONS = { performance: IconBolt, processes: IconGrid, hardware: IconChip, alerts: IconAlert }

/* ═══════════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════════════════ */

export default function SystemHealthPanel() {
  /* ── State ─────────────────────────────────────────────────────────── */
  const [activeTab, setActiveTab] = useState('performance')
  const [chatOpen, setChatOpen] = useState(false)

  /* Stop TTS when drawer closes — panel-level cutoff */
  const prevChatOpenRef = useRef(false)
  useEffect(() => {
    if (prevChatOpenRef.current && !chatOpen) {
      stopSpeaking()
    }
    prevChatOpenRef.current = chatOpen
  }, [chatOpen])

  // Summary
  const [summaryState, setSummaryState] = useState({ data: null, loading: false, error: null })
  const [gatewayState, setGatewayState] = useState({ data: null, loading: false, error: null })

  // Performance
  const [performanceState, setPerformanceState] = useState({ data: null, loading: false, error: null })
  const [autoRefreshPerformance, setAutoRefreshPerformance] = useState(true)
  const [performanceUpdatedAt, setPerformanceUpdatedAt] = useState(null)
  const [timeseriesState, setTimeseriesState] = useState({ data: null, loading: false, error: null })

  // Processes
  const [processState, setProcessState] = useState({ data: null, loading: false, error: null })
  const [autoRefreshProcesses, setAutoRefreshProcesses] = useState(false)
  const [processesUpdatedAt, setProcessesUpdatedAt] = useState(null)
  const [processFilter, setProcessFilter] = useState('')
  const [processSortBy, setProcessSortBy] = useState('cpu')
  const [showResourceHogs, setShowResourceHogs] = useState(false)
  const [expandedProcessGroups, setExpandedProcessGroups] = useState({})

  // Hardware
  const [hardwareData, setHardwareData] = useState(null)
  const [loadingHardware, setLoadingHardware] = useState(false)
  const [errorHardware, setErrorHardware] = useState(null)
  const [hardwareErrorDismissed, setHardwareErrorDismissed] = useState(false)
  const [hardwareFilter, setHardwareFilter] = useState('all')
  const [hardwareSearch, setHardwareSearch] = useState('')
  const [expandedCategories, setExpandedCategories] = useState({})

  // Alerts
  const [activeAlertsList, setActiveAlertsList] = useState([])
  const [alertHistoryList, setAlertHistoryList] = useState([])
  const [loadingAlerts, setLoadingAlerts] = useState(false)
  const [errorAlerts, setErrorAlerts] = useState(null)
  const [dismissingAlertId, setDismissingAlertId] = useState(null)

  // Optimize
  const [optimizeState, setOptimizeState] = useState({ pending: false, lastRun: null, message: null, error: null })

  /* ── Refs ──────────────────────────────────────────────────────────── */
  const perfTimerRef = useRef(null)
  const procTimerRef = useRef(null)

  /* ── Data loaders ─────────────────────────────────────────────────── */
  const loadSummary = useCallback(async () => {
    setSummaryState(s => ({ ...s, loading: true, error: null }))
    setGatewayState(s => ({ ...s, loading: true, error: null }))

    const [summaryResult, gatewayResult] = await Promise.allSettled([
      fetchHealthSummary(),
      fetchGatewayHealth()
    ])

    if (summaryResult.status === 'fulfilled') {
      setSummaryState({ data: summaryResult.value, loading: false, error: null })
    } else {
      setSummaryState(s => ({ ...s, loading: false, error: summaryResult.reason?.message || 'Failed' }))
    }

    if (gatewayResult.status === 'fulfilled') {
      setGatewayState({ data: gatewayResult.value, loading: false, error: null })
    } else {
      setGatewayState(s => ({ ...s, loading: false, error: gatewayResult.reason?.message || 'Failed' }))
    }
  }, [])

  const loadPerformance = useCallback(async () => {
    setPerformanceState(s => ({ ...s, loading: true, error: null }))
    try {
      const data = await fetchHealthPerformance()
      setPerformanceState({ data, loading: false, error: null })
      setPerformanceUpdatedAt(new Date().toISOString())
      // Accumulate time-series
      setTimeseriesState(prev => {
        const samples = prev.data ? [...prev.data] : []
        samples.push({
          timestamp: new Date().toISOString(),
          cpu_percent: data?.cpu?.percent,
          memory_percent: data?.memory?.percent,
          fps: data?.fps,
          latency_ms: data?.latency_ms
        })
        return { data: samples.slice(-5), loading: false, error: null }
      })
    } catch (err) {
      setPerformanceState(s => ({ ...s, loading: false, error: err.message || 'Failed' }))
    }
  }, [])

  const loadProcesses = useCallback(async () => {
    setProcessState(s => ({ ...s, loading: true, error: null }))
    try {
      const data = await fetchHealthProcesses()
      setProcessState({ data, loading: false, error: null })
      setProcessesUpdatedAt(new Date().toISOString())
    } catch (err) {
      setProcessState(s => ({ ...s, loading: false, error: err.message || 'Failed' }))
    }
  }, [])

  const loadHardware = useCallback(async () => {
    setLoadingHardware(true)
    setErrorHardware(null)
    try {
      const data = await fetchHealthHardware()
      setHardwareData(data)
    } catch (err) {
      setErrorHardware(err.message || 'Failed')
    } finally {
      setLoadingHardware(false)
    }
  }, [])

  const loadAlerts = useCallback(async () => {
    setLoadingAlerts(true)
    setErrorAlerts(null)
    try {
      const [active, history] = await Promise.all([
        fetchHealthAlertsActive(),
        fetchHealthAlertsHistory()
      ])
      setActiveAlertsList(Array.isArray(active) ? active : active?.alerts || [])
      setAlertHistoryList(Array.isArray(history) ? history : history?.alerts || [])
    } catch (err) {
      setErrorAlerts(err.message || 'Failed')
    } finally {
      setLoadingAlerts(false)
    }
  }, [])

  /* ── Initial load ─────────────────────────────────────────────────── */
  useEffect(() => {
    loadSummary()
    loadPerformance()
    loadProcesses()
    loadHardware()
    loadAlerts()
  }, [loadSummary, loadPerformance, loadProcesses, loadHardware, loadAlerts])

  /* ── Auto-refresh: Performance ────────────────────────────────────── */
  useEffect(() => {
    if (autoRefreshPerformance) {
      perfTimerRef.current = setInterval(loadPerformance, PERF_INTERVAL)
    }
    return () => clearInterval(perfTimerRef.current)
  }, [autoRefreshPerformance, loadPerformance])

  /* ── Auto-refresh: Processes ──────────────────────────────────────── */
  useEffect(() => {
    if (autoRefreshProcesses) {
      procTimerRef.current = setInterval(loadProcesses, PROCESS_INTERVAL)
    }
    return () => clearInterval(procTimerRef.current)
  }, [autoRefreshProcesses, loadProcesses])

  /* ── Handlers ─────────────────────────────────────────────────────── */
  const handleOptimize = useCallback(async () => {
    setOptimizeState(s => ({ ...s, pending: true, error: null, message: null }))
    try {
      const result = await runOptimizeAction()
      setOptimizeState({
        pending: false,
        lastRun: new Date().toISOString(),
        message: result?.message || 'Optimization queued.',
        error: null
      })
    } catch (err) {
      setOptimizeState(s => ({
        ...s,
        pending: false,
        error: err.message || 'Optimization request failed'
      }))
    }
  }, [])

  const handleDismissAlert = useCallback(async (alertId) => {
    setDismissingAlertId(alertId)
    try {
      await dismissHealthAlert(alertId)
      setActiveAlertsList(prev => prev.filter(a => a.id !== alertId))
    } catch {
      // Silent fail
    } finally {
      setDismissingAlertId(null)
    }
  }, [])

  const toggleProcessGroup = useCallback((groupId) => {
    setExpandedProcessGroups(prev => ({ ...prev, [groupId]: !prev[groupId] }))
  }, [])

  const handleRefreshAll = useCallback(() => {
    loadSummary()
    loadPerformance()
    loadProcesses()
    loadHardware()
    loadAlerts()
  }, [loadSummary, loadPerformance, loadProcesses, loadHardware, loadAlerts])

  /* ── Derived data ─────────────────────────────────────────────────── */
  const summaryData = summaryState.data || {}
  const timeseriesSamples = timeseriesState.data || []

  // Truth cards
  const truthCards = useMemo(() => buildTruthCards(summaryState.data, gatewayState.data, gatewayState.error), [summaryState.data, gatewayState.data, gatewayState.error])

  // Quick diagnosis
  const docQuickDiagnosis = useMemo(() => {
    return buildDocQuickDiagnosis({
      summary: summaryState.data,
      performance: performanceState.data,
      hardware: hardwareData,
      alerts: activeAlertsList,
      gateway: gatewayState.data,
      gatewayError: gatewayState.error
    })
  }, [summaryState.data, performanceState.data, hardwareData, activeAlertsList, gatewayState.data, gatewayState.error])

  // Performance metrics
  const performanceMetrics = useMemo(() => {
    const p = performanceState.data
    if (!p) return []
    return [
      { label: 'CPU Usage', value: formatPercent(p.cpu?.percent), sublabel: p.cpu?.cores ? `${p.cpu.cores} cores` : '' },
      { label: 'Memory', value: formatMemory(p.memory), sublabel: p.memory?.percent != null ? `${p.memory.percent.toFixed(0)}% used` : '' },
      { label: 'FPS', value: p.fps != null ? p.fps.toFixed(1) : '--', sublabel: 'Average' },
      { label: 'Latency', value: p.latency_ms != null ? `${p.latency_ms.toFixed(1)} ms` : '--', sublabel: 'Input' },
      { label: 'Disk', value: p.disk?.percent != null ? formatPercent(p.disk.percent) : '--', sublabel: p.disk?.percent != null ? (p.disk?.io_read ? 'Active' : 'Ready') : 'Unavailable' },
      { label: 'Network', value: p.network?.latency_ms != null ? `${p.network.latency_ms.toFixed(0)} ms` : '--', sublabel: 'Round-trip' }
    ]
  }, [performanceState.data])

  // Performance insights
  const performanceInsights = useMemo(() => {
    const p = performanceState.data
    if (!p) return []
    const insights = []
    const cpu = p.cpu?.percent
    if (typeof cpu === 'number') {
      if (cpu > 80) insights.push({ title: 'High CPU Load', description: `CPU is at ${cpu.toFixed(0)}%. Consider closing background processes.` })
      else if (cpu < 30) insights.push({ title: 'CPU Load Normal', description: `CPU is running at a comfortable ${cpu.toFixed(0)}%.` })
    }
    const mem = p.memory?.percent
    if (typeof mem === 'number' && mem > 75) {
      insights.push({ title: 'Memory Pressure', description: `Memory usage at ${mem.toFixed(0)}%. May impact game performance.` })
    }
    if (p.fps != null && p.fps < 30) {
      insights.push({ title: 'Low Frame Rate', description: `Average FPS is ${p.fps.toFixed(1)}. Check GPU utilization.` })
    }
    if (p.fps == null && p.latency_ms == null) {
      insights.push({ title: 'Gameplay Telemetry Limited', description: 'CPU, memory, and disk checks are live, but frame-rate and input-latency probes are not currently wired on this cabinet.' })
    }
    if (!insights.length) {
      insights.push({ title: 'All Systems Nominal', description: 'Performance metrics are within healthy ranges.' })
    }
    return insights
  }, [performanceState.data])

  // Process groups
  const processGroups = useMemo(() => {
    const rawGroups = Array.isArray(processState.data?.groups)
      ? processState.data.groups
      : Array.isArray(processState.data)
        ? processState.data
        : []
    if (!rawGroups.length) return []
    const sortFn = processSortBy === 'memory'
      ? (a, b) => (b.memory_bytes || 0) - (a.memory_bytes || 0)
      : (a, b) => (b.cpu_percent || 0) - (a.cpu_percent || 0)
    return rawGroups.map(group => ({
      id: group.id || group.title || 'group',
      title: group.title || 'Processes',
      processes: [...(group.processes || [])].sort(sortFn)
    }))
  }, [processState.data, processSortBy])

  const processesUnavailable = processState.data?.unavailable === true || processState.data?.psutil_available === false

  const filteredProcessGroups = useMemo(() => {
    const filterLower = processFilter.toLowerCase()
    return processGroups.map(group => ({
      ...group,
      processes: group.processes.filter(proc => {
        if (showResourceHogs) {
          const isHeavy = (proc.cpu_percent || 0) >= 50 || (proc.memory_bytes || 0) >= 512 * 1024 * 1024
          if (!isHeavy) return false
        }
        if (!filterLower) return true
        return (proc.name || '').toLowerCase().includes(filterLower) ||
               (proc.path || '').toLowerCase().includes(filterLower) ||
               String(proc.pid || '').includes(filterLower)
      })
    })).filter(group => group.processes.length > 0)
  }, [processGroups, processFilter, showResourceHogs])

  const processOverview = useMemo(() => {
    const all = processGroups.flatMap(g => g.processes)
    return {
      total: all.length,
      heavy: all.filter(p => (p.cpu_percent || 0) >= 50 || (p.memory_bytes || 0) >= 512 * 1024 * 1024).length,
      timestamp: processesUpdatedAt
    }
  }, [processGroups, processesUpdatedAt])

  // Hardware categories
  const hardwareCategories = useMemo(() => {
    if (!hardwareData?.categories) return []
    return (hardwareData.categories || []).map(cat => ({
      id: cat.id || cat.title,
      title: cat.title || 'Unknown',
      devices: cat.devices || []
    }))
  }, [hardwareData])

  const filteredHardwareCategories = useMemo(() => {
    const searchLower = hardwareSearch.toLowerCase()
    return hardwareCategories.map(cat => ({
      ...cat,
      devices: cat.devices.filter(device => {
        const status = (device.status || '').toLowerCase()
        if (hardwareFilter !== 'all' && status !== hardwareFilter) return false
        if (searchLower) {
          return (device.name || '').toLowerCase().includes(searchLower) ||
                 (device.id || '').toLowerCase().includes(searchLower)
        }
        return true
      })
    })).filter(cat => cat.devices.length > 0)
  }, [hardwareCategories, hardwareFilter, hardwareSearch])

  const hardwareStats = useMemo(() => {
    const all = hardwareCategories.flatMap(c => c.devices)
    return {
      connected: all.filter(d => (d.status || '').toLowerCase() === 'connected').length,
      warning: all.filter(d => (d.status || '').toLowerCase() === 'warning').length,
      disconnected: all.filter(d => (d.status || '').toLowerCase() === 'disconnected').length
    }
  }, [hardwareCategories])

  const hardwareStatus = (hardwareData?.status || 'healthy').toLowerCase()
  const hardwareStatusLabel = formatMetricLabel(hardwareStatus)
  const hardwareUsbBackend = hardwareData?.usb_backend
  const hardwareOperatorMessage = formatOperatorMessage(hardwareData?.error)

  /* ═══════════════════════════════════════════════════════════════════
     RENDER
     ═══════════════════════════════════════════════════════════════════ */
  return (
    <div className="doc-panel">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="doc-header">
        <div className="doc-header__left">
          <span className="doc-header__icon"><IconHeart /></span>
          <div>
            <h1 className="doc-header__title">System Health Panel</h1>
            <p className="doc-header__subtitle">Live telemetry for Doc</p>
          </div>
        </div>
        <div className="doc-header__actions">
          <button className="doc-btn" onClick={handleRefreshAll}>
            <IconRefresh /> Refresh Data
          </button>
          <button
            className={`doc-btn--primary doc-btn ${chatOpen ? 'doc-chat-toggle--open' : ''}`}
            onClick={() => setChatOpen(!chatOpen)}
          >
            <IconChat /> Ask Doc
          </button>
        </div>
      </header>

      {/* ── Scrollable Content ──────────────────────────────────────── */}
      <div className="doc-content">

        {/* Status Cards */}
        <section className="doc-status-grid">
          {truthCards.map(card => (
            <div key={card.label} className="doc-status-card">
              <div className={`doc-status-card__dot ${card.tone === 'warning' ? 'doc-status-card__dot--warn' : card.tone === 'error' ? 'doc-status-card__dot--error' : ''}`} />
              <div className="doc-status-card__label">{card.label}</div>
              <div className="doc-status-card__value">{card.value}</div>
              {card.meta && <div className="doc-status-card__meta">{card.meta}</div>}
            </div>
          ))}
        </section>

        {/* Diagnosis Banner */}
        <section className={`doc-diagnosis-banner doc-diagnosis-banner--${docQuickDiagnosis.overallStatus || 'healthy'}`}>
          <div className="doc-diagnosis-header">
            <h2>Doc&apos;s Quick Diagnosis</h2>
            <span className={`doc-diagnosis-badge doc-diagnosis-badge--${docQuickDiagnosis.overallStatus || 'healthy'}`}>
              {(docQuickDiagnosis.overallStatus || 'healthy').toUpperCase()}
            </span>
          </div>
          {docQuickDiagnosis.lines.length > 0 ? (
            <ul className="doc-diagnosis-lines">
              {docQuickDiagnosis.lines.map((line, i) => (
                <li key={i} dangerouslySetInnerHTML={{ __html: formatDiagnosisLine(line) }} />
              ))}
            </ul>
          ) : (
            <div className="doc-diagnosis-loading">Gathering telemetry...</div>
          )}
        </section>

        {/* Tab Bar */}
        <div className="doc-tab-bar">
          <nav className="doc-tab-bar__tabs">
            {['performance', 'processes', 'hardware', 'alerts'].map(tab => {
              const Icon = TAB_ICONS[tab]
              return (
                <button
                  key={tab}
                  className={`doc-tab ${activeTab === tab ? 'doc-tab--active' : ''}`}
                  onClick={() => setActiveTab(tab)}
                >
                  <Icon />
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </button>
              )
            })}
          </nav>
          <div className="doc-tab-bar__actions">
            <button className="doc-btn" onClick={handleRefreshAll} style={{ fontSize: 12, padding: '6px 12px' }}>
              <IconRefresh /> Refresh
            </button>
          </div>
        </div>

        {/* ── Performance Tab ────────────────────────────────────────── */}
        {activeTab === 'performance' && (
          <div className="doc-tab-content">
            <div className="doc-perf-header">
              <div>
                <h2>Gaming Performance Monitor</h2>
                <div className="doc-perf-status">
                  <span className="doc-status-dot" />
                  <span>Last updated: {performanceUpdatedAt ? formatTimeOfDay(performanceUpdatedAt) : 'calibrating...'}</span>
                </div>
              </div>
              <div className="doc-perf-controls">
                <label className={`doc-toggle ${autoRefreshPerformance ? 'active' : ''}`}>
                  <input type="checkbox" checked={autoRefreshPerformance} onChange={e => setAutoRefreshPerformance(e.target.checked)} />
                  Auto-refresh
                </label>
                <span className="doc-perf-meta">Samples: {timeseriesSamples.length}</span>
              </div>
            </div>

            {/* Optimize card */}
            <div className="doc-optimize-card">
              <div className="doc-optimize-copy">
                <h4>Doc Auto Optimize</h4>
                <p>Queues a safe tune-up via the backend (cache cleanup, telemetry recalibration, USB sanity checks).</p>
                <div className="doc-optimize-meta">
                  <span>Last request: {optimizeState.lastRun ? formatTimestamp(optimizeState.lastRun) : 'Not requested yet'}</span>
                  {optimizeState.message && <span className="doc-optimize-hint">{optimizeState.message}</span>}
                  {optimizeState.error && <span className="doc-optimize-error">Error: {optimizeState.error}</span>}
                </div>
              </div>
              <button className="doc-optimize-btn" onClick={handleOptimize} disabled={optimizeState.pending}>
                {optimizeState.pending ? 'Queuing...' : 'Run Quick Optimization'}
              </button>
            </div>

            {/* Metrics grid */}
            <div className="doc-metrics-grid">
              {performanceState.loading && !performanceState.data && (
                <div className="doc-metric-card">Loading performance...</div>
              )}
              {performanceState.error && !performanceState.data && (
                <div className="doc-error">{performanceState.error}</div>
              )}
              {performanceMetrics.map(m => (
                <div key={m.label} className="doc-metric-card">
                  <div className="doc-metric-value">{m.value}</div>
                  <div className="doc-metric-label">{m.label}</div>
                  <div className="doc-metric-sublabel">{m.sublabel}</div>
                </div>
              ))}
            </div>

            {/* Samples table */}
            <div className="doc-samples-section">
              <h3>Recent Samples (last 5 entries)</h3>
              {timeseriesState.loading && !timeseriesSamples.length && <div className="doc-empty">Loading samples...</div>}
              {timeseriesSamples.length > 0 && (
                <table className="doc-samples-table">
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
                    {timeseriesSamples.map(s => (
                      <tr key={s.timestamp}>
                        <td>{formatTimestamp(s.timestamp)}</td>
                        <td>{formatPercent(s.cpu_percent)}</td>
                        <td>{formatPercent(s.memory_percent)}</td>
                        <td>{s.fps != null ? s.fps.toFixed(1) : '--'}</td>
                        <td>{s.latency_ms != null ? `${s.latency_ms.toFixed(1)} ms` : '--'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Insights */}
            <div className="doc-insights-panel">
              <h3>Performance Insights</h3>
              <div className="doc-insights-list">
                {performanceInsights.map(insight => (
                  <div key={insight.title} className="doc-insight-item">
                    <div className="doc-insight-title">{insight.title}</div>
                    <div className="doc-insight-desc">{insight.description}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── Processes Tab ──────────────────────────────────────────── */}
        {activeTab === 'processes' && (
          <div className="doc-tab-content">
            <div className="doc-process-toolbar">
              <div className="doc-process-search">
                <span className="doc-process-search__icon"><IconSearch /></span>
                <input
                  type="text"
                  value={processFilter}
                  onChange={e => setProcessFilter(e.target.value)}
                  placeholder="Filter processes by name or path"
                />
              </div>
              <div className="doc-process-filters">
                <label className={`doc-toggle ${showResourceHogs ? 'active' : ''}`}>
                  <span>Show heavy usage only</span>
                  <input type="checkbox" checked={showResourceHogs} onChange={e => setShowResourceHogs(e.target.checked)} />
                </label>
                <button className="doc-btn" onClick={loadProcesses} disabled={processState.loading}>
                  <IconRefresh /> {processState.loading ? 'Refreshing...' : 'Refresh Processes'}
                </button>
              </div>
            </div>

            {processesUnavailable && (
              <div className="doc-error">Process metrics unavailable on this platform.</div>
            )}
            {processState.error && (
              <div className="doc-error">Error: {processState.error}</div>
            )}

            <div className="doc-process-table-wrap">
              {filteredProcessGroups.length === 0 && !processState.loading && (
                <div className="doc-empty">No processes match the current filters.</div>
              )}
              {filteredProcessGroups.map(group => {
                const isExpanded = expandedProcessGroups[group.id] || false
                const visibleProcesses = isExpanded
                  ? group.processes
                  : group.processes.slice(0, PROCESS_PREVIEW_LIMIT)
                const hiddenCount = group.processes.length - visibleProcesses.length
                return (
                  <div key={group.id}>
                    <div
                      className={`doc-process-section-header ${isExpanded ? 'expanded' : ''}`}
                      onClick={() => toggleProcessGroup(group.id)}
                    >
                      <IconChevron />
                      {group.title} <span className="doc-process-section-count">({group.processes.length})</span>
                    </div>
                    <table className="doc-process-table">
                      <thead>
                        <tr>
                          <th style={{ width: '25%' }}>Name</th>
                          <th style={{ width: '33%' }}>Path</th>
                          <th style={{ width: '12%' }}>Health (CPU)</th>
                          <th style={{ width: '12%' }}>Health (Mem)</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleProcesses.map(proc => (
                          <ProcessRow key={`${group.id}-${proc.pid}-${proc.name}`} process={proc} />
                        ))}
                      </tbody>
                    </table>
                    {!isExpanded && hiddenCount > 0 && (
                      <button className="doc-process-showmore" onClick={() => toggleProcessGroup(group.id)}>
                        Show {hiddenCount} more
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* ── Hardware Tab ───────────────────────────────────────────── */}
        {activeTab === 'hardware' && (
          <div className="doc-tab-content">
            <div className="doc-hw-toolbar">
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
              <button className="doc-btn" onClick={loadHardware} disabled={loadingHardware}>
                <IconRefresh /> {loadingHardware ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>

            {hardwareOperatorMessage && !hardwareErrorDismissed && (
              <div className="doc-banner-warn">
                <span>Hardware checks are limited: {hardwareOperatorMessage}</span>
                <button onClick={() => setHardwareErrorDismissed(true)}>Dismiss</button>
              </div>
            )}

            <div className="doc-hw-stats">
              <span>Connected: {hardwareStats.connected}</span>
              <span>Warnings: {hardwareStats.warning}</span>
              <span>Disconnected: {hardwareStats.disconnected}</span>
            </div>

            {loadingHardware && !hardwareCategories.length && <div className="doc-empty">Loading hardware...</div>}
            {errorHardware && !hardwareCategories.length && <div className="doc-error">Error: {errorHardware}</div>}

            <div className="doc-hw-grid">
              {filteredHardwareCategories.length === 0 && !loadingHardware && (
                <div className="doc-empty">No devices match the selected filters.</div>
              )}
              {filteredHardwareCategories.map(category => {
                const issueDevices = (category.devices || []).filter(d => {
                  const s = (d.status || '').toLowerCase()
                  return s === 'warning' || s === 'disconnected'
                })
                return (
                  <div key={category.id} className="doc-hw-category">
                    <div
                      className="doc-hw-category__header"
                      onClick={() => setExpandedCategories(prev => ({ ...prev, [category.id]: !prev[category.id] }))}
                    >
                      <span className="doc-hw-category__title">{category.title}</span>
                      <div className="doc-hw-category__badges">
                        <span className="doc-hw-badge doc-hw-badge--count">{category.devices.length} DEVICES</span>
                        <span className={`doc-hw-badge ${issueDevices.length ? 'doc-hw-badge--issues' : 'doc-hw-badge--ok'}`}>
                          {issueDevices.length ? 'ISSUES DETECTED' : 'ALL CLEAR'}
                        </span>
                      </div>
                    </div>
                    {(expandedCategories[category.id] !== false) && (
                      <div className="doc-hw-devices">
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

        {/* ── Alerts Tab ────────────────────────────────────────────── */}
        {activeTab === 'alerts' && (
          <div className="doc-tab-content">
            <div className="doc-alerts-toolbar">
              <button className="doc-btn" onClick={loadAlerts} disabled={loadingAlerts}>
                <IconRefresh /> {loadingAlerts ? 'Refreshing...' : 'Refresh Alerts'}
              </button>
            </div>
            {errorAlerts && <div className="doc-error">Error: {errorAlerts}</div>}
            <div className="doc-alerts-layout">
              <div className="doc-alert-section">
                <div className="doc-alert-section__header">
                  <h3>Active Alerts</h3>
                  <span className="doc-alert-count">{activeAlertsList.length}</span>
                </div>
                {loadingAlerts && !activeAlertsList.length && <div className="doc-empty">Loading alerts...</div>}
                <div className="doc-alert-list">
                  {!loadingAlerts && !errorAlerts && activeAlertsList.length === 0 && (
                    <div className="doc-empty">No active alerts</div>
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
              <div className="doc-alert-section">
                <div className="doc-alert-section__header">
                  <h3>Alert History</h3>
                  <span className="doc-alert-count">{alertHistoryList.length}</span>
                </div>
                {loadingAlerts && !alertHistoryList.length && <div className="doc-empty">Loading history...</div>}
                <div className="doc-alert-list">
                  {!loadingAlerts && !errorAlerts && alertHistoryList.length === 0 && (
                    <div className="doc-empty">No historical alerts logged</div>
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

      {/* ── Chat Drawer Overlay ─────────────────────────────────────── */}
      <div
        className={`eb-chat-backdrop ${chatOpen ? 'eb-chat-backdrop--visible' : ''}`}
        onClick={() => setChatOpen(false)}
      />
      <aside className={`eb-chat-drawer ${chatOpen ? 'eb-chat-drawer--open' : ''}`}>
        <button className="eb-chat-drawer__close" onClick={() => setChatOpen(false)}>✕</button>
        <EngineeringBaySidebar
          persona={DOC_PERSONA}
          contextAssembler={docContextAssembler}
        />
      </aside>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
   SUB-COMPONENTS
   ═══════════════════════════════════════════════════════════════════════ */

function ProcessRow({ process }) {
  const cpu = typeof process.cpu_percent === 'number' ? process.cpu_percent : 0
  const memory = typeof process.memory_bytes === 'number' ? formatBytes(process.memory_bytes) : '--'
  const healthPercent = Math.round((process.health ?? 0) * 100)
  const isWarn = cpu >= 50 || (process.memory_bytes || 0) >= 512 * 1024 * 1024
  const barColor = isWarn ? 'doc-health-bar__fill--pink' : 'doc-health-bar__fill--cyan'
  const badgeClass = isWarn ? 'doc-status-badge--warn' : 'doc-status-badge--healthy'
  const badgeLabel = isWarn ? 'WARN' : 'HEALTHY'

  return (
    <tr>
      <td className="doc-process-name">{process.name || 'Unknown Process'}</td>
      <td className="doc-process-path">{process.path || 'n/a'}</td>
      <td>{cpu.toFixed(1)}%</td>
      <td>{memory}</td>
      <td>
        <div className="doc-health-bar">
          <div className="doc-health-bar__track">
            <div className={`doc-health-bar__fill ${barColor}`} style={{ width: `${Math.min(100, healthPercent)}%` }} />
          </div>
          <span className="doc-health-bar__pct">{healthPercent}%</span>
          <span className={`doc-status-badge ${badgeClass}`}>{badgeLabel}</span>
        </div>
      </td>
    </tr>
  )
}

function HardwareDevice({ device }) {
  const status = (device.status || '').toLowerCase()
  const healthPercent = device.health != null ? Math.round(device.health * 100) : null
  const healthFill = healthPercent != null
    ? healthPercent > 85 ? 'doc-device-health-fill--green'
    : healthPercent > 70 ? 'doc-device-health-fill--yellow'
    : 'doc-device-health-fill--red'
    : ''
  const statusBadge = status === 'connected' ? 'doc-status-badge--healthy'
    : status === 'warning' ? 'doc-status-badge--warn'
    : 'doc-status-badge--error'
  const metrics = device.metrics
    ? Object.entries(device.metrics).map(([key, value]) => ({
        label: formatMetricLabel(key),
        value: typeof value === 'number' ? value : String(value)
      }))
    : []

  return (
    <div className="doc-device-item">
      <div className="doc-device-item__header">
        <div>
          <div className="doc-device-item__name">{device.name || 'Device'}</div>
          <div className="doc-device-item__specs">
            {metrics.map(m => (
              <span key={m.label}>{m.label}: {m.value}</span>
            ))}
          </div>
        </div>
        <span className={`doc-status-badge ${statusBadge}`}>
          {status ? status.toUpperCase() : 'UNKNOWN'}
        </span>
      </div>
      {healthPercent != null && (
        <div className="doc-device-item__health">
          <div className="doc-device-health-track">
            <div className={`doc-device-health-fill ${healthFill}`} style={{ width: `${Math.min(100, healthPercent)}%` }} />
          </div>
          <span className="doc-device-health-pct">{healthPercent}%</span>
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
    <div className={`doc-alert-item doc-alert-item--${severity}`}>
      <div className="doc-alert-item__header">
        <div className="doc-alert-item__title">
          {alert.title}{sourceLabel && ` (${sourceLabel})`}
        </div>
        <div className="doc-alert-item__time">{formatTimestamp(timestamp)}</div>
      </div>
      <div className="doc-alert-item__message">{alert.message}</div>
      {showActions && (
        <div className="doc-alert-item__actions">
          <button className="doc-alert-dismiss-btn" onClick={() => onDismiss(alert.id)} disabled={dismissing}>
            {dismissing ? 'Dismissing...' : 'Dismiss'}
          </button>
        </div>
      )}
      {compact && (
        <div className="doc-alert-item__meta">
          {alert.dismissed_at && <div>Dismissed {formatTimestamp(alert.dismissed_at)}</div>}
          {alert.reason && <div>Reason: {alert.reason}</div>}
        </div>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
   UTILITY FUNCTIONS
   ═══════════════════════════════════════════════════════════════════════ */

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
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

function formatTimestamp(value) {
  if (!value) return 'n/a'
  try { return new Date(value).toLocaleString() }
  catch { return value }
}

function formatTimeOfDay(value) {
  if (!value) return ''
  try { return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
  catch { return value }
}

function formatMetricLabel(label) {
  return label.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatDiagnosisLine(line) {
  // Bold labels and highlight "warning" / "critical" keywords
  return line
    .replace(/^(Overall|Gateway|Configured Root|Manifest|LaunchBox|Plugin|Emulators|ROM Folders|BIOS|Performance|Alerts|USB backend|CPU|Memory|Hardware):?/i, '<strong>$1:</strong>')
    .replace(/\bwarning\b/gi, '<span class="text-warn">warning</span>')
    .replace(/\bcritical\b/gi, '<span style="color:var(--doc-red)">critical</span>')
}

function buildDocQuickDiagnosis({ summary = {}, performance = {}, hardware = {}, alerts = [], gateway = null, gatewayError = null } = {}) {
  const summaryData = summary || {}
  const performanceData = performance || {}
  const hardwareData = hardware || {}
  const alertsList = Array.isArray(alerts) ? alerts : []
  const dependencies = summaryData.dependencies || {}
  const dependencyOverview = summaryData.dependency_overview || {}
  const gatewayStatus = resolveGatewayStatus(gateway, gatewayError)
  const lines = []
  const overallSeverity = worstStatusLabel([
    dependencyOverview.status,
    gatewayStatus.status,
    hardwareData.status === 'degraded' ? 'warning' : 'ok',
    alertsList.length > 0 ? 'warning' : 'ok'
  ])
  const overallStatus = overallSeverity === 'error' ? 'attention' : overallSeverity === 'warning' ? 'degraded' : 'healthy'

  const hasTelemetry =
    (summaryData && Object.keys(summaryData).length > 0) ||
    (performanceData && Object.keys(performanceData).length > 0) ||
    (hardwareData && Object.keys(hardwareData).length > 0) ||
    gateway != null
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
      ? alertsList.slice().sort((a, b) => severityWeight(b.severity) - severityWeight(a.severity))[0]
      : null

  const cpuPercent = performanceData?.cpu?.percent
  const cpuBucket =
    typeof cpuPercent === 'number'
      ? cpuPercent >= 85 ? 'high' : cpuPercent >= 60 ? 'moderate' : 'low'
      : 'unknown'
  const memoryPercent = performanceData?.memory?.percent
  const memoryDescriptor =
    typeof memoryPercent === 'number'
      ? `${memoryPercent.toFixed(0)}%`
      : performanceData?.memory ? formatMemory(performanceData.memory) : 'n/a'
  const usbBackend =
    hardwareData.usb_backend || summaryData?.hardware_status?.usb_backend || summaryData?.usb_backend

  lines.push(`Overall: ${formatOverallSummary(dependencyOverview, alertCount)}.`)
  lines.push(`Gateway: ${gatewayStatus.summary}.`)
  if (dependencies.configured_root?.summary) lines.push(`Configured Root: ${dependencies.configured_root.summary}.`)
  if (dependencies.manifest?.summary) lines.push(`Manifest: ${dependencies.manifest.summary}.`)
  if (dependencies.launchbox?.summary) lines.push(`LaunchBox: ${dependencies.launchbox.summary}.`)
  if (dependencies.plugin?.summary) lines.push(`Plugin: ${dependencies.plugin.summary}.`)
  if (dependencies.emulators?.summary) lines.push(`Emulators: ${dependencies.emulators.summary}.`)
  if (dependencies.roms?.summary) lines.push(`ROM Folders: ${dependencies.roms.summary}.`)
  if (dependencies.bios?.summary) lines.push(`BIOS: ${dependencies.bios.summary}.`)
  lines.push(`Performance: CPU load ${cpuBucket}${typeof cpuPercent === 'number' ? ` (${cpuPercent.toFixed(0)}%)` : ''}, memory ${memoryDescriptor}.`)
  lines.push(
    alertCount
      ? `Alerts: ${severeAlert?.title || 'Review active alerts'}${severeAlert?.message ? ` – ${severeAlert.message}` : ''}`
      : 'Alerts: No active alerts detected.'
  )
  if (usbBackend) {
    lines.push(`USB backend: ${formatMetricLabel(usbBackend)}.`)
  }

  return { overallStatus, lines }
}

function buildTruthCards(summary, gateway, gatewayError) {
  const dependencyChecks = summary?.dependencies || {}
  const cards = [
    buildCardFromCheck('Gateway / Backend', resolveGatewayStatus(gateway, gatewayError)),
    buildCardFromCheck('Configured Root', dependencyChecks.configured_root),
    buildCardFromCheck('Manifest', dependencyChecks.manifest),
    buildCardFromCheck('LaunchBox', dependencyChecks.launchbox),
    buildCardFromCheck('Plugin Bridge', dependencyChecks.plugin),
    buildCardFromCheck('Emulator Paths', dependencyChecks.emulators),
    buildCardFromCheck('ROM Folders', dependencyChecks.roms),
    buildCardFromCheck('BIOS', dependencyChecks.bios)
  ]

  return cards.filter(Boolean)
}

function buildCardFromCheck(label, check) {
  if (!check) {
    return {
      label,
      value: 'Checking',
      meta: 'Waiting for live status...',
      tone: 'warning'
    }
  }

  return {
    label,
    value: formatCheckValue(check.status),
    meta: check.summary || check.detail || null,
    tone: normalizeTone(check.status)
  }
}

function resolveGatewayStatus(gateway, gatewayError) {
  if (gatewayError) {
    return {
      status: 'error',
      summary: 'Gateway health could not be loaded',
      detail: formatOperatorMessage(gatewayError)
    }
  }

  if (!gateway) {
    return {
      status: 'warning',
      summary: 'Checking gateway to backend link',
      detail: null
    }
  }

  if (gateway.fastapi?.connected) {
    return {
      status: 'ok',
      summary: 'Gateway is online and backend communication is healthy',
      detail: gateway.fastapi?.url || null
    }
  }

  return {
    status: 'error',
    summary: 'Gateway is online, but the backend is unreachable',
    detail: formatOperatorMessage(gateway.fastapi?.error) || gateway.fastapi?.url || null
  }
}

function formatCheckValue(status) {
  switch ((status || '').toLowerCase()) {
    case 'ok':
      return 'Healthy'
    case 'error':
      return 'Action Needed'
    case 'warning':
    default:
      return 'Attention'
  }
}

function normalizeTone(status) {
  const normalized = (status || '').toLowerCase()
  if (normalized === 'ok') return 'ok'
  if (normalized === 'error') return 'error'
  return 'warning'
}

function worstStatusLabel(statuses = []) {
  const rank = value => {
    if (value === 'error') return 2
    if (value === 'warning') return 1
    return 0
  }

  return statuses.reduce((current, candidate) => (rank(candidate) > rank(current) ? candidate : current), 'ok') || 'ok'
}

function formatOverallSummary(overview = {}, alertCount = 0) {
  const okCount = overview.ok_count || 0
  const warningCount = overview.warning_count || 0
  const errorCount = overview.error_count || 0

  if (errorCount > 0) {
    return `${errorCount} cabinet dependencies need operator attention${alertCount ? `, plus ${alertCount} active alert${alertCount === 1 ? '' : 's'}` : ''}`
  }
  if (warningCount > 0) {
    return `${warningCount} cabinet dependencies are degraded${alertCount ? `, plus ${alertCount} active alert${alertCount === 1 ? '' : 's'}` : ''}`
  }
  if (okCount > 0) {
    return `All ${okCount} cabinet dependency checks are healthy${alertCount ? `, with ${alertCount} active alert${alertCount === 1 ? '' : 's'}` : ''}`
  }
  return 'Cabinet dependency status is still loading'
}

function formatOperatorMessage(message) {
  const text = String(message || '').trim()
  if (!text) return ''

  const lower = text.toLowerCase()
  if (lower.includes('usb backend unavailable')) {
    return 'USB scanning is unavailable in this runtime, so controller detection is limited.'
  }
  if (lower.includes('permission denied')) {
    return 'USB scanning does not currently have permission to inspect attached devices.'
  }
  if (lower.includes('detector unavailable')) {
    return 'Hardware detection is not available in this runtime.'
  }
  if (lower.includes('fastapi url not configured')) {
    return 'The gateway is missing its backend target configuration.'
  }
  if (lower.includes('failed to fetch') || lower.includes('networkerror')) {
    return 'The gateway could not reach the backend health endpoint.'
  }

  return text
}
