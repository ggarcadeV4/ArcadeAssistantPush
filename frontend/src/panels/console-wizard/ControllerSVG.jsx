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
      up: { cx: 24, cy: 38, w: 6.5, h: 9, shape: 'rect' },
      down: { cx: 24, cy: 51, w: 6.5, h: 9, shape: 'rect' },
      left: { cx: 17, cy: 44.5, w: 9, h: 6.5, shape: 'rect' },
      right: { cx: 31, cy: 44.5, w: 9, h: 6.5, shape: 'rect' },
      a: { x: 77, y: 53, r: 4.5, shape: 'circle' },
      b: { x: 84, y: 45.5, r: 4.5, shape: 'circle' },
      x: { x: 70, y: 45.5, r: 4.5, shape: 'circle' },
      y: { x: 77, y: 38, r: 4.5, shape: 'circle' },
      l: { cx: 24, cy: 19, w: 17, h: 7, shape: 'rect' },
      r: { cx: 76, cy: 19, w: 17, h: 7, shape: 'rect' },
      zl: { cx: 24, cy: 13, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 76, cy: 13, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 44, cy: 45, w: 5.5, h: 4, shape: 'rect' },
      start: { cx: 56, cy: 45, w: 5.5, h: 4, shape: 'rect' },
      home: { x: 50, y: 36, r: 2.8, shape: 'circle' },
      l3: { x: 35, y: 64, r: 6.5, shape: 'circle' },
      r3: { x: 62, y: 64, r: 6.5, shape: 'circle' },
    },
  },
  '8bitdo_sn30': {
    image: '/assets/controllers/8bitdo_sn30.png',
    label: '8BitDo SN30 Pro',
    hotspots: {
      up: { cx: 25, cy: 40, w: 6.5, h: 8.5, shape: 'rect' },
      down: { cx: 25, cy: 55, w: 6.5, h: 8.5, shape: 'rect' },
      left: { cx: 18, cy: 47.5, w: 9, h: 6.5, shape: 'rect' },
      right: { cx: 32, cy: 47.5, w: 9, h: 6.5, shape: 'rect' },
      a: { x: 78, y: 54, r: 4.5, shape: 'circle' },
      b: { x: 85, y: 47, r: 4.5, shape: 'circle' },
      x: { x: 71, y: 47, r: 4.5, shape: 'circle' },
      y: { x: 78, y: 40, r: 4.5, shape: 'circle' },
      l: { cx: 22, cy: 18, w: 18, h: 7, shape: 'rect' },
      r: { cx: 78, cy: 18, w: 18, h: 7, shape: 'rect' },
      zl: { cx: 22, cy: 12, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 78, cy: 12, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 43, cy: 47, w: 6, h: 4.2, shape: 'rect' },
      start: { cx: 57, cy: 47, w: 6, h: 4.2, shape: 'rect' },
      home: { x: 50, y: 56, r: 2.8, shape: 'circle' },
      l3: { x: 35, y: 68, r: 5.5, shape: 'circle' },
      r3: { x: 65, y: 68, r: 5.5, shape: 'circle' },
    },
  },
  xbox_360: {
    image: '/assets/controllers/xbox_360.png',
    label: 'Xbox 360',
    hotspots: {
      up: { cx: 35, cy: 55, w: 6.5, h: 8, shape: 'rect' },
      down: { cx: 35, cy: 68, w: 6.5, h: 8, shape: 'rect' },
      left: { cx: 27.5, cy: 61.5, w: 9, h: 6.2, shape: 'rect' },
      right: { cx: 42.5, cy: 61.5, w: 9, h: 6.2, shape: 'rect' },
      a: { x: 76, y: 54, r: 4.5, shape: 'circle' },
      b: { x: 83, y: 47, r: 4.5, shape: 'circle' },
      x: { x: 69, y: 47, r: 4.5, shape: 'circle' },
      y: { x: 76, y: 40, r: 4.5, shape: 'circle' },
      l: { cx: 23, cy: 19, w: 18, h: 8, shape: 'rect' },
      r: { cx: 77, cy: 19, w: 18, h: 8, shape: 'rect' },
      zl: { cx: 23, cy: 12, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 77, cy: 12, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 42.5, cy: 42, w: 6.5, h: 4.2, shape: 'rect' },
      start: { cx: 57.5, cy: 42, w: 6.5, h: 4.2, shape: 'rect' },
      home: { x: 50, y: 33, r: 3.6, shape: 'circle' },
      l3: { x: 22, y: 43, r: 6.8, shape: 'circle' },
      r3: { x: 60, y: 64, r: 6.8, shape: 'circle' },
    },
  },
  ps4_dualshock: {
    image: '/assets/controllers/ps4_dualshock.png',
    label: 'PS4 DualShock 4',
    hotspots: {
      up: { cx: 23, cy: 40, w: 6.5, h: 8.5, shape: 'rect' },
      down: { cx: 23, cy: 55, w: 6.5, h: 8.5, shape: 'rect' },
      left: { cx: 15.5, cy: 47.5, w: 9, h: 6.5, shape: 'rect' },
      right: { cx: 30.5, cy: 47.5, w: 9, h: 6.5, shape: 'rect' },
      a: { x: 81, y: 55, r: 4.5, shape: 'circle' },
      b: { x: 88, y: 47.5, r: 4.5, shape: 'circle' },
      x: { x: 74, y: 47.5, r: 4.5, shape: 'circle' },
      y: { x: 81, y: 40, r: 4.5, shape: 'circle' },
      l: { cx: 20, cy: 19, w: 18, h: 7, shape: 'rect' },
      r: { cx: 80, cy: 19, w: 18, h: 7, shape: 'rect' },
      zl: { cx: 20, cy: 13, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 80, cy: 13, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 39.5, cy: 37, w: 6, h: 4.2, shape: 'rect' },
      start: { cx: 60.5, cy: 37, w: 6, h: 4.2, shape: 'rect' },
      home: { x: 50, y: 48, r: 3, shape: 'circle' },
      l3: { x: 36, y: 65, r: 6, shape: 'circle' },
      r3: { x: 64, y: 65, r: 6, shape: 'circle' },
    },
  },
  switch_pro: {
    image: '/assets/controllers/switch_pro.png',
    label: 'Nintendo Switch Pro',
    hotspots: {
      up: { cx: 34, cy: 58, w: 6.5, h: 8, shape: 'rect' },
      down: { cx: 34, cy: 71, w: 6.5, h: 8, shape: 'rect' },
      left: { cx: 26.5, cy: 64.5, w: 9, h: 6.2, shape: 'rect' },
      right: { cx: 41.5, cy: 64.5, w: 9, h: 6.2, shape: 'rect' },
      a: { x: 79, y: 50, r: 4.5, shape: 'circle' },
      b: { x: 72, y: 57, r: 4.5, shape: 'circle' },
      x: { x: 72, y: 43, r: 4.5, shape: 'circle' },
      y: { x: 65, y: 50, r: 4.5, shape: 'circle' },
      l: { cx: 20, cy: 19, w: 18, h: 8, shape: 'rect' },
      r: { cx: 80, cy: 19, w: 18, h: 8, shape: 'rect' },
      zl: { cx: 20, cy: 12, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 80, cy: 12, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 37, cy: 38, w: 5.5, h: 4, shape: 'rect' },
      start: { cx: 58, cy: 38, w: 5.5, h: 4, shape: 'rect' },
      home: { x: 55, y: 46.5, r: 2.8, shape: 'circle' },
      l3: { x: 21, y: 42, r: 6.8, shape: 'circle' },
      r3: { x: 57, y: 65, r: 6.8, shape: 'circle' },
    },
  },
  '8bitdo_ultimate': {
    image: '/assets/controllers/8bitdo_ultimate.png',
    label: '8BitDo Ultimate',
    hotspots: {
      up: { cx: 34, cy: 55, w: 6.5, h: 8, shape: 'rect' },
      down: { cx: 34, cy: 68, w: 6.5, h: 8, shape: 'rect' },
      left: { cx: 27, cy: 61.5, w: 9, h: 6.2, shape: 'rect' },
      right: { cx: 41, cy: 61.5, w: 9, h: 6.2, shape: 'rect' },
      a: { x: 77, y: 54, r: 4.5, shape: 'circle' },
      b: { x: 84, y: 47, r: 4.5, shape: 'circle' },
      x: { x: 70, y: 47, r: 4.5, shape: 'circle' },
      y: { x: 77, y: 40, r: 4.5, shape: 'circle' },
      l: { cx: 23, cy: 19, w: 17, h: 7, shape: 'rect' },
      r: { cx: 77, cy: 19, w: 17, h: 7, shape: 'rect' },
      zl: { cx: 23, cy: 13, w: 14, h: 5.5, shape: 'rect' },
      zr: { cx: 77, cy: 13, w: 14, h: 5.5, shape: 'rect' },
      select: { cx: 43, cy: 42, w: 5.5, h: 4, shape: 'rect' },
      start: { cx: 57, cy: 42, w: 5.5, h: 4, shape: 'rect' },
      home: { x: 50, y: 33, r: 3, shape: 'circle' },
      l3: { x: 22, y: 42, r: 6.5, shape: 'circle' },
      r3: { x: 61, y: 64, r: 6.5, shape: 'circle' },
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
