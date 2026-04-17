import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import PropTypes from 'prop-types';
import PanelShell from '../panels/_kit/PanelShell';
import { buildStandardHeaders } from '../utils/identity';

const CONTROLLER_API = '/api/local/controller';
const HARDWARE_API = '/api/local/hardware';

function buildHeaders(scope = 'state', json = false) {
  return buildStandardHeaders({
    panel: 'controller-wizard',
    scope,
    extraHeaders: json ? { 'Content-Type': 'application/json' } : {},
  });
}

async function requestJson(path, { method = 'GET', scope = 'state', body, signal } = {}) {
  const response = await fetch(path, {
    method,
    headers: buildHeaders(scope, body !== undefined),
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (!response.ok) {
    const message =
      payload?.detail?.message
      || payload?.detail
      || payload?.message
      || `${method} ${path} failed (${response.status})`;
    throw new Error(message);
  }

  return payload;
}

function formatControlKey(controlKey) {
  if (!controlKey) return 'Waiting';
  return controlKey
    .replace(/\./g, ' ')
    .replace(/\bp(\d)\b/gi, 'P$1')
    .replace(/\bbutton(\d+)\b/gi, 'Button $1')
    .replace(/\bcoin\b/gi, 'Coin')
    .replace(/\bstart\b/gi, 'Start')
    .replace(/\bup\b/gi, 'Up')
    .replace(/\bdown\b/gi, 'Down')
    .replace(/\bleft\b/gi, 'Left')
    .replace(/\bright\b/gi, 'Right')
    .replace(/\s+/g, ' ')
    .trim();
}

const StepIndicator = React.memo(({ stepNumber, label, isActive, isComplete }) => (
  <div className={`wizard-step ${isActive ? 'active' : ''} ${isComplete ? 'complete' : ''}`}>
    <div className="step-number">{isComplete ? '✓' : stepNumber}</div>
    <div className="step-label">{label}</div>
  </div>
));

StepIndicator.propTypes = {
  stepNumber: PropTypes.number.isRequired,
  label: PropTypes.string.isRequired,
  isActive: PropTypes.bool,
  isComplete: PropTypes.bool,
};

function ControllerWizardPanel() {
  const steps = useMemo(() => [
    { id: 'detect', label: 'Detect', description: 'Confirm the encoder and live input feed.' },
    { id: 'map', label: 'Map', description: 'Capture physical controls into the wizard session.' },
    { id: 'test', label: 'Test', description: 'Preview the pending wiring changes.' },
    { id: 'export', label: 'Export', description: 'Apply the wizard session to controls.json.' },
  ], []);

  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState(new Set());
  const [controllers, setControllers] = useState([]);
  const [latestInput, setLatestInput] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [wizard, setWizard] = useState({
    sessionId: null,
    buttons: [],
    captures: {},
    nextButton: null,
    progress: 0,
    total: 0,
    detectedBoard: null,
    detectedMode: null,
    modeWarning: null,
    preview: null,
    applyResult: null,
  });

  const sessionIdRef = useRef(null);
  const lastInputTimestampRef = useRef(null);

  const loadControllers = useCallback(async (signal) => {
    const data = await requestJson(`${HARDWARE_API}/arcade/boards`, { signal });
    setControllers(Array.isArray(data?.boards) ? data.boards : []);
  }, []);

  const startWizard = useCallback(async (signal) => {
    const data = await requestJson(`${CONTROLLER_API}/wizard/start`, {
      method: 'POST',
      scope: 'state',
      body: { player_mode: '4p' },
      signal,
    });

    sessionIdRef.current = data.session_id || null;
    setWizard({
      sessionId: data.session_id || null,
      buttons: Array.isArray(data?.buttons) ? data.buttons : [],
      captures: {},
      nextButton: data.next_button || data.next || null,
      progress: data.progress || 0,
      total: data.total || 0,
      detectedBoard: data.detected_board || 'Unknown board',
      detectedMode: data.detected_mode || 'unknown',
      modeWarning: data.mode_warning || null,
      preview: null,
      applyResult: null,
    });
    setIsConnected(true);
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    (async () => {
      setIsLoading(true);
      setError('');
      try {
        await Promise.all([
          loadControllers(controller.signal),
          startWizard(controller.signal),
        ]);
      } catch (err) {
        setError(err.message || 'Failed to initialize the controller wizard.');
        setIsConnected(false);
      } finally {
        setIsLoading(false);
      }
    })();

    return () => {
      controller.abort();
      if (sessionIdRef.current) {
        fetch(`${CONTROLLER_API}/wizard/cancel`, {
          method: 'POST',
          headers: buildHeaders('state', true),
          body: JSON.stringify({ session_id: sessionIdRef.current }),
        }).catch(() => {});
      }
    };
  }, [loadControllers, startWizard]);

  useEffect(() => {
    if (!wizard.sessionId) return undefined;

    let cancelled = false;
    const pollLatest = async () => {
      try {
        const data = await requestJson(`${CONTROLLER_API}/input/latest`);
        const event = data?.event || null;
        if (!cancelled && event?.timestamp && event.timestamp !== lastInputTimestampRef.current) {
          lastInputTimestampRef.current = event.timestamp;
          setLatestInput(event);
        }
      } catch {
        if (!cancelled) {
          setIsConnected(false);
        }
      }
    };

    pollLatest();
    const intervalId = window.setInterval(pollLatest, 700);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [wizard.sessionId]);

  const captureCurrentInput = useCallback(async () => {
    if (!wizard.sessionId || !wizard.nextButton) {
      setError('Wizard session is not ready for a capture yet.');
      return;
    }
    if (!latestInput) {
      setError('Press a physical control first so the wizard has a live input event to capture.');
      return;
    }

    setIsLoading(true);
    setError('');
    try {
      const response = await requestJson(`${CONTROLLER_API}/wizard/capture`, {
        method: 'POST',
        scope: 'state',
        body: {
          session_id: wizard.sessionId,
          button_name: wizard.nextButton,
          input_event: latestInput,
        },
      });

      setWizard((prev) => ({
        ...prev,
        captures: {
          ...prev.captures,
          [wizard.nextButton]: latestInput,
        },
        nextButton: response.next_button || response.next || null,
        progress: response.progress || prev.progress,
        total: response.total || prev.total,
      }));
    } catch (err) {
      setError(err.message || 'Failed to capture the latest input.');
    } finally {
      setIsLoading(false);
    }
  }, [latestInput, wizard.nextButton, wizard.sessionId]);

  const skipCurrentInput = useCallback(async () => {
    if (!wizard.sessionId || !wizard.nextButton) return;

    setIsLoading(true);
    setError('');
    try {
      const response = await requestJson(`${CONTROLLER_API}/wizard/capture`, {
        method: 'POST',
        scope: 'state',
        body: {
          session_id: wizard.sessionId,
          button_name: wizard.nextButton,
          skip: true,
        },
      });

      setWizard((prev) => ({
        ...prev,
        captures: {
          ...prev.captures,
          [wizard.nextButton]: { skipped: true },
        },
        nextButton: response.next_button || response.next || null,
        progress: response.progress || prev.progress,
        total: response.total || prev.total,
      }));
    } catch (err) {
      setError(err.message || 'Failed to skip the current control.');
    } finally {
      setIsLoading(false);
    }
  }, [wizard.nextButton, wizard.sessionId]);

  const undoCapture = useCallback(async () => {
    if (!wizard.sessionId) return;

    setIsLoading(true);
    setError('');
    try {
      const response = await requestJson(`${CONTROLLER_API}/wizard/capture`, {
        method: 'POST',
        scope: 'state',
        body: {
          session_id: wizard.sessionId,
          rollback: true,
        },
      });

      setWizard((prev) => {
        const captures = { ...prev.captures };
        if (response.button_name) {
          delete captures[response.button_name];
        }

        return {
          ...prev,
          captures,
          nextButton: response.next_button || response.next || prev.nextButton,
          progress: response.progress || 0,
          total: response.total || prev.total,
        };
      });
    } catch (err) {
      setError(err.message || 'Failed to undo the last capture.');
    } finally {
      setIsLoading(false);
    }
  }, [wizard.sessionId]);

  const loadPreview = useCallback(async () => {
    if (!wizard.sessionId) return null;

    const preview = await requestJson(`${CONTROLLER_API}/wizard/preview`, {
      method: 'POST',
      scope: 'state',
      body: { session_id: wizard.sessionId },
    });

    setWizard((prev) => ({
      ...prev,
      preview,
    }));

    return preview;
  }, [wizard.sessionId]);

  const handleNext = useCallback(async () => {
    const stepId = steps[currentStep]?.id;
    if (!stepId) return;

    setError('');

    try {
      if (stepId === 'detect') {
        setCompletedSteps((prev) => new Set([...prev, 'detect']));
        setCurrentStep(1);
        return;
      }

      if (stepId === 'map') {
        await loadPreview();
        setCompletedSteps((prev) => new Set([...prev, 'map']));
        setCurrentStep(2);
        return;
      }

      if (stepId === 'test') {
        setCompletedSteps((prev) => new Set([...prev, 'test']));
        setCurrentStep(3);
      }
    } catch (err) {
      setError(err.message || 'Unable to advance the wizard.');
    }
  }, [currentStep, loadPreview, steps]);

  const handleBack = useCallback(() => {
    setError('');
    if (currentStep > 0) {
      setCurrentStep((prev) => prev - 1);
    }
  }, [currentStep]);

  const handleFinish = useCallback(async () => {
    if (!wizard.sessionId) return;

    setIsLoading(true);
    setError('');
    try {
      const applyResult = await requestJson(`${CONTROLLER_API}/wizard/apply`, {
        method: 'POST',
        scope: 'config',
        body: { session_id: wizard.sessionId },
      });

      setWizard((prev) => ({
        ...prev,
        applyResult,
      }));
      setCompletedSteps(new Set(steps.map((step) => step.id)));
      setIsConnected(true);
    } catch (err) {
      setError(err.message || 'Failed to apply the wizard session.');
    } finally {
      setIsLoading(false);
    }
  }, [steps, wizard.sessionId]);

  const captureEntries = Object.entries(wizard.captures);
  const previewChanges = Array.isArray(wizard.preview?.changes) ? wizard.preview.changes : [];

  const renderStepContent = useMemo(() => {
    const step = steps[currentStep];

    if (!step) return null;

    if (step.id === 'detect') {
      return (
        <div className="step-content detect-step">
          <h3>Encoder Detection</h3>
          <p>{wizard.modeWarning || 'Chuck found the current controller context and is ready to map controls.'}</p>
          <div className="config-summary">
            <div className="summary-item">
              <span>Detected Board:</span>
              <span>{wizard.detectedBoard || 'Unknown board'}</span>
            </div>
            <div className="summary-item">
              <span>Detection Mode:</span>
              <span>{wizard.detectedMode || 'unknown'}</span>
            </div>
            <div className="summary-item">
              <span>Controllers Seen:</span>
              <span>{controllers.length}</span>
            </div>
          </div>
          <div className="detected-controllers">
            <h4>Detected Controllers</h4>
            {controllers.length > 0 ? (
              <ul>
                {controllers.map((controller, index) => (
                  <li key={`${controller.vid || 'vid'}-${controller.pid || 'pid'}-${index}`} className="controller-item">
                    <span className="controller-icon">🎮</span>
                    {controller.name || 'Unknown controller'} ({controller.vid || 'n/a'}:{controller.pid || 'n/a'})
                  </li>
                ))}
              </ul>
            ) : (
              <p>No arcade boards are currently reported by the hardware route.</p>
            )}
          </div>
        </div>
      );
    }

    if (step.id === 'map') {
      return (
        <div className="step-content map-step">
          <h3>Capture Controls</h3>
          <p>The wizard uses the live `/api/local/controller/input/latest` feed. Press a control, then capture it into the highlighted slot.</p>
          <div className="config-summary">
            <div className="summary-item">
              <span>Next Control:</span>
              <span>{formatControlKey(wizard.nextButton)}</span>
            </div>
            <div className="summary-item">
              <span>Latest Input:</span>
              <span>{latestInput ? `${formatControlKey(latestInput.control_key)} • GPIO ${latestInput.pin}` : 'Waiting for input'}</span>
            </div>
            <div className="summary-item">
              <span>Progress:</span>
              <span>{wizard.progress} / {wizard.total}</span>
            </div>
          </div>
          <div className="wizard-footer" style={{ justifyContent: 'flex-start' }}>
            <button className="wizard-btn btn-next" onClick={captureCurrentInput} disabled={isLoading || !wizard.nextButton}>
              Capture Latest
            </button>
            <button className="wizard-btn btn-back" onClick={skipCurrentInput} disabled={isLoading || !wizard.nextButton}>
              Skip
            </button>
            <button className="wizard-btn btn-back" onClick={undoCapture} disabled={isLoading || captureEntries.length === 0}>
              Undo
            </button>
          </div>
          <div className="detected-controllers">
            <h4>Captured Controls</h4>
            {captureEntries.length > 0 ? (
              <ul>
                {captureEntries.map(([controlKey, capture]) => (
                  <li key={controlKey} className="controller-item">
                    <span className="controller-icon">{capture?.skipped ? '⏭' : '✓'}</span>
                    {formatControlKey(controlKey)} → {capture?.skipped ? 'Skipped' : `GPIO ${capture.pin ?? '?'}`}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No controls captured yet.</p>
            )}
          </div>
        </div>
      );
    }

    if (step.id === 'test') {
      return (
        <div className="step-content test-step">
          <h3>Preview Wiring Changes</h3>
          <p>This step reflects the live backend preview contract before the wizard writes to `controls.json`.</p>
          <div className="config-summary">
            <div className="summary-item">
              <span>Preview Status:</span>
              <span>{wizard.preview?.status || 'empty'}</span>
            </div>
            <div className="summary-item">
              <span>Preview Changes:</span>
              <span>{previewChanges.length}</span>
            </div>
            <div className="summary-item">
              <span>Latest Input Feed:</span>
              <span>{latestInput ? `${formatControlKey(latestInput.control_key)} • GPIO ${latestInput.pin}` : 'No recent event'}</span>
            </div>
          </div>
          <div className="detected-controllers">
            <h4>Pending Changes</h4>
            {previewChanges.length > 0 ? (
              <ul>
                {previewChanges.map((change) => (
                  <li key={change.control_key} className="controller-item">
                    <span className="controller-icon">🧩</span>
                    {formatControlKey(change.control_key)} → GPIO {change.new?.pin ?? '?'} ({change.action})
                  </li>
                ))}
              </ul>
            ) : (
              <p>No preview changes were returned. Capture at least one control before advancing.</p>
            )}
          </div>
        </div>
      );
    }

    return (
      <div className="step-content export-step">
        <div className="success-message">
          <div className="success-icon">{wizard.applyResult ? '🎉' : '📦'}</div>
          <h3>{wizard.applyResult ? 'Wizard Applied' : 'Ready To Export'}</h3>
          <p>
            {wizard.applyResult
              ? 'The wizard session has been committed to controls.json.'
              : 'Finish will apply the wizard session through the backend wiring route.'}
          </p>
          <div className="config-summary">
            <div className="summary-item">
              <span>Captured Controls:</span>
              <span>{captureEntries.length}</span>
            </div>
            <div className="summary-item">
              <span>Backup Path:</span>
              <span>{wizard.applyResult?.backup_path || 'Created on apply if configured'}</span>
            </div>
            <div className="summary-item">
              <span>Cascade:</span>
              <span>{wizard.applyResult?.cascade_result?.triggered ? 'Triggered' : (wizard.applyResult?.cascade_preference || 'Not applied yet')}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }, [
    captureCurrentInput,
    captureEntries,
    controllers,
    currentStep,
    isLoading,
    latestInput,
    loadPreview,
    previewChanges,
    skipCurrentInput,
    steps,
    undoCapture,
    wizard,
  ]);

  return (
    <PanelShell
      title="Controller Wizard - Guided Setup"
      subtitle="Live controller detection, mapping preview, and backend apply"
      icon={<img src="/wiz-avatar.jpeg" alt="Wiz" className="avatar-img" />}
      headerActions={(
        <div className="connection-status">
          <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
          <span>{isConnected ? 'Session Ready' : 'Disconnected'}</span>
        </div>
      )}
    >
      <div className="controller-wizard-panel">
        {error && (
          <div className="step-content" style={{ marginBottom: 16, border: '1px solid rgba(255,0,0,0.25)' }}>
            <strong>Wizard Error</strong>
            <p>{error}</p>
          </div>
        )}

        <div className="wizard-progress">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }}
            ></div>
          </div>
          <div className="step-indicators">
            {steps.map((step, idx) => (
              <StepIndicator
                key={step.id}
                stepNumber={idx + 1}
                label={step.label}
                isActive={idx === currentStep}
                isComplete={completedSteps.has(step.id)}
              />
            ))}
          </div>
        </div>

        <div className="wizard-body">
          {isLoading && !wizard.sessionId ? (
            <div className="step-content detect-step">
              <div className="detection-status">
                <div className="spinner"></div>
                <h3>Starting controller wizard…</h3>
              </div>
            </div>
          ) : renderStepContent}
        </div>

        <div className="wizard-footer">
          <button
            className="wizard-btn btn-back"
            onClick={handleBack}
            disabled={currentStep === 0 || isLoading}
          >
            Back
          </button>

          {currentStep < steps.length - 1 ? (
            <button
              className="wizard-btn btn-next"
              onClick={handleNext}
              disabled={isLoading || (steps[currentStep]?.id === 'map' && captureEntries.length === 0)}
            >
              {isLoading ? 'Processing...' : 'Next'}
            </button>
          ) : (
            <button
              className="wizard-btn btn-finish"
              onClick={handleFinish}
              disabled={isLoading || captureEntries.length === 0}
            >
              {isLoading ? 'Applying...' : (wizard.applyResult ? 'Applied' : 'Finish')}
            </button>
          )}
        </div>
      </div>
    </PanelShell>
  );
}

ControllerWizardPanel.propTypes = {};

export default ControllerWizardPanel;
