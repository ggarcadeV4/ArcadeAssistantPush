// frontend/src/components/ControllerWizardPanel.jsx

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import PanelShell from '../panels/_kit/PanelShell';
import PropTypes from 'prop-types';
import { getGatewayWsUrl } from '../services/gateway'

/**
 * WebSocket manager for Controller Wizard - extracted outside component for performance
 */
class ControllerWizardWebSocket {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.listeners = new Set();
    this.reconnectTimer = null;
    this.reconnectDelay = 1000;
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('Controller Wizard WebSocket connected');
        this.reconnectDelay = 1000;
        this.notifyListeners({ type: 'connected' });
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.notifyListeners(data);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      this.ws.onclose = () => {
        console.log('Controller Wizard WebSocket disconnected');
        this.notifyListeners({ type: 'disconnected' });
        this.scheduleReconnect();
      };

      this.ws.onerror = (error) => {
        console.error('Controller Wizard WebSocket error:', error);
        this.notifyListeners({ type: 'error', error });
      };
    } catch (err) {
      console.error('Failed to create WebSocket:', err);
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimer) return;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
      this.connect();
    }, this.reconnectDelay);
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket not connected, cannot send message');
    }
  }

  addListener(callback) {
    this.listeners.add(callback);
  }

  removeListener(callback) {
    this.listeners.delete(callback);
  }

  notifyListeners(data) {
    this.listeners.forEach(callback => callback(data));
  }
}

// Create singleton instance
const wsManager = new ControllerWizardWebSocket(getGatewayWsUrl('/controller_wizard/ws'));

/**
 * Step indicator component for wizard progress
 */
const StepIndicator = React.memo(({ stepNumber, label, isActive, isComplete }) => (
  <div className={`wizard-step ${isActive ? 'active' : ''} ${isComplete ? 'complete' : ''}`}>
    <div className="step-number">
      {isComplete ? '✓' : stepNumber}
    </div>
    <div className="step-label">{label}</div>
  </div>
));

StepIndicator.propTypes = {
  stepNumber: PropTypes.number.isRequired,
  label: PropTypes.string.isRequired,
  isActive: PropTypes.bool,
  isComplete: PropTypes.bool
};

/**
 * Controller Wizard Panel - Step-by-step controller configuration
 */
function ControllerWizardPanel() {
  const [currentStep, setCurrentStep] = useState(0);
  const [wizardData, setWizardData] = useState({
    sessionId: null,
    controllers: [],
    mapping: null,
    testResults: null
  });
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [completedSteps, setCompletedSteps] = useState(new Set());

  const sessionIdRef = useRef(null);

  // Generate session ID on mount
  useEffect(() => {
    sessionIdRef.current = `wizard_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    setWizardData(prev => ({ ...prev, sessionId: sessionIdRef.current }));
  }, []);

  // Step definitions
  const steps = useMemo(() => [
    { id: 'detect', label: 'Detect', description: 'Find connected controllers' },
    { id: 'map', label: 'Map', description: 'Configure button mappings' },
    { id: 'test', label: 'Test', description: 'Verify configuration' },
    { id: 'export', label: 'Export', description: 'Save configuration' }
  ], []);

  // WebSocket connection management
  useEffect(() => {
    const handleMessage = (data) => {
      switch (data.type) {
        case 'connected':
          setIsConnected(true);
          break;
        case 'disconnected':
          setIsConnected(false);
          break;
        case 'wizard_updated':
          setWizardData(prev => ({ ...prev, ...data.wizard }));
          break;
        case 'wizard_started':
          console.log('Wizard started:', data.data);
          break;
        case 'wizard_step_complete':
          setCompletedSteps(prev => new Set([...prev, data.data.step]));
          if (data.data.nextStep) {
            const nextIndex = steps.findIndex(s => s.id === data.data.nextStep);
            if (nextIndex !== -1) setCurrentStep(nextIndex);
          }
          break;
        case 'wizard_complete':
          setCompletedSteps(new Set(steps.map(s => s.id)));
          break;
      }
    };

    wsManager.addListener(handleMessage);
    wsManager.connect();

    return () => {
      wsManager.removeListener(handleMessage);
    };
  }, [steps]);

  /**
   * Handle next step progression
   */
  const handleNext = useCallback(async () => {
    if (currentStep >= steps.length - 1) return;

    setIsLoading(true);
    const currentStepId = steps[currentStep].id;

    try {
      // Send step update via WebSocket
      wsManager.send({
        type: 'step_update',
        data: {
          session_id: sessionIdRef.current,
          step: currentStepId,
          data: wizardData
        }
      });

      // Also send via REST API
      const response = await fetch('/api/controller_wizard/wizard/step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionIdRef.current,
          step: currentStepId,
          user_id: 'dad'
        })
      });

      if (response.ok) {
        setCompletedSteps(prev => new Set([...prev, currentStepId]));
        setCurrentStep(prev => prev + 1);
      }
    } catch (err) {
      console.error('Failed to progress wizard:', err);
    } finally {
      setIsLoading(false);
    }
  }, [currentStep, steps, wizardData]);

  /**
   * Handle back navigation
   */
  const handleBack = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep(prev => prev - 1);
    }
  }, [currentStep]);

  /**
   * Handle wizard completion
   */
  const handleFinish = useCallback(async () => {
    setIsLoading(true);
    try {
      wsManager.send({
        type: 'step_update',
        data: {
          session_id: sessionIdRef.current,
          step: 'export',
          data: { ...wizardData, complete: true }
        }
      });

      setCompletedSteps(new Set(steps.map(s => s.id)));
    } catch (err) {
      console.error('Failed to complete wizard:', err);
    } finally {
      setIsLoading(false);
    }
  }, [wizardData, steps]);

  /**
   * Render step content based on current step
   */
  const renderStepContent = useMemo(() => {
    const step = steps[currentStep];

    switch (step.id) {
      case 'detect':
        return (
          <div className="step-content detect-step">
            <div className="detection-status">
              <div className="spinner"></div>
              <h3>Detecting controllers...</h3>
              <p>Please ensure your controllers are connected</p>
            </div>
            {wizardData.controllers.length > 0 && (
              <div className="detected-controllers">
                <h4>Detected Controllers:</h4>
                <ul>
                  {wizardData.controllers.map((ctrl, idx) => (
                    <li key={idx} className="controller-item">
                      <span className="controller-icon">🎮</span>
                      {ctrl.name || `Controller ${idx + 1}`}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        );

      case 'map':
        return (
          <div className="step-content map-step">
            <h3>Button Mapping</h3>
            <p>Suggested mapping for your controller:</p>
            <div className="mapping-display">
              <div className="mapping-grid">
                <div className="mapping-item">
                  <span className="button-label">A Button</span>
                  <span className="button-mapping">→ Action 1</span>
                </div>
                <div className="mapping-item">
                  <span className="button-label">B Button</span>
                  <span className="button-mapping">→ Action 2</span>
                </div>
                <div className="mapping-item">
                  <span className="button-label">X Button</span>
                  <span className="button-mapping">→ Action 3</span>
                </div>
                <div className="mapping-item">
                  <span className="button-label">Y Button</span>
                  <span className="button-mapping">→ Action 4</span>
                </div>
              </div>
            </div>
          </div>
        );

      case 'test':
        return (
          <div className="step-content test-step">
            <h3>Testing Configuration</h3>
            <div className="test-status">
              <div className="test-indicator">
                <div className="pulse-ring"></div>
                <span>Testing buttons...</span>
              </div>
              <p>Press buttons on your controller to verify mapping</p>
            </div>
            {wizardData.testResults && (
              <div className="test-results">
                <div className="result-icon">✓</div>
                <p>All buttons responding correctly!</p>
              </div>
            )}
          </div>
        );

      case 'export':
        return (
          <div className="step-content export-step">
            <div className="success-message">
              <div className="success-icon">🎉</div>
              <h3>Configuration Complete!</h3>
              <p>Your controller has been successfully configured</p>
              <div className="config-summary">
                <div className="summary-item">
                  <span>Controller:</span>
                  <span>{wizardData.controllers[0]?.name || 'Controller 1'}</span>
                </div>
                <div className="summary-item">
                  <span>Profile:</span>
                  <span>Default</span>
                </div>
                <div className="summary-item">
                  <span>Status:</span>
                  <span className="status-ready">Ready to use</span>
                </div>
              </div>
            </div>
          </div>
        );

      default:
        return null;
    }
  }, [currentStep, steps, wizardData]);

  return (
    <PanelShell
      title="Controller Wizard - Guided Setup"
      subtitle="Step-by-step controller configuration"
      icon={<img src="/wiz-avatar.jpeg" alt="Wiz" className="avatar-img" />}
      headerActions={
        <div className="connection-status">
          <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
          <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
      }
    >
      <div className="controller-wizard-panel">
        {/* Progress Bar */}
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

        {/* Step Content */}
        <div className="wizard-body">
          {renderStepContent}
        </div>

        {/* Navigation Buttons */}
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
              disabled={isLoading}
            >
              {isLoading ? 'Processing...' : 'Next'}
            </button>
          ) : (
            <button
              className="wizard-btn btn-finish"
              onClick={handleFinish}
              disabled={isLoading}
            >
              {isLoading ? 'Saving...' : 'Finish'}
            </button>
          )}
        </div>
      </div>
    </PanelShell>
  );
}

ControllerWizardPanel.propTypes = {};

export default ControllerWizardPanel;