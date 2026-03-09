import React from 'react'
import { DiffPreview } from '../../_kit'

export default function ShaderPreviewModal({
  isOpen,
  shaderModal,
  shaderPreview,
  onCancel,
  onApply
}) {
  if (!isOpen) return null

  return (
    <div role="dialog" aria-modal="true" aria-label="Shader preview" className="shader-preview-overlay">
      <div className="shader-preview-card">
        <h3 className="shader-preview-title">Shader Configuration for {shaderModal.gameId}</h3>
        <div className="shader-preview-details">
          <div className="shader-detail-item">
            <span className="shader-detail-label">Shader:</span>
            <span className="shader-detail-value">{shaderModal.shaderName || 'n/a'}</span>
          </div>
          <div className="shader-detail-item">
            <span className="shader-detail-label">Emulator:</span>
            <span className="shader-detail-value">{shaderModal.emulator || 'n/a'}</span>
          </div>
          {shaderModal.diff && (
            <div className="shader-detail-item">
              <span className="shader-detail-label">Change:</span>
              <span className="shader-detail-value">{shaderModal.diff}</span>
            </div>
          )}
        </div>
        {shaderModal.error && (
          <div style={{ color: '#ff6b6b', marginBottom: 8 }}>Error: {shaderModal.error}</div>
        )}
        <div style={{ marginTop: 6 }}>
          <DiffPreview
            oldText={shaderPreview?.oldText || JSON.stringify(shaderModal.oldConfig || { shader: 'none' }, null, 2)}
            newText={shaderPreview?.newText || JSON.stringify(shaderModal.newConfig || {}, null, 2)}
          />
        </div>
        <div className="shader-preview-actions">
          <button
            onClick={onCancel}
            disabled={shaderModal.applying}
            className="shader-btn shader-btn-cancel"
          >
            Cancel
          </button>
          <button onClick={onApply} disabled={shaderModal.applying} className="shader-btn shader-btn-apply">
            {shaderModal.applying ? 'Applying…' : 'Apply Shader'}
          </button>
        </div>
      </div>
    </div>
  )
}