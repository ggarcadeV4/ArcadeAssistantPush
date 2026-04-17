/**
 * CabinetControlStatus.jsx
 *
 * One coherent "cabinet control truth" surface for Controller Chuck.
 * Pulls the unified payload from /api/local/controller/status and
 * presents five plain-language sections:
 *   1. Connected Board   (live canonical hardware)
 *   2. Saved Cabinet Mapping (controls.json)
 *   3. Runtime Endpoints (Windows/HID children)
 *   4. Downstream Sync   (cascade/baseline)
 *   5. Warnings & Drift  (reconciliation diffs)
 *
 * The backend already does the truth reconciliation; this component is
 * intentionally just rendering — no logic that competes with chuck/ai.
 */

import React, { useCallback, useEffect, useState } from 'react';
import './cabinet-control-status.css';

const STATUS_ENDPOINT = '/api/local/controller/status';

function formatVidPid(vid, pid) {
  if (!vid || !pid) return null;
  return `${vid}:${pid}`;
}

function buildBoardLabel(entry) {
  if (!entry?.name) return null;
  const ids = formatVidPid(entry.vid, entry.pid);
  return ids ? `${entry.name} (${ids})` : entry.name;
}

export default function CabinetControlStatus({ headers, refreshKey = 0 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [savingOverride, setSavingOverride] = useState(false);

  const handleOverride = async (e) => {
    const newName = e.target.value;
    if (!newName) return;

    setSavingOverride(true);
    setError(null);

    try {
      // Construct a partial payload that the backend wizard router will merge and atomically save
      const res = await fetch('/api/local/wizard/save', {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          controls: {
            // Pass existing saved mappings if available, or empty objects to satisfy the schema
            ...data?.saved_mapping?.full_payload,
            board: {
              ...data?.connected_board,
              name: newName,
              detected: false // Flag as manual override
            },
            mappings: data?.saved_mapping?.mappings || {}
          },
          generate_mame_config: false // Don't trigger heavy cascade just for a name change
        })
      });

      if (!res.ok) throw new Error('Failed to save hardware override');

      // Refresh the status component to pull the new truth from the backend
      await refresh();
    } catch (err) {
      setError(err?.message || 'Override failed.');
    } finally {
      setSavingOverride(false);
    }
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(STATUS_ENDPOINT, { headers });
      if (!res.ok) {
        throw new Error(`Status load failed (${res.status})`);
      }
      const payload = await res.json();
      setData(payload);
    } catch (err) {
      setError(err?.message || 'Could not load cabinet control status.');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { refresh(); }, [refresh, refreshKey]);

  if (loading && !data) {
    return (
      <section className="cabinet-status" aria-label="Cabinet control status">
        <header className="cabinet-status__header">
          <h2>Cabinet Control Status</h2>
        </header>
        <p className="cabinet-status__placeholder">Reading the cabinet…</p>
      </section>
    );
  }

  if (error && !data) {
    return (
      <section className="cabinet-status" aria-label="Cabinet control status">
        <header className="cabinet-status__header">
          <h2>Cabinet Control Status</h2>
          <button type="button" className="cabinet-status__refresh" onClick={refresh}>
            Retry
          </button>
        </header>
        <p className="cabinet-status__error">{error}</p>
      </section>
    );
  }

  const connected = data?.connected_board || {};
  const saved = data?.saved_mapping || {};
  const runtime = data?.runtime || {};
  const cascade = data?.cascade || {};
  const warnings = Array.isArray(data?.warnings) ? data.warnings : [];

  // Wave 1 #11: keep the friendly board name as the main truth. The raw
  // VID/PID (and any spoofed-XInput USB descriptor) become subordinate
  // detail lines so a promoted Pacto board never looks like an Xbox.
  const connectedName = connected.name || 'No live encoder board';
  const connectedVidPid = formatVidPid(connected.vid, connected.pid);
  const usbDescriptor = connected.usb_descriptor || null;
  const detectionFailure = connected.detection_failure || null;
  const savedLabel = buildBoardLabel(saved) || (saved.name || 'No saved mapping');

  return (
    <section className="cabinet-status" aria-label="Cabinet control status">
      <header className="cabinet-status__header">
        <div>
          <h2>Cabinet Control Status</h2>
          <p>One coherent view of what Chuck believes your cabinet currently is.</p>
        </div>
        <button
          type="button"
          className="cabinet-status__refresh"
          onClick={refresh}
          disabled={loading}
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </header>

      <div className="cabinet-status__grid">
        <article className={`cabinet-status__card cabinet-status__card--${connected.status || 'unknown'}`}>
          <span className="cabinet-status__label">Connected Board</span>
          <strong className="cabinet-status__value">{connectedName}</strong>
          {/* Hardware Override Dropdown */}
          <div className="cabinet-status__override" style={{ marginTop: '0.5rem', marginBottom: '0.5rem' }}>
            <select
              onChange={handleOverride}
              disabled={savingOverride || loading}
              value=""
              style={{ padding: '4px', borderRadius: '4px', width: '100%' }}
              aria-label="Override Hardware Profile"
            >
              <option value="" disabled>Force Profile Override...</option>
              <option value="Arcade Panel (Pacto)">Arcade Panel (Pacto)</option>
              <option value="Xbox 360 Controller">Xbox 360 Controller</option>
              <option value="8BitDo Pad">8BitDo Pad</option>
              <option value="Generic XInput Pad">Generic XInput Pad</option>
            </select>
            {savingOverride && <span style={{ fontSize: '0.8rem', color: '#666' }}> Saving override...</span>}
          </div>
          <p className="cabinet-status__detail">{connected.summary}</p>
          {connectedVidPid && !usbDescriptor && (
            <span className="cabinet-status__source">VID/PID: {connectedVidPid}</span>
          )}
          {usbDescriptor && (
            <span
              className="cabinet-status__source"
              title={usbDescriptor.explanation || ''}
            >
              USB descriptor: {usbDescriptor.vid_pid}
              {usbDescriptor.label ? ` (${usbDescriptor.label})` : ''}
            </span>
          )}
          {connected.source && (
            <span className="cabinet-status__source">Source: {connected.source}</span>
          )}
          {detectionFailure?.code && (
            <span className="cabinet-status__source">
              Failure: {detectionFailure.code}
            </span>
          )}
        </article>

        <article className={`cabinet-status__card cabinet-status__card--${saved.status || 'unknown'}`}>
          <span className="cabinet-status__label">Saved Cabinet Mapping</span>
          <strong className="cabinet-status__value">{savedLabel}</strong>
          <p className="cabinet-status__detail">{saved.summary}</p>
          {saved.last_modified && (
            <span className="cabinet-status__source">Saved: {saved.last_modified}</span>
          )}
          {saved.file_path && (
            <span className="cabinet-status__source">File: {saved.file_path}</span>
          )}
        </article>

        <article className="cabinet-status__card cabinet-status__card--runtime">
          <span className="cabinet-status__label">Runtime Endpoints</span>
          <strong className="cabinet-status__value">
            {runtime.endpoints?.length
              ? `${runtime.endpoints.length} child endpoint(s) visible`
              : 'No child controllers visible'}
          </strong>
          <p className="cabinet-status__detail">{runtime.explanation}</p>
          {!!runtime.endpoints?.length && (
            <ul className="cabinet-status__list">
              {runtime.endpoints.slice(0, 4).map((ep, idx) => {
                const ids = formatVidPid(ep.vid, ep.pid);
                return (
                  <li key={`${ep.vid || 'na'}-${ep.pid || 'na'}-${idx}`}>
                    {ep.name}{ids ? ` — ${ids}` : ''}
                  </li>
                );
              })}
            </ul>
          )}
        </article>

        <article className={`cabinet-status__card cabinet-status__card--${cascade.status || 'unknown'}`}>
          <span className="cabinet-status__label">Downstream Sync</span>
          <strong className="cabinet-status__value">
            {cascade.status ? `Cascade ${cascade.status}` : 'Cascade status unknown'}
          </strong>
          <p className="cabinet-status__detail">{cascade.summary}</p>
          {cascade.led?.status && (
            <span className="cabinet-status__source">
              LED baseline: {cascade.led.status}
              {cascade.led.last_synced ? ` • synced ${cascade.led.last_synced}` : ''}
            </span>
          )}
          {cascade.updated_at && (
            <span className="cabinet-status__source">Baseline: {cascade.updated_at}</span>
          )}
        </article>
      </div>

      <div className="cabinet-status__warnings">
        <h3>Warnings &amp; Drift</h3>
        {warnings.length ? (
          <ul>
            {warnings.map((w, idx) => (
              <li
                key={`${w.code || 'warn'}-${idx}`}
                className={`cabinet-status__warning cabinet-status__warning--${w.severity || 'info'}`}
              >
                <strong>{w.title}</strong>
                <span>{w.detail}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="cabinet-status__healthy">No drift detected. Chuck is happy.</p>
        )}
      </div>
    </section>
  );
}
