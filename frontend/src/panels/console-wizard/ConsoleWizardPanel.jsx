import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import './console-wizard.css';
import { speak as ttsSpeak, stopSpeaking as stopTTS } from '../../services/ttsClient';
import { EngineeringBaySidebar } from '../_kit/EngineeringBaySidebar';
import '../_kit/EngineeringBaySidebar.css';
import { ExecutionCard } from '../controller/ExecutionCard';
import { assembleWizContext } from './wizContextAssembler';
import { WIZ_CHIPS } from './wizChips';
import WizNavSidebar from './WizNavSidebar';

/** WIZ persona config for EngineeringBaySidebar */
const WIZ_PERSONA = {
  id: 'wiz',
  name: 'WIZ',
  icon: '🕹️',
  icon2: '🎮',
  accentColor: '#a78bfa',
  accentGlow: 'rgba(167,139,250,0.35)',
  scannerLabel: 'CONJURING...',
  voiceProfile: 'wiz',
  emptyHint: 'Ask WIZ about emulator configs, controller mapping, or RetroArch setup.',
  chips: WIZ_CHIPS,
};
import DashboardTab from './DashboardTab';
import VisualDiffTab from './VisualDiffTab';
import ActivityLogTab from './ActivityLogTab';
import GamepadSetupOverlay from './GamepadSetupOverlay';

const arrayBufferToBase64 = (buffer) => {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  if (typeof window !== 'undefined' && typeof window.btoa === 'function') {
    return window.btoa(binary);
  }
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(binary, 'binary').toString('base64');
  }
  throw new Error('No base64 encoder available');
};

/**
 * Helper to select the best supported audio format for MediaRecorder.
 * @returns {object|undefined} Options object with mimeType, or undefined.
 */
function pickRecorderOptions() {
  if (!window?.MediaRecorder) {
    return undefined;
  }
  if (typeof window.MediaRecorder.isTypeSupported !== 'function') {
    return undefined;
  }
  const preferred = ['audio/wav', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
  const supported = preferred.find(type => window.MediaRecorder.isTypeSupported(type));
  return supported ? { mimeType: supported } : undefined;
}

/**
 * Console Wizard Panel - Backend Integration Update
 *
 * This panel was updated to align with the backend API contract defined in
 * backend/routers/console_wizard.py. Key changes:
 *
 * 1. Endpoint URLs updated to match backend routes:
 *    - /emulators/scan ? /emulators
 *    - /configs/preview + /configs/apply ? /generate-configs (with dry_run param)
 *    - /sync_from_chuck/preview + /sync_from_chuck/apply ? /sync-from-chuck
 *    - /restore/all ? /restore-all
 *    - /defaults/set ? /set-defaults
 *
 * 2. Preview/Apply pattern changed to dry_run parameter approach:
 *    - Preview: calls endpoint with dry_run=true
 *    - Apply: calls endpoint with dry_run=false
 *
 * 3. Chuck sync status monitoring temporarily disabled:
 *    - Backend /status/chuck endpoint not yet implemented
 *    - Sync banner hidden until backend support is added
 *
 * 4. Response transformation added:
 *    - Backend returns {results: [...]} format
 *    - Frontend expects {emulators: [...], preview: {...}} format
 *    - Added normalizeEmulator() and inline transformations
 *
 * See: backend/services/console_wizard_manager.py for backend implementation
 */

/**
 * @typedef {Object} ConsoleWizardEmulator
 * @property {string} id
 * @property {string} displayName
 * @property {'retroarch_core' | 'standalone' | 'other'} type
 * @property {string[]} systems
 * @property {'INI' | 'XML' | 'JSON' | 'CFG' | 'PROPRIETARY'} configFormat
 * @property {string} inputNamingConvention
 * @property {'ok' | 'warning' | 'error'} status
 * @property {string} [statusReason]
 */

/**
 * @typedef {Object} EmulatorHealthEntry
 * @property {string} id
 * @property {'ok' | 'corrupted_config' | 'missing_config' | 'no_default_snapshot'} status
 * @property {string} [details]
 */

/**
 * @typedef {Object} ConsoleWizardHealth
 * @property {'healthy' | 'warning' | 'error'} status
 * @property {EmulatorHealthEntry[]} emulators
 */

/**
 * @typedef {Object} ConfigDiffFile
 * @property {string} relativePath
 * @property {'created' | 'modified' | 'deleted'} changeType
 * @property {string} [before]
 * @property {string} [after]
 */

/**
 * @typedef {Object} PreviewEmulatorEntry
 * @property {string} id
 * @property {string} displayName
 * @property {ConfigDiffFile[]} files
 */

/**
 * @typedef {Object} ConfigPreviewResult
 * @property {boolean} dryRun
 * @property {PreviewEmulatorEntry[]} emulators
 * @property {string} summary
 */

/**
 * @typedef {Object} ConfigApplyResult
 * @property {boolean} success
 * @property {ConfigPreviewResult} preview
 * @property {string} backupPath
 * @property {string} [logId]
 * @property {QuirkResult[]} quirks
 * @property {boolean} [requiresRestart]
 */

/**
 * @typedef {Object} QuirkResult
 * @property {string} quirkId
 * @property {string} emulatorId
 * @property {boolean} success
 * @property {'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'} severity
 * @property {string} userMessage
 * @property {string[]} [actionsTaken]
 * @property {string[]} [warnings]
 * @property {string[]} [errors]
 */

/**
 * @typedef {Object} ChuckSyncStatus
 * @property {string} currentMappingHash
 * @property {string | null} lastSyncedHash
 * @property {boolean} isOutOfSync
 */

const API_BASE = '';
const TTS_VOICE_ID = 'CwhRBWXzGAHq8TQ4Fs17';
const DEFAULT_SCOPE = 'state';
const PREVIEW_SCOPE = 'state';  // Fixed: backend requires 'state' for dry_run=true
const MUTATION_SCOPE = 'config';
const wizDeviceId = window.AA_DEVICE_ID || (() => {
  console.warn('[Wiz] window.AA_DEVICE_ID not available, ' +
    'falling back to cabinet-001. Cabinet identity may not be unique.');
  return 'cabinet-001';
})();

const panelHeaders = (scope = DEFAULT_SCOPE) => ({
  'Content-Type': 'application/json',
  'x-device-id': wizDeviceId,
  'x-panel': 'console-wizard',
  'x-scope': scope,
});

const PANEL_STATUS_META = {
  healthy: { label: 'Healthy', tone: 'status-healthy' },
  warning: { label: 'Warnings', tone: 'status-warning' },
  error: { label: 'Errors', tone: 'status-error' },
};

const ENDPOINTS = {
  emulators: '/api/local/console_wizard/emulators',
  generateConfigs: '/api/local/console_wizard/generate-configs',
  syncFromChuck: '/api/local/console_wizard/sync-from-chuck',
  setDefaults: '/api/local/console_wizard/set-defaults',
  restoreAll: '/api/local/console_wizard/restore-all',
  health: '/api/local/console_wizard/health',
  controllers: '/api/local/console/controllers',
  profiles: '/api/local/console/profiles',
};

const STATUS_LABELS = {
  ok: 'OK',
  warning: 'Warn',
  error: 'Error',
};

const DETAIL_TABS = [
  { id: 'summary', label: 'Summary' },
  { id: 'preview', label: 'Preview' },
  { id: 'quirks', label: 'Quirks' },
];

const severityTone = {
  LOW: 'quirk-low',
  MEDIUM: 'quirk-medium',
  HIGH: 'quirk-high',
  CRITICAL: 'quirk-critical',
};

const statusAttention = new Set(['warning', 'error']);
const healthAttention = new Set([
  'corrupted_config',
  'missing_config',
  'modified',
  'no_default_snapshot',
]);

const describeHealth = (entry) => {
  if (!entry) return 'No issues detected for this emulator.';
  if (entry.details) return entry.details;
  switch (entry.status) {
    case 'modified':
      return 'Config drift detected. Preview and repair recommended.';
    case 'corrupted_config':
      return 'Config appears corrupted. Preview and repair recommended.';
    case 'missing_config':
      return 'Config missing. Console Wizard can rebuild it from Chuck mapping.';
    case 'no_default_snapshot':
      return 'No default snapshot on record. Create one after configs look good.';
    case 'ok':
    default:
      return 'Healthy. No drift from the last snapshot.';
  }
};

const relativeTime = (iso) => {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  if (Number.isNaN(diff) || diff < 0) return null;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr${hours > 1 ? 's' : ''} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days > 1 ? 's' : ''} ago`;
};

const previewCounts = (preview) => {
  const emulatorCount = preview?.emulators?.length ?? 0;
  const fileCount =
    preview?.emulators?.reduce(
      (total, entry) => total + (entry.files?.length ?? 0),
      0,
    ) ?? 0;
  return { emulatorCount, fileCount };
};

const summarizeUnifiedDiff = (diffText) => {
  if (!diffText) {
    return { additions: 0, removals: 0 };
  }

  return diffText.split(/\r?\n/).reduce(
    (stats, line) => {
      if (line.startsWith('+++') || line.startsWith('---')) {
        return stats;
      }
      if (line.startsWith('+')) {
        stats.additions += 1;
      } else if (line.startsWith('-')) {
        stats.removals += 1;
      }
      return stats;
    },
    { additions: 0, removals: 0 },
  );
};

const formatSystems = (systems) =>
  systems?.length ? systems.join(', ') : 'â€”';

const safeJoin = (list) => (list?.length ? list.join(', ') : 'None');

/**
 * Transform backend emulator data to match frontend expectations
 */
const normalizeEmulator = (backendEmu) => ({
  id: backendEmu.id,
  displayName: backendEmu.name || backendEmu.displayName || backendEmu.id,
  type: backendEmu.type || 'other',
  systems: backendEmu.systems || [],
  configFormat: backendEmu.config_format || backendEmu.configFormat || 'UNKNOWN',
  inputNamingConvention: backendEmu.input_naming_convention || backendEmu.inputNamingConvention || 'Unknown',
  status: backendEmu.status || 'ok',
  statusReason: backendEmu.status_reason || backendEmu.statusReason,
});

export default function ConsoleWizardPanel() {
  const [emulators, setEmulators] = useState([]);
  const [health, setHealth] = useState(/** @type {ConsoleWizardHealth | null} */(null));
  const [healthUnavailable, setHealthUnavailable] = useState(false);
  const [healthMessage, setHealthMessage] = useState(null);
  const [chuckStatus, setChuckStatus] =
    useState(/** @type {ChuckSyncStatus | null} */(null));
  const [selectedEmulatorId, setSelectedEmulatorId] = useState(null);
  const [detailsTab, setDetailsTab] = useState('summary');
  const [statusFilter, setStatusFilter] = useState('all');
  const [initialLoading, setInitialLoading] = useState(true);
  const [scanInFlight, setScanInFlight] = useState(false);
  const [panelError, setPanelError] = useState(null);
  const [previewResult, setPreviewResult] =
    useState(/** @type {ConfigPreviewResult | null} */(null));
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const previewRequestRef = useRef(/** @type {Record<string, unknown> | null} */(null));
  const previewContextRef = useRef('configs');
  const [applyInFlight, setApplyInFlight] = useState(false);
  const [pendingExecution, setPendingExecution] = useState(null);
  const [quirkResults, setQuirkResults] =
    useState(/** @type {QuirkResult[]} */([]));
  const [requiresRestart, setRequiresRestart] = useState(false);
  const [restoringEmulatorId, setRestoringEmulatorId] = useState(null);
  const [restoringAll, setRestoringAll] = useState(false);
  const [settingDefaults, setSettingDefaults] = useState(false);
  const [toast, setToast] = useState(null);
  const toastTimerRef = useRef(/** @type {ReturnType<typeof setTimeout> | null} */(null));
  const [lastActions, setLastActions] = useState({});
  const [tendenciesData, setTendenciesData] = useState(null);
  const [tendenciesProfileId, setTendenciesProfileId] = useState(null);
  const tableRef = useRef(null);
  const [devErrorDetails, setDevErrorDetails] = useState(null);
  const [activeNav, setActiveNav] = useState('dashboard');
  const [activityLogs, setActivityLogs] = useState([]);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const chatMessagesRef = useRef(chatMessages);
  const handoffProcessedRef = useRef(null); // Track last processed handoff context
  const initialGreetingRef = useRef(false);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [listeningLabel, setListeningLabel] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(true);
  // Pending confirmation tracking: { emulator, controller, action, summary }
  const [pendingConfirmation, setPendingConfirmation] = useState(null);
  const [backendDisconnected, setBackendDisconnected] = useState(false);
  const [backendDisconnectMessage, setBackendDisconnectMessage] = useState('');

  // Controller detection state
  const [detectedControllers, setDetectedControllers] = useState([]);
  const [controllerDetectionLoading, setControllerDetectionLoading] = useState(false);
  const [controllerDetectionError, setControllerDetectionError] = useState(null);
  const [autoConfiguring, setAutoConfiguring] = useState(false);
  const [autoConfigProgress, setAutoConfigProgress] = useState(null);

  // TeknoParrot state
  const [tpSelectedGame, setTpSelectedGame] = useState('InitialD8');
  const [tpGames, setTpGames] = useState([]);
  const [tpPreviewLoading, setTpPreviewLoading] = useState(false);
  const [tpApplyLoading, setTpApplyLoading] = useState(false);
  const [tpPreviewResult, setTpPreviewResult] = useState(null);
  const [tpApplyResult, setTpApplyResult] = useState(null);
  const [tpError, setTpError] = useState(null);

  // Voice recording refs
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const wsRef = useRef(null);
  const chunkSequenceRef = useRef(0);

  const logEvent = useCallback((event, payload = {}) => {
    console.info('[ConsoleWizard]', event, payload);
    setActivityLogs(prev => [{
      id: Date.now() + '-' + Math.random().toString(36).slice(2, 6),
      event,
      title: event,
      detail: payload.error || payload.controller || payload.summary || null,
      type: payload.error ? 'error' : (event.includes('fail') ? 'error' : event.includes('complete') ? 'success' : 'info'),
      timestamp: new Date().toISOString(),
    }, ...prev].slice(0, 200));
  }, []);

  const formatDevError = useCallback((err, fallback) => {
    if (!err) return fallback ?? 'No additional error details were provided.';
    const parts = [];
    if (err.status) {
      parts.push(
        `HTTP ${err.status}${err.statusText ? ` ${err.statusText}` : ''}`,
      );
    } else if (err.statusText) {
      parts.push(err.statusText);
    }
    const message = err.message || fallback || 'Request failed.';
    parts.push(`Message: ${message}`);
    if (err.path) {
      parts.push(`Endpoint: ${err.path}`);
    }
    if (err.correlationId) {
      parts.push(`Correlation ID: ${err.correlationId}`);
    }
    return parts.join('\n');
  }, []);

  const showDevErrorDetails = useCallback((title, details) => {
    setDevErrorDetails({ title, details });
  }, []);

  const describeBackendError = useCallback((err, fallback) => {
    if (!err) return fallback;
    const code = err.status ?? err.code;
    if (code === 0 || code === 502 || code === 503 || code === 504) {
      return 'Console Wizard backend is not reachable. Start the backend service (`node scripts/dev-backend.cjs` or `npm run dev`) and wait for http://localhost:8888/health to report OK.';
    }
    if (code === 404) {
      return 'Console Wizard API endpoint was not found. Ensure the gateway is routing /api/local/console_wizard/* requests.';
    }
    return err.message ?? fallback;
  }, []);

  const showErrorToast = useCallback(
    (summary, err) => {
      const detailSummary = err?.message ?? summary;
      const devDetails = formatDevError(err, summary);
      setToast({
        type: 'error',
        text: detailSummary,
        actionLabel: 'View details',
        actionHandler: () => {
          showDevErrorDetails(summary, devDetails);
          setToast(null);
        },
      });
    },
    [formatDevError, showDevErrorDetails],
  );

  const fetchJSON = useCallback(
    async (path, { method = 'GET', scope = DEFAULT_SCOPE, body } = {}) => {
      let response;
      try {
        response = await fetch(`${API_BASE}${path}`, {
          method,
          headers: panelHeaders(scope),
          body: body ? JSON.stringify(body) : undefined,
        });
      } catch (networkErr) {
        const error = new Error(networkErr?.message || 'Network error');
        error.status = 0;
        error.statusText = 'Network Error';
        error.path = path;
        throw error;
      }

      const text = await response.text();
      let data = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (_err) {
          data = text;
        }
      }

      if (!response.ok) {
        const detail =
          (data &&
            typeof data === 'object' &&
            data !== null &&
            typeof data.detail === 'string' &&
            data.detail) ||
          (typeof data === 'string' && data) ||
          response.statusText ||
          'Request failed';
        const error = new Error(detail);
        error.status = response.status;
        error.statusText = response.statusText;
        error.correlationId = response.headers.get('x-correlation-id');
        error.body = data;
        error.path = path;
        throw error;
      }

      return data ?? {};
    },
    [],
  );

  const recordActivity = useCallback((ids, description) => {
    if (!ids?.length) return;
    const timestamp = new Date().toISOString();
    setLastActions((prev) => {
      const next = { ...prev };
      ids.forEach((id) => {
        next[id] = { description, timestamp };
      });
      return next;
    });
  }, []);

  const refreshAll = useCallback(async () => {
    setPanelError(null);
    setScanInFlight(true);
    setHealthUnavailable(false);
    setHealthMessage(null);
    logEvent('Scan started');

    try {
      const response = await fetchJSON(ENDPOINTS.emulators);
      const rawEmulators = response?.emulators ?? [];
      const normalizedEmulators = Array.isArray(rawEmulators)
        ? rawEmulators.map(normalizeEmulator)
        : [];

      // Deduplicate emulators by ID (backend sometimes returns duplicates)
      const uniqueEmulators = normalizedEmulators.reduce((acc, emu) => {
        if (!acc.find(e => e.id === emu.id)) {
          acc.push(emu);
        }
        return acc;
      }, []);

      setEmulators(uniqueEmulators);
      logEvent('Emulator scan loaded', {
        count: uniqueEmulators.length,
        duplicatesRemoved: normalizedEmulators.length - uniqueEmulators.length,
      });
      setBackendDisconnected(false);
      setBackendDisconnectMessage('');
    } catch (err) {
      const friendly = describeBackendError(err, 'Unable to load console emulator list.');
      setPanelError(friendly);
      if (err?.status === 0 || err?.status === 502 || err?.status === 503 || err?.status === 504) {
        setBackendDisconnected(true);
        setBackendDisconnectMessage(friendly);
      } else {
        setBackendDisconnected(false);
        setBackendDisconnectMessage('');
      }
      showErrorToast('Failed to scan emulators', err);
      console.error('[ConsoleWizard] Emulator scan failed', err);
    }

    try {
      const healthData = await fetchJSON(ENDPOINTS.health);
      // Backend returns: { status: [array of emulator health objects] }
      // Transform to frontend format: { status: overall, emulators: [...] }
      const emulatorHealthArray = healthData?.status ?? [];

      // Calculate overall status from emulator statuses
      let overallStatus = 'healthy';
      if (emulatorHealthArray.some((e) => e.status === 'corrupted')) {
        overallStatus = 'error';  // Only corrupted configs are errors
      } else if (emulatorHealthArray.some((e) => e.status === 'missing' || e.status === 'modified')) {
        overallStatus = 'warning';  // Missing/modified defaults are warnings (user needs to set defaults)
      }

      const transformedHealth = {
        status: overallStatus,
        emulators: emulatorHealthArray.map((e) => {
          let mappedStatus = 'ok';
          if (e.status === 'modified') mappedStatus = 'modified';
          else if (e.status === 'missing') mappedStatus = 'no_default_snapshot';
          else if (e.status === 'corrupted') mappedStatus = 'corrupted_config';
          else if (e.status === 'pending_defaults') mappedStatus = 'ok';

          return {
            id: e.emulator,
            status: mappedStatus,
            details: e.details,
            currentFile: e.current_file,
            defaultsFile: e.defaults_file,
          };
        }),
      };

      setHealth(transformedHealth);
      setHealthUnavailable(false);
      setHealthMessage(null);
      setBackendDisconnected(false);
      setBackendDisconnectMessage('');
      logEvent('Health loaded', {
        status: overallStatus,
        emulatorCount: transformedHealth.emulators.length,
      });
    } catch (err) {
      const friendly = describeBackendError(err, 'Console Wizard health status is unavailable. Try again shortly.');
      setHealthUnavailable(true);
      setHealthMessage(friendly);
      if (err?.status === 0 || err?.status === 502 || err?.status === 503 || err?.status === 504) {
        setBackendDisconnected(true);
        setBackendDisconnectMessage(friendly);
      } else {
        setBackendDisconnected(false);
        setBackendDisconnectMessage('');
      }
      setHealth((prev) => prev ?? { status: 'warning', emulators: [] });
      showErrorToast('Health check failed', err);
      console.warn('[ConsoleWizard] Health load failed', err);
    }

    // Fetch Chuck sync status
    try {
      const chuckStatusData = await fetchJSON('/api/local/console_wizard/status/chuck');
      setChuckStatus(chuckStatusData);
      logEvent('Chuck status loaded', {
        currentHash: chuckStatusData?.currentMappingHash,
        lastSyncedHash: chuckStatusData?.lastSyncedHash,
        isOutOfSync: chuckStatusData?.isOutOfSync,
      });
    } catch (err) {
      // Chuck status not critical, just log and continue
      setChuckStatus(null);
      console.warn('[ConsoleWizard] Chuck status load failed', err);
    }

    setScanInFlight(false);
    setInitialLoading(false);
  }, [fetchJSON, logEvent, showErrorToast, describeBackendError]);

  const processOperationResult = useCallback(
    (result, description, fallbackIds = []) => {
      if (!result) return;
      if (result.preview) {
        setPreviewResult(result.preview);
      }
      if (Array.isArray(result.quirks)) {
        setQuirkResults(result.quirks);
      }
      if (result.requiresRestart) {
        setRequiresRestart(true);
      }
      const affectedIds =
        result.preview?.emulators?.map((entry) => entry.id) ?? fallbackIds;
      recordActivity(affectedIds, description);

      const toastText = result.backupPath
        ? `Configs updated. Backups saved under ${result.backupPath}`
        : description;

      setToast({
        type: 'success',
        text: toastText,
        actionLabel: result.quirks?.length ? 'View actions & quirks' : null,
        actionHandler: result.quirks?.length
          ? () => {
            if (affectedIds.length) {
              setSelectedEmulatorId(affectedIds[0]);
              setDetailsTab('quirks');
            }
            setToast(null);
          }
          : null,
      });

      refreshAll();
    },
    [recordActivity, refreshAll],
  );

  const handlePreview = useCallback(
    async (request = {}, context = 'configs') => {
      console.log('[ConsoleWizard] handlePreview called', { request, context });
      setPanelError(null);
      setPendingExecution(null);
      setPreviewModalOpen(true);
      console.log('[ConsoleWizard] setPreviewModalOpen(true) called');
      setPreviewLoading(true);
      setPreviewError(null);

      const normalizedRequest = { ...(request ?? {}) };

      previewRequestRef.current = normalizedRequest;
      previewContextRef.current = context;

      logEvent('Preview requested', {
        context,
        emulatorIds: normalizedRequest.emulatorIds ?? 'all',
      });

      try {
        let endpoint, payload;

        if (context === 'configs') {
          endpoint = ENDPOINTS.generateConfigs;
          payload = {
            dry_run: true,
          };
          // Only include emulators if we have specific IDs to target
          if (normalizedRequest.emulatorIds && normalizedRequest.emulatorIds.length > 0) {
            payload.emulators = normalizedRequest.emulatorIds;
          }
        } else if (context === 'chuck') {
          endpoint = ENDPOINTS.syncFromChuck;
          payload = {
            force: false,
            dry_run: true,
          };
          // Only include emulators if we have specific IDs to target
          if (normalizedRequest.emulatorIds && normalizedRequest.emulatorIds.length > 0) {
            payload.emulators = normalizedRequest.emulatorIds;
          }
        }

        const response = await fetchJSON(endpoint, {
          method: 'POST',
          scope: PREVIEW_SCOPE,
          body: payload,
        });

        // Transform backend response to frontend preview format
        const backendResults = response?.results ?? [];
        const transformedEmulators = backendResults
          .filter((result) => result.has_changes)
          .map((result) => {
            const relativePath = result.target_file || `${result.emulator}.json`;
            const diffText = result.diff || '';
            const diffStats = summarizeUnifiedDiff(diffText);
            return {
              id: result.emulator,
              displayName: result.emulator,
              files: [
                {
                  relativePath,
                  path: relativePath,
                  changeType: 'modified',
                  before: '', // Backend provides unified diff, not separate before/after
                  after: diffText,
                  diff: diffText,
                  unifiedDiff: diffText,
                  additions: diffStats.additions,
                  removals: diffStats.removals,
                },
              ],
            };
          });

        const preview = {
          dryRun: response?.dry_run ?? true,
          emulators: transformedEmulators,
          summary: `Preview for ${transformedEmulators.length} emulator(s) with changes`,
        };

        setPreviewResult(preview);
        setPreviewError(null);
        logEvent('Preview received', {
          context,
          emulatorCount: preview?.emulators?.length ?? 0,
        });
        if (!preview?.emulators?.length) {
          setToast({
            type: 'info',
            text: 'No config changes detected for the selected scope.',
          });
        }
      } catch (err) {
        let detail = err.message ?? 'Preview failed.';

        // Check for incomplete_mapping error
        if (err.body && typeof err.body === 'object') {
          const errorData = err.body.detail || err.body;
          if (errorData.error === 'incomplete_mapping') {
            const missingKeys = errorData.missing_keys || [];
            detail = `Controller Chuck's mapping is incomplete. Please open Controller Chuck and configure the missing buttons: ${missingKeys.join(', ')}`;
          }
        }

        setPanelError(detail);
        setPreviewError(detail);
        showErrorToast('Preview failed', err);
        console.error('[ConsoleWizard] Preview failed', err);
      } finally {
        setPreviewLoading(false);
      }
    },
    [fetchJSON, logEvent, showErrorToast],
  );

  const handleClosePreviewModal = useCallback(() => {
    setPreviewModalOpen(false);
    setPreviewError(null);
  }, []);

  const handleApplyPreview = useCallback(() => {
    if (!previewRequestRef.current) {
      const err = new Error('Run a preview before applying changes.');
      setPanelError(err.message);
      showErrorToast('Apply aborted', err);
      return;
    }
    if (!previewResult?.emulators?.length) {
      const err = new Error('No config changes are queued for apply.');
      setPanelError(err.message);
      showErrorToast('Apply aborted', err);
      return;
    }

    const emulatorCount = previewResult.emulators.length;
    const fileCount = previewResult.emulators.reduce(
      (total, entry) => total + (entry.files?.length ?? 0),
      0,
    );
    const names = previewResult.emulators.map((entry) => entry.displayName || entry.id);
    const summaryPrefix =
      previewContextRef.current === 'chuck'
        ? 'Sync Controller Chuck mappings into Wiz emulator configs'
        : 'Apply Wiz config changes to emulator config files';
    const display = `${summaryPrefix} for ${emulatorCount} emulator${emulatorCount === 1 ? '' : 's'} and ${fileCount} file${fileCount === 1 ? '' : 's'}: ${names.join(', ')}.`;

    setPendingExecution({
      display,
      payload: {
        context: previewContextRef.current,
        emulator_ids:
          previewRequestRef.current.emulatorIds && previewRequestRef.current.emulatorIds.length > 0
            ? previewRequestRef.current.emulatorIds
            : previewResult.emulators.map((entry) => entry.id),
        preview_summary: previewResult.summary || display,
      },
    });
    setToast({
      type: 'info',
      text: 'Config changes staged. Press EXECUTE to write them to disk.',
    });
    logEvent('ExecutionCard queued', {
      context: previewContextRef.current,
      emulatorCount,
      fileCount,
    });
    handleClosePreviewModal();
  }, [
    previewResult,
    handleClosePreviewModal,
    logEvent,
    showErrorToast,
  ]);

  const handleExecutePreviewApply = useCallback(async (payload) => {
    setApplyInFlight(true);
    setPanelError(null);

    try {
      const response = await fetchJSON('/api/local/console/apply-config', {
        method: 'POST',
        scope: MUTATION_SCOPE,
        body: payload,
      });

      if (response?.status !== 'applied') {
        throw new Error(response?.message || 'Apply failed.');
      }

      const affectedEmulatorIds =
        response?.emulators?.length
          ? response.emulators
          : (previewResult?.emulators?.map((entry) => entry.id) ?? []);

      processOperationResult(
        {
          success: true,
          preview: null,
          quirks: [],
          requiresRestart: false,
          backupPath: null,
        },
        payload.context === 'chuck'
          ? 'Console emulators synced from Controller Chuck.'
          : 'Config changes applied.',
        affectedEmulatorIds,
      );

      setToast({
        type: 'success',
        text:
          response?.files?.length > 0
            ? `Applied ${response.files.length} config file${response.files.length === 1 ? '' : 's'} successfully.`
            : (response?.message || 'Config changes applied.'),
      });
      setPendingExecution(null);
      logEvent('Apply finished', {
        context: payload.context,
        success: true,
        written: response?.files?.length ?? 0,
      });
    } catch (err) {
      const detail = err.message ?? 'Apply failed.';
      setPanelError(detail);
      showErrorToast('Apply failed', err);
      logEvent('Apply failed', {
        context: payload?.context ?? previewContextRef.current,
        error: detail,
      });
      throw err;
    } finally {
      setApplyInFlight(false);
    }
  }, [
    fetchJSON,
    previewResult,
    processOperationResult,
    logEvent,
    showErrorToast,
  ]);

  const handleCancelPreviewApply = useCallback(() => {
    setPendingExecution(null);
    setToast({
      type: 'info',
      text: 'Config apply was cancelled before execution.',
    });
    logEvent('ExecutionCard cancelled', {
      context: previewContextRef.current,
    });
  }, [logEvent]);

  const handleRestoreEmulator = useCallback(
    async (emulatorId) => {
      const emulator = emulators.find((entry) => entry.id === emulatorId);
      const label = emulator?.displayName ?? emulatorId;
      if (
        !window.confirm(
          `Restore ${label} from its default snapshot? This will overwrite current configs.`,
        )
      ) {
        return;
      }
      logEvent('Restore started', { emulatorId });
      setRestoringEmulatorId(emulatorId);
      setPanelError(null);
      try {
        const response = await fetchJSON(
          `/api/local/console_wizard/restore/${encodeURIComponent(emulatorId)}`,
          {
            method: 'POST',
            scope: MUTATION_SCOPE,
            body: { dry_run: false },
          },
        );

        // Transform backend response
        const transformedResult = {
          success: response?.restored ?? false,
          preview: null,
          quirks: [],
          requiresRestart: false,
          backupPath: response?.backup_path ?? null,
        };

        processOperationResult(
          transformedResult,
          `Restored ${emulatorId} from default snapshot.`,
          [emulatorId],
        );
        logEvent('Restore finished', { emulatorId, success: true });
      } catch (err) {
        setPanelError(err.message ?? 'Restore failed.');
        showErrorToast('Restore failed', err);
        logEvent('Restore failed', { emulatorId, error: err?.message });
      } finally {
        setRestoringEmulatorId(null);
      }
    },
    [emulators, fetchJSON, processOperationResult, logEvent, showErrorToast],
  );

  const handleRestoreAll = useCallback(async () => {
    if (!emulators.length) return;
    if (
      !window.confirm(
        'Restore all console emulator configs from their default snapshots? This will overwrite current configs.',
      )
    ) {
      return;
    }
    logEvent('Restore all started', { count: emulators.length });
    setRestoringAll(true);
    setPanelError(null);
    try {
      const response = await fetchJSON(ENDPOINTS.restoreAll, {
        method: 'POST',
        scope: MUTATION_SCOPE,
        body: { dry_run: false },
      });

      // Transform backend response
      const backendResults = response?.results ?? [];
      const restoredEmulatorIds = backendResults
        .filter((r) => r.restored)
        .map((r) => r.emulator);

      const transformedResult = {
        success: restoredEmulatorIds.length > 0,
        preview: null,
        quirks: [],
        requiresRestart: false,
        backupPath: null,
      };

      processOperationResult(
        transformedResult,
        'All emulators restored from default snapshots.',
        restoredEmulatorIds.length > 0 ? restoredEmulatorIds : emulators.map((emu) => emu.id),
      );
      logEvent('Restore all finished', { success: true });
    } catch (err) {
      setPanelError(err.message ?? 'Restore all failed.');
      showErrorToast('Restore all failed', err);
      logEvent('Restore all failed', { error: err?.message });
    } finally {
      setRestoringAll(false);
    }
  }, [emulators, fetchJSON, processOperationResult, logEvent, showErrorToast]);

  const handleSetDefaults = useCallback(async () => {
    if (!emulators.length) return;
    logEvent('Defaults snapshot started', { count: emulators.length });
    setSettingDefaults(true);
    setPanelError(null);
    try {
      const result = await fetchJSON(ENDPOINTS.setDefaults, {
        method: 'POST',
        scope: MUTATION_SCOPE,
        body: { emulators: null },
      });
      const resultsArray = result?.results ?? [];
      setToast({
        type: 'success',
        text: `Snapshot captured for ${resultsArray.length} emulator(s).`,
      });
      refreshAll();
      logEvent('Defaults snapshot finished', { count: resultsArray.length });
    } catch (err) {
      setPanelError(err.message ?? 'Unable to snapshot defaults.');
      showErrorToast('Defaults snapshot failed', err);
      logEvent('Defaults snapshot failed', { error: err?.message });
    } finally {
      setSettingDefaults(false);
    }
  }, [emulators.length, fetchJSON, refreshAll, logEvent, showErrorToast]);

  const handleBannerReview = useCallback(() => {
    setStatusFilter('attention');
    if (tableRef.current) {
      tableRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, []);

  const handlePreviewAll = useCallback(() => {
    handlePreview({}, 'configs');
  }, [handlePreview]);

  const handleRetryPreview = useCallback(() => {
    if (!previewRequestRef.current) return;
    handlePreview(previewRequestRef.current, previewContextRef.current);
  }, [handlePreview]);

  const handlePreviewSingle = useCallback(
    (emulatorId) => {
      console.log('[ConsoleWizard] handlePreviewSingle called with emulatorId:', emulatorId);
      handlePreview({ emulatorIds: [emulatorId] }, 'configs');
    },
    [handlePreview],
  );

  const handleChuckPreview = useCallback(() => {
    handlePreview(
      { fromMappingHash: chuckStatus?.currentMappingHash },
      'chuck',
    );
  }, [chuckStatus, handlePreview]);

  const handleDismissToast = useCallback(() => {
    setToast(null);
  }, []);

  const handleDismissError = useCallback(() => {
    setPanelError(null);
  }, []);

  const handleCloseDevError = useCallback(() => {
    setDevErrorDetails(null);
  }, []);

  // TeknoParrot handlers
  const fetchTpGames = useCallback(async () => {
    try {
      const response = await fetchJSON('/api/console/teknoparrot/games');
      const games = response?.games ?? [];
      setTpGames(games);
      if (games.length > 0 && !games.find(g => g.name === tpSelectedGame)) {
        setTpSelectedGame(games[0].name);
      }
    } catch (err) {
      console.warn('[ConsoleWizard] Failed to fetch TeknoParrot games:', err);
      // Fallback to hardcoded games
      setTpGames([
        { name: 'InitialD8', category: 'racing', display_name: 'Initial D Arcade Stage 8' },
        { name: 'HOTD4', category: 'lightgun', display_name: 'House of the Dead 4' },
      ]);
    }
  }, [fetchJSON, tpSelectedGame]);

  const handleTpPreflight = useCallback(async () => {
    if (!tpSelectedGame) return;
    setTpPreviewLoading(true);
    setTpPreviewResult(null);
    setTpApplyResult(null);
    setTpError(null);
    logEvent('TeknoParrot preflight started', { game: tpSelectedGame });

    try {
      const response = await fetchJSON('/api/console/teknoparrot/preview', {
        method: 'POST',
        scope: PREVIEW_SCOPE,
        body: { profile_name: tpSelectedGame },
      });
      setTpPreviewResult(response);
      logEvent('TeknoParrot preflight complete', {
        game: tpSelectedGame,
        hasChanges: response?.has_changes,
        changesCount: response?.changes_count,
      });
    } catch (err) {
      const detail = err.message ?? 'TeknoParrot preflight failed.';
      setTpError(detail);
      showErrorToast('TeknoParrot preflight failed', err);
      logEvent('TeknoParrot preflight failed', { game: tpSelectedGame, error: detail });
    } finally {
      setTpPreviewLoading(false);
    }
  }, [tpSelectedGame, fetchJSON, logEvent, showErrorToast]);

  const handleTpApply = useCallback(async () => {
    if (!tpSelectedGame) return;
    setTpApplyLoading(true);
    setTpApplyResult(null);
    setTpError(null);
    logEvent('TeknoParrot apply started', { game: tpSelectedGame });

    try {
      const response = await fetchJSON('/api/console/teknoparrot/apply', {
        method: 'POST',
        scope: MUTATION_SCOPE,
        body: { profile_name: tpSelectedGame },
      });
      setTpApplyResult(response);
      setTpPreviewResult(null); // Clear preview after successful apply
      setToast({
        type: 'success',
        text: `TeknoParrot config applied for ${tpSelectedGame}. ${response?.changes_applied ?? 0} bindings updated.`,
      });
      logEvent('TeknoParrot apply complete', {
        game: tpSelectedGame,
        changesApplied: response?.changes_applied,
        backupPath: response?.backup_path,
      });
    } catch (err) {
      const detail = err.message ?? 'TeknoParrot apply failed.';
      setTpError(detail);
      showErrorToast('TeknoParrot apply failed', err);
      logEvent('TeknoParrot apply failed', { game: tpSelectedGame, error: detail });
    } finally {
      setTpApplyLoading(false);
    }
  }, [tpSelectedGame, fetchJSON, logEvent, showErrorToast]);

  // Fetch TeknoParrot games on mount
  useEffect(() => {
    fetchTpGames();
  }, [fetchTpGames]);

  const speakText = useCallback(
    async (text) => {
      if (!speakReplies || !text) return;
      try {
        await ttsSpeak(String(text), { voice_id: TTS_VOICE_ID, model_id: 'eleven_turbo_v2' });
      } catch (err) {
        console.warn('[ConsoleWizard] TTS unavailable:', err);
      }
    },
    [speakReplies],
  );

  const addChatMessage = useCallback(
    (text, sender = 'assistant', options = {}) => {
      const speak = options.speak ?? true;
      const newMessage = {
        id: Date.now(),
        text,
        sender,
        timestamp: new Date().toISOString(),
      };
      setChatMessages((prev) => {
        const updated = [...prev, newMessage];
        chatMessagesRef.current = updated;
        return updated;
      });
      if (sender === 'assistant' && text && speak) {
        speakText(String(text));
      }
    },
    [speakText],
  );

  // Confirmation detection patterns
  const CONFIRMATION_ASK_PATTERNS = [
    /is that correct\??$/i,
    /does that sound right\??$/i,
    /shall I (proceed|configure|set up|apply)/i,
    /ready to (apply|proceed|configure)\??$/i,
    /want me to (proceed|configure|set up|go ahead)/i,
    /should I (proceed|configure|set up|apply)/i,
  ];

  const YES_RESPONSE_PATTERNS = [
    /^yes$/i, /^yep$/i, /^yeah$/i, /^yup$/i, /^correct$/i,
    /^that'?s? (right|correct)$/i, /^y$/i, /^sure$/i, /^ok$/i, /^okay$/i,
    /^go ahead$/i, /^do it$/i, /^please$/i, /^affirmative$/i,
    /^yes[,.]? (that'?s?|it'?s?) (right|correct)/i,
    /^yes[,.]? please/i, /^yes[,.]? go ahead/i,
  ];

  const NO_RESPONSE_PATTERNS = [
    /^no$/i, /^nope$/i, /^nah$/i, /^not (quite|exactly|really)$/i,
    /^that'?s? (wrong|not right|incorrect)$/i, /^wait$/i, /^hold on$/i,
    /^actually/i, /^not what I/i, /^I (meant|want)/i,
  ];

  const detectConfirmationAsk = useCallback((text) => {
    const trimmed = (text || '').trim();
    return CONFIRMATION_ASK_PATTERNS.some(p => p.test(trimmed));
  }, []);

  const isYesResponse = useCallback((text) => {
    const trimmed = (text || '').trim();
    return YES_RESPONSE_PATTERNS.some(p => p.test(trimmed));
  }, []);

  const isNoResponse = useCallback((text) => {
    const trimmed = (text || '').trim();
    return NO_RESPONSE_PATTERNS.some(p => p.test(trimmed));
  }, []);

  // Extract emulator/action context from recent conversation for pendingConfirmation
  const extractConfirmationContext = useCallback((messages) => {
    // Look at recent messages to extract what's being discussed
    const recentText = messages.slice(-6).map(m => m.text).join(' ').toLowerCase();
    let emulator = 'unknown';
    let action = 'configuration';

    // Detect emulator from conversation
    if (recentText.includes('retroarch')) emulator = 'RetroArch';
    else if (recentText.includes('dolphin')) emulator = 'Dolphin';
    else if (recentText.includes('pcsx2')) emulator = 'PCSX2';
    else if (recentText.includes('rpcs3')) emulator = 'RPCS3';
    else if (recentText.includes('mame')) emulator = 'MAME';

    // Detect action type
    if (recentText.includes('dual mapping') || (recentText.includes('left stick') && recentText.includes('d-pad'))) {
      action = 'dual mapping (left stick + d-pad for directions)';
    } else if (recentText.includes('analog') && recentText.includes('direction')) {
      action = 'left analog stick directional mapping';
    } else if (recentText.includes('button') && recentText.includes('map')) {
      action = 'button mapping';
    }

    return { emulator, action, summary: `${emulator}: ${action}` };
  }, []);

  const sendChat = useCallback(
    async (messageText) => {
      const userMessage = messageText.trim();
      if (!userMessage) return;
      addChatMessage(userMessage, 'user');
      setChatLoading(true);

      try {
        // Check if we have a pending confirmation and user is responding to it
        if (pendingConfirmation) {
          if (isYesResponse(userMessage)) {
            // User confirmed! Advance the flow without calling LLM for a generic response
            const confirmReply = `Great! I'll configure ${pendingConfirmation.emulator} for ${pendingConfirmation.action}. Let me prepare that for you.\n\nTo apply this configuration, go to Generate Configs (Preview) button above, review the changes, and click Apply. I'll make sure the ${pendingConfirmation.emulator} settings include the mapping you requested.`;
            addChatMessage(confirmReply, 'assistant');
            setPendingConfirmation(null);
            setChatLoading(false);
            return;
          } else if (isNoResponse(userMessage)) {
            // User rejected - ask for clarification but keep context
            const clarifyReply = `I see, that's not quite what you wanted. Can you clarify what you'd like instead? I understood: ${pendingConfirmation.summary}`;
            addChatMessage(clarifyReply, 'assistant');
            setPendingConfirmation(null);
            setChatLoading(false);
            return;
          }
          // If it's not a clear yes/no, clear pending and treat as new input
          setPendingConfirmation(null);
        }

        const controllerSummary = detectedControllers
          .map((c) => `${c.name || c.profile_id || 'Unknown'}${c.profile_id ? ` (${c.profile_id})` : ''}`)
          .join(', ') || 'none detected';
        const healthFiles = (health?.emulators || []).map((h) => ({
          id: h.id,
          status: h.status,
          current: h.currentFile,
          defaults: h.defaultsFile,
          details: h.details,
        }));
        const contextInfo = {
          panel: 'console-wizard',
          emulators: emulators.map((e) => ({
            id: e.id,
            name: e.displayName,
            configFormat: e.configFormat,
            status: e.status,
            statusReason: e.statusReason,
          })),
          health: health?.status,
          controllers: controllerSummary,
          controllersCount: detectedControllers.length,
          healthFiles,
          tendenciesProfileId,
          tendencies: tendenciesData,
        };
        const systemPrompt = `You are Wiz, the Console Wizard AI assistant. Keep responses concise (1-2 sentences).

CRITICAL INSTRUCTIONS FOR RETROARCH CONFIGURATIONS:
- When user says "I want left stick AND d-pad to do the same thing" or "both control directions" ? They want DUAL MAPPING (both inputs mapped to same function)
- When user says "I want left stick to NOT control directions" or "only d-pad" ? They want SEPARATE MAPPING (only d-pad mapped)
- ALWAYS confirm what the user wants BEFORE generating config
- Say exactly what you understood: "So you want [LEFT STICK + D-PAD] to both control directions?" OR "So you want [ONLY D-PAD] to control directions?"
- Wait for user confirmation before proceeding
- Do NOT contradict yourself - if user says "both do same thing" don't say "separate functions"
- When user confirms with "yes" or similar, PROCEED with the configuration steps, do NOT ask generic questions

IMPORTANT: The user has already been talking to you. Maintain context from all previous messages. Do not restart the conversation or ask what emulator they want if they already told you.

You may read configs via Console Wizard endpoints (generate, health, config/{emulator}) and suggest applies/restores when needed. Use detected controllers if available; otherwise ask the user what they are holding.

Current context: ${JSON.stringify(contextInfo)}`;
        const history = [...chatMessagesRef.current, { text: userMessage, sender: 'user' }];
        // Use 20 messages instead of 8 to maintain context across more turns
        const historyMessages = history
          .slice(-20)
          .map((msg) => ({
            role: msg.sender === 'assistant' ? 'assistant' : 'user',
            content: msg.text,
          }));

        const response = await fetch('/api/ai/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-device-id': window?.AA_DEVICE_ID ?? 'cabinet-001',
            'x-scope': 'state',
            'x-panel': 'console-wizard',
          },
          body: JSON.stringify({
            messages: [
              { role: 'system', content: systemPrompt },
              ...historyMessages,
            ],
          }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.message || errorData.detail || `AI chat failed: ${response.statusText}`);
        }

        const data = await response.json();
        const assistantReply = data.message?.content || data.response || 'I encountered an error processing your request.';
        addChatMessage(assistantReply, 'assistant');

        // Check if the assistant is asking for confirmation - set pending state
        if (detectConfirmationAsk(assistantReply)) {
          const context = extractConfirmationContext([...chatMessagesRef.current, { text: userMessage, sender: 'user' }]);
          setPendingConfirmation(context);
          console.info('[ConsoleWizard] Pending confirmation set:', context);
        }
      } catch (err) {
        console.error('[ConsoleWizard] Chat error:', err);
        addChatMessage(`Sorry, I encountered an error: ${err.message}`, 'assistant');
      } finally {
        setChatLoading(false);
      }
    },
    [emulators, health, detectedControllers, tendenciesProfileId, tendenciesData, addChatMessage, pendingConfirmation, isYesResponse, isNoResponse, detectConfirmationAsk, extractConfirmationContext],
  );

  const handleChatSend = useCallback(async () => {
    if (!chatInput.trim() || chatLoading) return;
    const userMessage = chatInput.trim();
    setChatInput('');
    await sendChat(userMessage);
  }, [chatInput, chatLoading, sendChat]);

  useEffect(() => () => {
    try {
      stopTTS();
    } catch (err) {
      console.warn('[ConsoleWizard] Failed to stop TTS on unmount:', err);
    }
  }, []);

  const handleChatKeyPress = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleChatSend();
      }
    },
    [handleChatSend],
  );

  // Voice recording functions
  const cleanupVoiceStream = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => {
        try { track.stop(); } catch (err) { console.warn(err); }
      });
      mediaStreamRef.current = null;
    }
  }, []);

  const sendVoiceMessage = useCallback((payload) => {
    if (typeof WebSocket === 'undefined') return false;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    try {
      ws.send(JSON.stringify(payload));
      return true;
    } catch (err) {
      console.error('[ConsoleWizard] Voice send failed:', err);
      return false;
    }
  }, []);

  const handleVoiceTranscript = useCallback(async (payload) => {
    setIsRecording(false);
    setListeningLabel(false);
    if (!payload) return;
    if (payload.code === 'NOT_CONFIGURED') {
      addChatMessage('Voice transcription is not configured. Add an OpenAI key in settings.', 'assistant');
      return;
    }
    const text = payload.text || payload.transcript || payload.message;
    if (typeof text === 'string' && text.trim()) {
      setChatInput('');
      await sendChat(text);
    } else {
      addChatMessage('Sorry, no transcription was returned.', 'assistant');
    }
  }, [addChatMessage, sendChat]);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof WebSocket === 'undefined') return;
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${proto}://${window.location.host}/ws/audio`;
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg?.type === 'transcription') {
          handleVoiceTranscript(msg);
        }
      } catch (err) {
        console.error('[ConsoleWizard] Voice socket parse error', err);
      }
    };

    socket.onclose = () => {
      wsRef.current = null;
      setIsRecording(false);
    };

    return () => {
      try { socket.close(); } catch { }
      wsRef.current = null;
    };
  }, [handleVoiceTranscript]);

  const stopVoiceRecording = useCallback((options = {}) => {
    const { skipSignal = false } = options;
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      try { recorder.stop(); } catch (e) { console.error(e); }
    }
    mediaRecorderRef.current = null;
    cleanupVoiceStream();
    if (!skipSignal) {
      sendVoiceMessage({ type: 'stop_recording' });
    }
    setIsRecording(false);
    setListeningLabel(false);
  }, [cleanupVoiceStream, sendVoiceMessage]);

  const startVoiceRecording = useCallback(async () => {
    // Prefer Web Speech API if available
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsRecording(true);
        setListeningLabel(true);
      };
      recognition.onresult = async (event) => {
        if (!event.results[0].isFinal) return;
        const transcript = event.results[0][0].transcript;
        await handleVoiceTranscript({ text: transcript });
      };
      recognition.onerror = (event) => {
        console.error('[ConsoleWizard] Speech recognition error:', event.error);
        addChatMessage(`Speech recognition error: ${event.error}`, 'assistant');
        setIsRecording(false);
        setListeningLabel(false);
      };
      recognition.onend = () => {
        setIsRecording(false);
        setListeningLabel(false);
      };
      try {
        recognition.start();
        mediaRecorderRef.current = { stop: () => recognition.stop() };
      } catch (err) {
        console.error('[ConsoleWizard] Failed to start speech recognition:', err);
        addChatMessage('Failed to start speech recognition.', 'assistant');
      }
      return;
    }

    if (!navigator?.mediaDevices?.getUserMedia || typeof window.MediaRecorder === 'undefined') {
      addChatMessage('Microphone not supported in this browser', 'system');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const options = pickRecorderOptions();
      const recorder = options ? new MediaRecorder(stream, options) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      chunkSequenceRef.current = 0;

      recorder.ondataavailable = async (event) => {
        if (!event.data || event.data.size === 0) return;
        try {
          const buffer = await event.data.arrayBuffer();
          const chunk = arrayBufferToBase64(buffer);
          chunkSequenceRef.current += 1;
          const ok = sendVoiceMessage({ type: 'audio_chunk', chunk, data: chunk, sequence: chunkSequenceRef.current });
          if (!ok) {
            addChatMessage('Voice service unavailable. Refresh and try again.', 'assistant');
            stopVoiceRecording({ skipSignal: true });
          }
        } catch (err) {
          console.error('[ConsoleWizard] Failed to process audio chunk', err);
          addChatMessage('Failed to process microphone audio.', 'assistant');
        }
      };

      recorder.onerror = (event) => {
        console.error('[ConsoleWizard] Recorder error:', event);
        addChatMessage('Microphone error occurred', 'system');
        stopVoiceRecording({ skipSignal: true });
      };

      if (!sendVoiceMessage({ type: 'start_recording' })) {
        addChatMessage('Voice service unavailable. Refresh and try again.', 'assistant');
        stopVoiceRecording({ skipSignal: true });
        return;
      }

      recorder.start(250);
      setIsRecording(true);
      setListeningLabel(true);
    } catch (err) {
      console.error('[ConsoleWizard] Microphone access denied:', err);
      addChatMessage('Microphone permission denied', 'system');
    }
  }, [addChatMessage, handleVoiceTranscript, sendVoiceMessage, stopVoiceRecording]);

  const toggleMic = useCallback(() => {
    // If assistant is speaking, stop TTS immediately to prioritize user voice
    try {
      stopTTS();
    } catch (err) {
      console.warn('[ConsoleWizard] Failed to stop TTS before recording:', err);
    }
    if (isRecording) {
      stopVoiceRecording();
    } else {
      startVoiceRecording();
    }
  }, [isRecording, startVoiceRecording, stopVoiceRecording]);

  const handleDetectControllers = useCallback(async () => {
    setControllerDetectionLoading(true);
    setControllerDetectionError(null);
    logEvent('Controller detection started');

    try {
      const response = await fetchJSON(ENDPOINTS.controllers, {
        method: 'GET',
        scope: DEFAULT_SCOPE,
      });

      const controllers = response?.controllers ?? [];
      setDetectedControllers(controllers);
      logEvent('Controller detection complete', {
        count: controllers.length,
        controllers: controllers.map(c => c.name),
      });

      if (controllers.length === 0) {
        setToast({
          type: 'info',
          text: 'No controllers detected. Please plug in a controller and try again.',
        });
      } else {
        setToast({
          type: 'success',
          text: `Detected ${controllers.length} controller${controllers.length > 1 ? 's' : ''}: ${controllers.map(c => c.name).join(', ')}`,
        });
      }
    } catch (err) {
      const errorMsg = err.message ?? 'Failed to detect controllers';
      setControllerDetectionError(errorMsg);
      showErrorToast('Controller detection failed', err);
      logEvent('Controller detection failed', { error: err?.message });
    } finally {
      setControllerDetectionLoading(false);
    }
  }, [fetchJSON, logEvent, showErrorToast]);

  const handleAutoConfigureAll = useCallback(async () => {
    if (!detectedControllers.length) {
      setToast({
        type: 'warning',
        text: 'No controllers detected. Please detect a controller first.',
      });
      return;
    }

    const controller = detectedControllers[0]; // Use first detected controller
    const confirmMsg = `Auto-configure all ${emulators.length} emulators for ${controller.name}?\n\nThis will generate configs using the standard ${controller.name} button layout.`;

    if (!window.confirm(confirmMsg)) {
      return;
    }

    setAutoConfiguring(true);
    setAutoConfigProgress({ current: 0, total: emulators.length, status: 'Starting...' });
    setPanelError(null);
    logEvent('Auto-configure all started', {
      controller: controller.name,
      profile_id: controller.profile_id,
      emulator_count: emulators.length,
    });

    try {
      // Generate configs for ALL emulators (no filter = all emulators)
      const response = await fetchJSON(ENDPOINTS.generateConfigs, {
        method: 'POST',
        scope: MUTATION_SCOPE,
        body: {
          dry_run: false,
          // No emulators filter = generate for all
        },
      });

      const results = response?.results ?? [];
      const successCount = results.filter(r => r.status === 'written').length;

      setAutoConfigProgress({
        current: results.length,
        total: results.length,
        status: 'Complete',
      });

      setToast({
        type: 'success',
        text: `Auto-configuration complete! Configured ${successCount} of ${results.length} emulators for ${controller.name}.`,
      });

      logEvent('Auto-configure all complete', {
        controller: controller.name,
        success_count: successCount,
        total_count: results.length,
      });

      // Refresh emulator list and health
      refreshAll();
    } catch (err) {
      const errorMsg = err.message ?? 'Auto-configuration failed';
      setPanelError(errorMsg);
      showErrorToast('Auto-configuration failed', err);
      logEvent('Auto-configure all failed', {
        controller: controller?.name,
        error: err?.message,
      });
    } finally {
      setAutoConfiguring(false);
      setTimeout(() => setAutoConfigProgress(null), 3000);
    }
  }, [
    detectedControllers,
    emulators,
    fetchJSON,
    logEvent,
    showErrorToast,
    refreshAll,
  ]);

  useEffect(() => {
    logEvent('Panel loaded');
    refreshAll();
    // Check for handoff context from Dewey
    const urlParams = new URLSearchParams(window.location.search);
    const handoffContext = urlParams.get('context');
    const hasHandoff = Boolean((handoffContext || '').trim());
    const noHandoff = urlParams.has('nohandoff');
    const shouldHandoff = hasHandoff && !noHandoff;

    // Only process if we have context AND it's different from last processed context
    if (shouldHandoff && handoffContext !== handoffProcessedRef.current) {
      const welcomeMsg = `Hi! Dewey told me you said: "${handoffContext}"\n\nI'm Console Wizard, and I can help you with controller configuration for emulators. What would you like me to do?`;
      handoffProcessedRef.current = handoffContext; // Store the processed context
      initialGreetingRef.current = true;
      addChatMessage(welcomeMsg, 'assistant', { speak: true }); // Enable voice on handoff
      setChatOpen(true);
    } else if (!hasHandoff && !initialGreetingRef.current) {
      // Default greeting if no handoff
      const defaultMsg = "Hi, I'm Wiz. I can help you configure your emulators. Just ask!";
      addChatMessage(defaultMsg, 'assistant', { speak: true });
      initialGreetingRef.current = true;
      // Don't auto-open chat for default greeting to be less intrusive? 
      // User said "The AI would then talk", so speech is key.
      // Let's NOT auto-open chat window for default, just speak.
      // But addChatMessage adds to history.
    }

    // Check for JSON handoff from Dewey (only when arriving via Dewey URL context)
    if (shouldHandoff) (async () => {
      try {
        const result = await fetchJSON('/api/local/dewey/handoff/console_wizard');
        if (result && result.handoff) {
          const rawSummary = typeof result.handoff.summary === 'string'
            ? result.handoff.summary
            : JSON.stringify(result.handoff);

          const summaryText = (rawSummary || '').trim();
          if (summaryText && summaryText !== handoffProcessedRef.current) {
            handoffProcessedRef.current = summaryText;
            const welcomeMsg = `Dewey briefed me that you're dealing with: "${summaryText}". Let's tackle it together.`;
            initialGreetingRef.current = true;
            addChatMessage(welcomeMsg, 'assistant', { speak: true });
            setChatOpen(true);
          }
        }
      } catch (err) {
        console.warn('[ConsoleWizard] Handoff fetch failed:', err);
      }
    })();

    // Load tendencies for contextual AI replies (shared with Vicky Voice)
    try {
      const profileId =
        window?.AA_PROFILE_ID ||
        localStorage.getItem('aa_profile_id') ||
        'default';
      setTendenciesProfileId(profileId);
      fetch(`/profiles/${profileId}/tendencies.json`, { cache: 'no-store' })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data && typeof data === 'object') {
            setTendenciesData(data);
          }
        })
        .catch((err) => console.warn('[ConsoleWizard] Tendencies load failed', err));
    } catch (err) {
      console.warn('[ConsoleWizard] Tendencies initialization failed', err);
    }
    // Stop any ongoing TTS when this panel unmounts
    return () => { try { stopTTS() } catch { } }
  }, [logEvent, refreshAll, addChatMessage]);

  useEffect(() => {
    if (!emulators.length) {
      setSelectedEmulatorId(null);
      return;
    }
    const exists = emulators.some((emu) => emu.id === selectedEmulatorId);
    if (!exists) {
      setSelectedEmulatorId(emulators[0].id);
      setDetailsTab('summary');
    }
  }, [emulators, selectedEmulatorId]);

  useEffect(() => {
    if (!toast) return undefined;
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 6000);
    return () => {
      if (toastTimerRef.current) {
        clearTimeout(toastTimerRef.current);
        toastTimerRef.current = null;
      }
    };
  }, [toast]);

  const healthMap = useMemo(() => {
    const map = new Map();
    health?.emulators?.forEach((entry) => map.set(entry.id, entry));
    return map;
  }, [health]);

  const emulatorMap = useMemo(() => {
    const map = new Map();
    emulators.forEach((emu) => map.set(emu.id, emu));
    return map;
  }, [emulators]);

  const attentionEntries = useMemo(
    () =>
      health?.emulators?.filter((entry) =>
        healthAttention.has(entry.status),
      ) ?? [],
    [health],
  );

  const filteredEmulators = useMemo(() => {
    if (statusFilter !== 'attention') return emulators;
    return emulators.filter((emu) => {
      if (statusAttention.has(emu.status)) return true;
      const entry = healthMap.get(emu.id);
      return entry ? healthAttention.has(entry.status) : false;
    });
  }, [emulators, statusFilter, healthMap]);

  const selectedEmulator = selectedEmulatorId
    ? emulatorMap.get(selectedEmulatorId)
    : null;
  const selectedHealth = selectedEmulatorId
    ? healthMap.get(selectedEmulatorId)
    : null;

  const previewMap = useMemo(() => {
    const map = new Map();
    previewResult?.emulators?.forEach((entry) => map.set(entry.id, entry));
    return map;
  }, [previewResult]);

  const selectedPreviewEntry = selectedEmulatorId
    ? previewMap.get(selectedEmulatorId)
    : null;

  const selectedQuirks = useMemo(
    () =>
      quirkResults.filter(
        (quirk) => quirk.emulatorId === selectedEmulatorId,
      ),
    [quirkResults, selectedEmulatorId],
  );

  const panelStatus = PANEL_STATUS_META[
    healthUnavailable ? 'warning' : health?.status ?? 'warning'
  ] ?? PANEL_STATUS_META.warning;

  const renderActiveTab = () => {
    switch (activeNav) {
      case 'dashboard':
        return (
          <DashboardTab
            emulators={emulators}
            filteredEmulators={filteredEmulators}
            selectedEmulatorId={selectedEmulatorId}
            selectedEmulator={selectedEmulator}
            selectedHealth={selectedHealth}
            selectedPreviewEntry={selectedPreviewEntry}
            selectedQuirks={selectedQuirks}
            healthMap={healthMap}
            healthUnavailable={healthUnavailable}
            healthMessage={healthMessage}
            health={health}
            statusFilter={statusFilter}
            setStatusFilter={setStatusFilter}
            setSelectedEmulatorId={setSelectedEmulatorId}
            setDetailsTab={setDetailsTab}
            detailsTab={detailsTab}
            attentionEntries={attentionEntries}
            panelStatus={panelStatus}
            scanInFlight={scanInFlight}
            refreshAll={refreshAll}
            handlePreviewAll={handlePreviewAll}
            previewLoading={previewLoading}
            previewResult={previewResult}
            previewModalOpen={previewModalOpen}
            handleRestoreEmulator={handleRestoreEmulator}
            handleRestoreAll={handleRestoreAll}
            restoringEmulatorId={restoringEmulatorId}
            restoringAll={restoringAll}
            settingDefaults={settingDefaults}
            lastActions={lastActions}
            detectedControllers={detectedControllers}
            controllerDetectionLoading={controllerDetectionLoading}
            controllerDetectionError={controllerDetectionError}
            autoConfiguring={autoConfiguring}
            autoConfigProgress={autoConfigProgress}
            handleDetectControllers={handleDetectControllers}
            handleAutoConfigureAll={handleAutoConfigureAll}
            chuckStatus={chuckStatus}
            requiresRestart={requiresRestart}
            quirkResults={quirkResults}
            tendenciesData={tendenciesData}
            tendenciesProfileId={tendenciesProfileId}
            describeHealth={describeHealth}
            showDevErrorDetails={showDevErrorDetails}
            formatSystems={formatSystems}
            relativeTime={relativeTime}
          />
        )
      case 'diff':
        return (
          <VisualDiffTab
            previewResult={previewResult}
            previewLoading={previewLoading}
            emulatorMap={emulatorMap}
            handlePreviewAll={handlePreviewAll}
            onApply={handleApplyPreview}
            applyInFlight={applyInFlight}
          />
        )
      case 'logs':
        return <ActivityLogTab logs={activityLogs} />
      case 'controller-setup':
        return (
          <GamepadSetupOverlay
            fetchJSON={fetchJSON}
            onClose={() => setActiveNav('dashboard')}
          />
        )
      default:
        return null
    }
  }

  return (
    <div className="wiz-layout" style={{ display: 'flex', width: '100%', alignItems: 'flex-start' }}>
      <WizNavSidebar activeTab={activeNav} onTabChange={setActiveNav} onChatToggle={() => setChatOpen(v => !v)} />
      <div className="console-wizard-panel" style={{ flex: 1, minWidth: 0 }}>
        <header className="console-wizard-header">
          <div className="panel-heading">
            <h1>Console Wizard</h1>
            <p>Auto-configure console emulators from your controller mapping.</p>
          </div>
          <div className="panel-actions">
            <span className={`status-pill ${panelStatus.tone}`}>
              {panelStatus.label}
            </span>
          </div>
        </header>

        {panelError && (
          <div className="panel-banner error">
            <div>
              <strong>Something went wrong.</strong>
              <span>{panelError}</span>
            </div>
            <button type="button" className="text" onClick={handleDismissError}>
              Dismiss
            </button>
          </div>
        )}

        {backendDisconnected && (
          <div className="panel-banner warning">
            <div>
              <strong>Backend offline.</strong>
              <span>{backendDisconnectMessage || 'Start the backend service and retry.'}</span>
            </div>
          </div>
        )}

        {pendingExecution && (
          <ExecutionCard
            proposal={pendingExecution}
            onExecute={handleExecutePreviewApply}
            onCancel={handleCancelPreviewApply}
            loading={applyInFlight}
          />
        )}

        {/* -- Tab Content ----------------------- */}
        {renderActiveTab()}

        {/* -- Toasts & Modals (overlay all tabs) -- */}
        {toast && (
          <div className={`action-toast ${toast.type}`}>
            <span>{toast.text}</span>
            <div>
              {toast.actionLabel && toast.actionHandler && (
                <button type="button" onClick={toast.actionHandler}>
                  {toast.actionLabel}
                </button>
              )}
              <button type="button" className="text" onClick={handleDismissToast}>
                Close
              </button>
            </div>
          </div>
        )}

        {previewModalOpen && (
          <PreviewModal
            preview={previewResult}
            error={previewError}
            onClose={handleClosePreviewModal}
            loading={previewLoading}
            onApply={handleApplyPreview}
            applying={applyInFlight}
            emulatorMap={emulatorMap}
            onRetry={handleRetryPreview}
          />
        )}

        {devErrorDetails && (
          <DevErrorModal error={devErrorDetails} onClose={handleCloseDevError} />
        )}
      </div>
      <div className={`eb-chat-backdrop ${chatOpen ? 'eb-chat-backdrop--visible' : ''}`} onClick={() => setChatOpen(false)} />
      <div className={`eb-chat-drawer ${chatOpen ? 'eb-chat-drawer--open' : ''}`}>
        <button type='button' className='eb-chat-drawer__close' onClick={() => setChatOpen(false)} aria-label='Close sidebar'>X</button>
        <EngineeringBaySidebar persona={WIZ_PERSONA} contextAssembler={assembleWizContext} />
      </div>
    </div>
  );
}


function PreviewModal({
  preview,
  error,
  onClose,
  loading,
  onApply,
  applying,
  emulatorMap,
  onRetry,
}) {
  const [expandedIds, setExpandedIds] = useState([]);

  useEffect(() => {
    if (!preview?.emulators) {
      setExpandedIds([]);
      return;
    }
    setExpandedIds(preview.emulators.map((entry) => entry.id));
  }, [preview]);

  const toggleExpanded = (id) => {
    setExpandedIds((prev) =>
      prev.includes(id) ? prev.filter((entry) => entry !== id) : [...prev, id],
    );
  };

  const hasPreviewData = Boolean(preview);
  const previewHasDiffs = Boolean(preview?.emulators?.length);
  const { emulatorCount, fileCount } = hasPreviewData
    ? previewCounts(preview)
    : { emulatorCount: 0, fileCount: 0 };

  return (
    <div className="wizard-modal-backdrop" role="dialog" aria-modal="true">
      <div className="wizard-modal">
        <header>
          <h3>Preview Config Changes</h3>
          <button type="button" className="text" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="modal-body">
          {error && <div className="modal-error">{error}</div>}
          {loading && <p>Loading previewâ€¦</p>}
          {!loading && hasPreviewData && (
            <>
              <p className="modal-summary">
                Will update configs for {emulatorCount} emulator
                {emulatorCount === 1 ? '' : 's'}, {fileCount} file
                {fileCount === 1 ? '' : 's'} total.
              </p>
              {preview?.summary && <p className="modal-copy">{preview.summary}</p>}
            </>
          )}
          {!loading && previewHasDiffs && (
            <ul className="preview-groups">
              {preview?.emulators?.map((entry) => {
                const source = emulatorMap.get(entry.id);
                const isExpanded = expandedIds.includes(entry.id);
                return (
                  <li key={entry.id} className="preview-group">
                    <div className="preview-header">
                      <div>
                        <strong>{entry.displayName}</strong>
                        {source?.status && (
                          <span className={`status-chip ${source.status}`}>
                            {STATUS_LABELS[source.status] ?? 'OK'}
                          </span>
                        )}
                      </div>
                      <button
                        type="button"
                        className="text"
                        onClick={() => toggleExpanded(entry.id)}
                      >
                        {isExpanded ? 'Hide files' : 'Show files'} (
                        {entry.files?.length ?? 0})
                      </button>
                    </div>
                    {isExpanded && (
                      <ul className="preview-files">
                        {entry.files?.map((file) => (
                          <li key={file.relativePath}>
                            <div className="diff-heading">
                              <span>{file.relativePath}</span>
                              <span className={`chip ${file.changeType}`}>
                                {file.changeType}
                              </span>
                            </div>
                            {(file.before || file.after) && (
                              <div className="diff-body">
                                {file.before && (
                                  <pre>
                                    <strong>Before</strong>
                                    <code>{file.before}</code>
                                  </pre>
                                )}
                                {file.after && (
                                  <pre>
                                    <strong>After</strong>
                                    <code>{file.after}</code>
                                  </pre>
                                )}
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {!loading && hasPreviewData && !previewHasDiffs && !error && (
            <p className="modal-copy">
              Console Wizard did not detect any config changes for this selection.
            </p>
          )}
          {!loading && !hasPreviewData && !error && (
            <p className="modal-copy">No preview data available yet.</p>
          )}
        </div>
        <footer className="modal-footer">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          {error && onRetry && (
            <button type="button" className="ghost" onClick={onRetry} disabled={loading}>
              Retry Preview
            </button>
          )}
          <button
            type="button"
            className="primary"
            onClick={onApply}
            disabled={applying || !previewHasDiffs}
          >
            {applying ? 'Applying...' : 'Apply Changes'}
          </button>
        </footer>
      </div>
    </div>
  );
}

function DevErrorModal({ error, onClose }) {
  if (!error) return null;
  return (
    <div className="wizard-modal-backdrop" role="dialog" aria-modal="true">
      <div className="wizard-modal">
        <header>
          <h3>{error.title ?? 'Error details'}</h3>
          <button type="button" className="text" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="modal-body">
          <pre className="dev-error-body">{error.details}</pre>
        </div>
        <footer className="modal-footer">
          <button type="button" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </div>
  );
}
