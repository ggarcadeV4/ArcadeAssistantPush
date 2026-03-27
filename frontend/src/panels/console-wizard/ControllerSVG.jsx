/**
 * ControllerSVG.jsx
 *
 * Hybrid PNG + hotspot overlay "digital twin" of a gamepad controller.
 *
 * Each controller profile has:
 *  - A controller PNG background image (in /assets/controllers/)
 *  - Transparent hotspot overlays positioned over each button
 *
 * Props:
 *  - activeButton {string|null} key of the control being prompted
 *  - confirmedButton {string|null} key that was just captured
 *  - pressedButtons {Set<string>} buttons currently physically pressed
 *  - mappedButtons {Set<string>} controls successfully mapped
 *  - profileId {string} e.g. '8bitdo_pro_2', 'xbox_360', 'ps4_dualshock', 'switch_pro'
 */
import React, { memo, useEffect, useMemo, useRef, useState } from 'react';

const BUTTON_LABELS = {
  up: 'D-Pad Up',
  down: 'D-Pad Down',
  left: 'D-Pad Left',
  right: 'D-Pad Right',
  a: 'A',
  b: 'B',
  x: 'X',
  y: 'Y',
  l: 'L1',
  r: 'R1',
  zl: 'L2',
  zr: 'R2',
  select: 'Select',
  start: 'Start',
  l3: 'L3',
  r3: 'R3',
  home: 'Home',
};

const FALLBACK_ROWS = [
  ['up', 'down', 'left', 'right'],
  ['x', 'y', 'a', 'b'],
  ['l', 'r', 'zl', 'zr'],
  ['select', 'start', 'l3', 'r3'],
];

/*
 * Percentage-based coordinates relative to the rendered image.
 * Rectangles use center-point coordinates to keep calibration consistent with circles.
 */
const PROFILES = {
  '8bitdo_pro_2': {
    image: '/assets/controllers/8bitdo_pro_2.png',
    label: '8BitDo Pro 2',
    hotspots: {
      up: { cx: 20, cy: 29.5, w: 6.5, h: 9, shape: 'rect' },
      down: { cx: 20, cy: 42.5, w: 6.5, h: 9, shape: 'rect' },
      left: { cx: 13, cy: 36, w: 9, h: 6.5, shape: 'rect' },
      right: { cx: 27, cy: 36, w: 9, h: 6.5, shape: 'rect' },
      a: { x: 77, y: 45.5, r: 4.2, shape: 'circle' },
      b: { x: 84.2, y: 38, r: 4.2, shape: 'circle' },
      x: { x: 69.8, y: 38, r: 4.2, shape: 'circle' },
      y: { x: 77, y: 30.5, r: 4.2, shape: 'circle' },
      l: { cx: 22, cy: 10.5, w: 17, h: 7, shape: 'rect' },
      r: { cx: 78, cy: 10.5, w: 17, h: 7, shape: 'rect' },
      zl: { cx: 22, cy: 4.5, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 78, cy: 4.5, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 44, cy: 37.5, w: 5.5, h: 4, shape: 'rect' },
      start: { cx: 56, cy: 37.5, w: 5.5, h: 4, shape: 'rect' },
      home: { x: 50, y: 27.5, r: 2.8, shape: 'circle' },
      l3: { x: 33.5, y: 57.5, r: 6.2, shape: 'circle' },
      r3: { x: 60.5, y: 57.5, r: 6.2, shape: 'circle' },
    },
  },
  '8bitdo_sn30': {
    image: '/assets/controllers/8bitdo_sn30.png',
    label: '8BitDo SN30 Pro',
    hotspots: {
      up: { cx: 23.5, cy: 31, w: 6.5, h: 8.5, shape: 'rect' },
      down: { cx: 23.5, cy: 47.5, w: 6.5, h: 8.5, shape: 'rect' },
      left: { cx: 16, cy: 39.5, w: 9, h: 6.5, shape: 'rect' },
      right: { cx: 31, cy: 39.5, w: 9, h: 6.5, shape: 'rect' },
      a: { x: 78.5, y: 46, r: 4.2, shape: 'circle' },
      b: { x: 85.5, y: 38.5, r: 4.2, shape: 'circle' },
      x: { x: 71.5, y: 38.5, r: 4.2, shape: 'circle' },
      y: { x: 78.5, y: 31, r: 4.2, shape: 'circle' },
      l: { cx: 22, cy: 9.5, w: 18, h: 7, shape: 'rect' },
      r: { cx: 78, cy: 9.5, w: 18, h: 7, shape: 'rect' },
      zl: { cx: 22, cy: 4, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 78, cy: 4, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 43.2, cy: 39, w: 6, h: 4.2, shape: 'rect' },
      start: { cx: 56.8, cy: 39, w: 6, h: 4.2, shape: 'rect' },
      home: { x: 50, y: 48.5, r: 2.8, shape: 'circle' },
      l3: { x: 34.5, y: 60.5, r: 5.2, shape: 'circle' },
      r3: { x: 65.5, y: 60.5, r: 5.2, shape: 'circle' },
    },
  },
  xbox_360: {
    image: '/assets/controllers/xbox_360.png',
    label: 'Xbox 360',
    hotspots: {
      up: { cx: 34.5, cy: 48.5, w: 6.5, h: 8, shape: 'rect' },
      down: { cx: 34.5, cy: 61.5, w: 6.5, h: 8, shape: 'rect' },
      left: { cx: 27, cy: 55, w: 9, h: 6.2, shape: 'rect' },
      right: { cx: 42, cy: 55, w: 9, h: 6.2, shape: 'rect' },
      a: { x: 76.5, y: 47.5, r: 4.2, shape: 'circle' },
      b: { x: 83.5, y: 40, r: 4.2, shape: 'circle' },
      x: { x: 69.5, y: 40, r: 4.2, shape: 'circle' },
      y: { x: 76.5, y: 32.5, r: 4.2, shape: 'circle' },
      l: { cx: 22, cy: 10, w: 18, h: 8, shape: 'rect' },
      r: { cx: 78, cy: 10, w: 18, h: 8, shape: 'rect' },
      zl: { cx: 22, cy: 4, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 78, cy: 4, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 42.5, cy: 35, w: 6.5, h: 4.2, shape: 'rect' },
      start: { cx: 57.5, cy: 35, w: 6.5, h: 4.2, shape: 'rect' },
      home: { x: 50, y: 26, r: 3.4, shape: 'circle' },
      l3: { x: 19, y: 36, r: 6.4, shape: 'circle' },
      r3: { x: 59, y: 57, r: 6.4, shape: 'circle' },
    },
  },
  ps4_dualshock: {
    image: '/assets/controllers/ps4_dualshock.png',
    label: 'PS4 DualShock 4',
    hotspots: {
      up: { cx: 21.5, cy: 31, w: 6.5, h: 8.5, shape: 'rect' },
      down: { cx: 21.5, cy: 47.5, w: 6.5, h: 8.5, shape: 'rect' },
      left: { cx: 14, cy: 39.5, w: 9, h: 6.5, shape: 'rect' },
      right: { cx: 29, cy: 39.5, w: 9, h: 6.5, shape: 'rect' },
      a: { x: 81.5, y: 47.8, r: 4.2, shape: 'circle' },
      b: { x: 88.5, y: 40.2, r: 4.2, shape: 'circle' },
      x: { x: 74.5, y: 40.2, r: 4.2, shape: 'circle' },
      y: { x: 81.5, y: 32.5, r: 4.2, shape: 'circle' },
      l: { cx: 19, cy: 10.5, w: 18, h: 7, shape: 'rect' },
      r: { cx: 81, cy: 10.5, w: 18, h: 7, shape: 'rect' },
      zl: { cx: 19, cy: 4.5, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 81, cy: 4.5, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 39.5, cy: 29, w: 6, h: 4.2, shape: 'rect' },
      start: { cx: 60.5, cy: 29, w: 6, h: 4.2, shape: 'rect' },
      home: { x: 50, y: 41, r: 2.8, shape: 'circle' },
      l3: { x: 36, y: 58, r: 5.8, shape: 'circle' },
      r3: { x: 64, y: 58, r: 5.8, shape: 'circle' },
    },
  },
  switch_pro: {
    image: '/assets/controllers/switch_pro.png',
    label: 'Nintendo Switch Pro',
    hotspots: {
      up: { cx: 33.5, cy: 51.5, w: 6.5, h: 8, shape: 'rect' },
      down: { cx: 33.5, cy: 64.5, w: 6.5, h: 8, shape: 'rect' },
      left: { cx: 26, cy: 58, w: 9, h: 6.2, shape: 'rect' },
      right: { cx: 41, cy: 58, w: 9, h: 6.2, shape: 'rect' },
      a: { x: 79.5, y: 43, r: 4.2, shape: 'circle' },
      b: { x: 72.2, y: 50.3, r: 4.2, shape: 'circle' },
      x: { x: 72.2, y: 35.7, r: 4.2, shape: 'circle' },
      y: { x: 65, y: 43, r: 4.2, shape: 'circle' },
      l: { cx: 19, cy: 10, w: 18, h: 8, shape: 'rect' },
      r: { cx: 81, cy: 10, w: 18, h: 8, shape: 'rect' },
      zl: { cx: 19, cy: 4, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 81, cy: 4, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 36, cy: 31, w: 5.5, h: 4, shape: 'rect' },
      start: { cx: 58, cy: 31, w: 5.5, h: 4, shape: 'rect' },
      home: { x: 55.2, y: 39.5, r: 2.8, shape: 'circle' },
      l3: { x: 20, y: 35, r: 6.4, shape: 'circle' },
      r3: { x: 57, y: 58, r: 6.4, shape: 'circle' },
    },
  },
};

const DEFAULT_PROFILE = '8bitdo_pro_2';

function buildHotspotClasses(key, activeButton, confirmedButton, pressedButtons, mappedButtons) {
  const classes = ['gp-controller__hotspot'];

  if (mappedButtons?.has(key)) classes.push('gp-controller__hotspot--mapped');
  if (pressedButtons?.has(key)) classes.push('gp-controller__hotspot--pressed');
  if (key === activeButton) classes.push('gp-controller__hotspot--active');
  if (key === confirmedButton) classes.push('gp-controller__hotspot--confirmed');

  return classes.join(' ');
}

function renderFallbackRows(activeButton, confirmedButton, pressedButtons, mappedButtons) {
  return (
    <div className="gp-controller-fallback">
      <div className="gp-controller-fallback__warning">
        Controller art unavailable. Using text-only mapping view for this profile.
      </div>
      {FALLBACK_ROWS.map((row, idx) => (
        <div key={`fallback-row-${idx}`} className="gp-controller-fallback__row">
          {row.map((key) => (
            <div
              key={key}
              className={buildHotspotClasses(key, activeButton, confirmedButton, pressedButtons, mappedButtons)}
            >
              <span className="gp-controller-fallback__label">{BUTTON_LABELS[key] ?? key.toUpperCase()}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function ControllerSVG({ activeButton, confirmedButton, pressedButtons, mappedButtons, profileId }) {
  const warnedImagesRef = useRef(new Set());
  const profileKey = profileId && PROFILES[profileId] ? profileId : DEFAULT_PROFILE;
  const profile = PROFILES[profileKey];
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [profileKey]);

  const hotspotEntries = useMemo(() => Object.entries(profile.hotspots), [profile]);

  const handleImageError = () => {
    setImageFailed(true);
    if (!warnedImagesRef.current.has(profile.image)) {
      warnedImagesRef.current.add(profile.image);
      console.warn(`[Wiz] Controller image missing for profile '${profileKey}': ${profile.image}`);
    }
  };

  return (
    <div className="gp-controller">
      {imageFailed ? (
        renderFallbackRows(activeButton, confirmedButton, pressedButtons, mappedButtons)
      ) : (
        <>
          <img
            src={profile.image}
            alt={profile.label}
            draggable={false}
            className="gp-controller__image"
            onError={handleImageError}
          />

          {hotspotEntries.map(([key, spot]) => {
            const commonStyle = {
              zIndex: 2,
              pointerEvents: 'none',
            };

            if (spot.shape === 'circle') {
              return (
                <div
                  key={key}
                  title={BUTTON_LABELS[key] ?? key.toUpperCase()}
                  className={buildHotspotClasses(key, activeButton, confirmedButton, pressedButtons, mappedButtons)}
                  style={{
                    ...commonStyle,
                    left: `${spot.x - spot.r}%`,
                    top: `${spot.y - spot.r}%`,
                    width: `${spot.r * 2}%`,
                    height: `${spot.r * 2}%`,
                    borderRadius: '999px',
                  }}
                />
              );
            }

            return (
              <div
                key={key}
                title={BUTTON_LABELS[key] ?? key.toUpperCase()}
                className={buildHotspotClasses(key, activeButton, confirmedButton, pressedButtons, mappedButtons)}
                style={{
                  ...commonStyle,
                  left: `${spot.cx - (spot.w / 2)}%`,
                  top: `${spot.cy - (spot.h / 2)}%`,
                  width: `${spot.w}%`,
                  height: `${spot.h}%`,
                  borderRadius: spot.h <= 5 ? '999px' : '6px',
                }}
              />
            );
          })}
        </>
      )}

      <div className="gp-controller__badge">{profile.label}</div>
    </div>
  );
}

export default memo(ControllerSVG);
