/**
 * ControllerSVG.jsx
 *
 * Hybrid PNG + SVG Overlay "digital twin" of a gamepad controller.
 *
 * Each controller profile has:
 *  - A realistic PNG background image (in /assets/controllers/)
 *  - Transparent SVG hotspot overlays positioned over each button
 *
 * Props:
 *  - activeButton {string|null} — key of the control being prompted (pulsing amber)
 *  - pressedButtons {Set<string>} — buttons currently physically pressed (cyan glow)
 *  - mappedButtons {Set<string>} — controls successfully mapped (green)
 *  - profileId {string} — e.g. '8bitdo_pro_2', 'xbox_360', 'ps4_dualshock', 'switch_pro'
 */
import React, { memo } from 'react';

const AMBER = '#f59e0b';
const CYAN  = '#38bdf8';
const GREEN = '#22c55e';

/* ── Per-profile PNG + hotspot coordinate maps ─────────────────────────
   Coordinates are percentage-based (0-100) relative to the image.
   Each hotspot: { x, y, w, h, shape } where shape is 'circle' or 'rect'
   For circles: x,y = center %, r = radius %
   For rects: x,y = top-left %, w,h = size %
──────────────────────────────────────────────────────────────────────── */

const PROFILES = {
  '8bitdo_pro_2': {
    image: '/assets/controllers/8bitdo_pro_2.png',
    label: '8BitDo Pro 2',
    hotspots: {
      // D-Pad
      up:    { x: 24, y: 32, w: 7, h: 10, shape: 'rect' },
      down:  { x: 24, y: 52, w: 7, h: 10, shape: 'rect' },
      left:  { x: 15, y: 42, w: 10, h: 7, shape: 'rect' },
      right: { x: 30, y: 42, w: 10, h: 7, shape: 'rect' },
      // Face buttons
      a: { x: 76, y: 48, r: 4.5, shape: 'circle' },
      b: { x: 83, y: 40, r: 4.5, shape: 'circle' },
      x: { x: 69, y: 40, r: 4.5, shape: 'circle' },
      y: { x: 76, y: 32, r: 4.5, shape: 'circle' },
      // Shoulders
      l:  { x: 14, y: 8, w: 16, h: 8, shape: 'rect' },
      r:  { x: 70, y: 8, w: 16, h: 8, shape: 'rect' },
      zl: { x: 16, y: 0, w: 12, h: 7, shape: 'rect' },
      zr: { x: 72, y: 0, w: 12, h: 7, shape: 'rect' },
      // Meta
      select: { x: 40, y: 34, w: 7, h: 5, shape: 'rect' },
      start:  { x: 53, y: 34, w: 7, h: 5, shape: 'rect' },
      home:   { x: 48, y: 44, r: 3, shape: 'circle' },
      // Sticks
      l3: { x: 35, y: 58, r: 6, shape: 'circle' },
      r3: { x: 65, y: 58, r: 6, shape: 'circle' },
    },
  },

  '8bitdo_sn30': {
    image: '/assets/controllers/8bitdo_sn30.png',
    label: '8BitDo SN30 Pro',
    hotspots: {
      up:    { x: 22, y: 30, w: 7, h: 10, shape: 'rect' },
      down:  { x: 22, y: 50, w: 7, h: 10, shape: 'rect' },
      left:  { x: 13, y: 40, w: 10, h: 7, shape: 'rect' },
      right: { x: 28, y: 40, w: 10, h: 7, shape: 'rect' },
      a: { x: 78, y: 47, r: 4.5, shape: 'circle' },
      b: { x: 85, y: 39, r: 4.5, shape: 'circle' },
      x: { x: 71, y: 39, r: 4.5, shape: 'circle' },
      y: { x: 78, y: 31, r: 4.5, shape: 'circle' },
      l:  { x: 12, y: 8, w: 18, h: 8, shape: 'rect' },
      r:  { x: 70, y: 8, w: 18, h: 8, shape: 'rect' },
      zl: { x: 14, y: 0, w: 14, h: 7, shape: 'rect' },
      zr: { x: 72, y: 0, w: 14, h: 7, shape: 'rect' },
      select: { x: 39, y: 38, w: 7, h: 5, shape: 'rect' },
      start:  { x: 54, y: 38, w: 7, h: 5, shape: 'rect' },
      home:   { x: 50, y: 48, r: 3, shape: 'circle' },
      l3: { x: 34, y: 60, r: 5.5, shape: 'circle' },
      r3: { x: 66, y: 60, r: 5.5, shape: 'circle' },
    },
  },

  xbox_360: {
    image: '/assets/controllers/xbox_360.png',
    label: 'Xbox 360',
    hotspots: {
      up:    { x: 20, y: 42, w: 7, h: 10, shape: 'rect' },
      down:  { x: 20, y: 62, w: 7, h: 10, shape: 'rect' },
      left:  { x: 11, y: 52, w: 10, h: 7, shape: 'rect' },
      right: { x: 26, y: 52, w: 10, h: 7, shape: 'rect' },
      a: { x: 76, y: 48, r: 4.5, shape: 'circle' },
      b: { x: 83, y: 40, r: 4.5, shape: 'circle' },
      x: { x: 69, y: 40, r: 4.5, shape: 'circle' },
      y: { x: 76, y: 32, r: 4.5, shape: 'circle' },
      l:  { x: 12, y: 6, w: 18, h: 9, shape: 'rect' },
      r:  { x: 70, y: 6, w: 18, h: 9, shape: 'rect' },
      zl: { x: 14, y: 0, w: 14, h: 6, shape: 'rect' },
      zr: { x: 72, y: 0, w: 14, h: 6, shape: 'rect' },
      select: { x: 38, y: 34, w: 8, h: 5, shape: 'rect' },
      start:  { x: 54, y: 34, w: 8, h: 5, shape: 'rect' },
      home:   { x: 50, y: 24, r: 4, shape: 'circle' },
      l3: { x: 30, y: 32, r: 6, shape: 'circle' },
      r3: { x: 60, y: 58, r: 6, shape: 'circle' },
    },
  },

  ps4_dualshock: {
    image: '/assets/controllers/ps4_dualshock.png',
    label: 'PS4 DualShock 4',
    hotspots: {
      up:    { x: 18, y: 30, w: 7, h: 10, shape: 'rect' },
      down:  { x: 18, y: 50, w: 7, h: 10, shape: 'rect' },
      left:  { x: 9,  y: 40, w: 10, h: 7, shape: 'rect' },
      right: { x: 24, y: 40, w: 10, h: 7, shape: 'rect' },
      a: { x: 82, y: 48, r: 4.5, shape: 'circle' },  // Cross
      b: { x: 89, y: 40, r: 4.5, shape: 'circle' },  // Circle
      x: { x: 75, y: 40, r: 4.5, shape: 'circle' },  // Square
      y: { x: 82, y: 32, r: 4.5, shape: 'circle' },  // Triangle
      l:  { x: 10, y: 8, w: 18, h: 8, shape: 'rect' },
      r:  { x: 72, y: 8, w: 18, h: 8, shape: 'rect' },
      zl: { x: 12, y: 0, w: 14, h: 7, shape: 'rect' },
      zr: { x: 74, y: 0, w: 14, h: 7, shape: 'rect' },
      select: { x: 36, y: 28, w: 7, h: 5, shape: 'rect' },
      start:  { x: 57, y: 28, w: 7, h: 5, shape: 'rect' },
      home:   { x: 50, y: 40, r: 3, shape: 'circle' },
      l3: { x: 34, y: 58, r: 6, shape: 'circle' },
      r3: { x: 66, y: 58, r: 6, shape: 'circle' },
    },
  },

  switch_pro: {
    image: '/assets/controllers/switch_pro.png',
    label: 'Switch Pro',
    hotspots: {
      up:    { x: 20, y: 44, w: 7, h: 10, shape: 'rect' },
      down:  { x: 20, y: 64, w: 7, h: 10, shape: 'rect' },
      left:  { x: 11, y: 54, w: 10, h: 7, shape: 'rect' },
      right: { x: 26, y: 54, w: 10, h: 7, shape: 'rect' },
      a: { x: 80, y: 50, r: 4.5, shape: 'circle' },
      b: { x: 87, y: 42, r: 4.5, shape: 'circle' },
      x: { x: 73, y: 42, r: 4.5, shape: 'circle' },
      y: { x: 80, y: 34, r: 4.5, shape: 'circle' },
      l:  { x: 10, y: 6, w: 18, h: 9, shape: 'rect' },
      r:  { x: 72, y: 6, w: 18, h: 9, shape: 'rect' },
      zl: { x: 12, y: 0, w: 14, h: 6, shape: 'rect' },
      zr: { x: 74, y: 0, w: 14, h: 6, shape: 'rect' },
      select: { x: 36, y: 30, w: 7, h: 5, shape: 'rect' },
      start:  { x: 57, y: 30, w: 7, h: 5, shape: 'rect' },
      home:   { x: 50, y: 48, r: 3, shape: 'circle' },
      l3: { x: 30, y: 30, r: 6, shape: 'circle' },
      r3: { x: 60, y: 56, r: 6, shape: 'circle' },
    },
  },
};

// Fallback for unknown profiles — uses the 8BitDo Pro 2
const DEFAULT_PROFILE = '8bitdo_pro_2';

/* ── Overlay color logic ──── */
const getOverlayStyle = (key, activeButton, pressedButtons, mappedButtons) => {
  const isPressed = pressedButtons?.has(key);
  const isActive  = key === activeButton;
  const isMapped  = mappedButtons?.has(key);

  let bg = 'transparent';
  let border = 'transparent';
  let shadow = 'none';
  let anim = undefined;

  if (isPressed) {
    bg = `${CYAN}55`;
    border = CYAN;
    shadow = `0 0 12px ${CYAN}, 0 0 24px ${CYAN}44`;
  } else if (isActive) {
    bg = `${AMBER}33`;
    border = AMBER;
    shadow = `0 0 14px ${AMBER}, 0 0 28px ${AMBER}44`;
    anim = 'gp-pulse-dot 1.2s ease-in-out infinite';
  } else if (isMapped) {
    bg = `${GREEN}22`;
    border = `${GREEN}88`;
  }

  return { backgroundColor: bg, borderColor: border, boxShadow: shadow, animation: anim };
};

function ControllerSVG({ activeButton, pressedButtons, mappedButtons, profileId }) {
  const profileKey = profileId && PROFILES[profileId] ? profileId : DEFAULT_PROFILE;
  const profile = PROFILES[profileKey];

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        maxWidth: '540px',
        margin: '0 auto',
      }}
    >
      {/* PNG Controller Image */}
      <img
        src={profile.image}
        alt={profile.label}
        draggable={false}
        style={{
          width: '100%',
          height: 'auto',
          display: 'block',
          borderRadius: '12px',
          userSelect: 'none',
        }}
      />

      {/* SVG Hotspot Overlays */}
      {Object.entries(profile.hotspots).map(([key, spot]) => {
        const style = getOverlayStyle(key, activeButton, pressedButtons, mappedButtons);

        if (spot.shape === 'circle') {
          return (
            <div
              key={key}
              title={key.toUpperCase()}
              style={{
                position: 'absolute',
                left: `${spot.x - spot.r}%`,
                top: `${spot.y - spot.r}%`,
                width: `${spot.r * 2}%`,
                height: `${spot.r * 2}%`,
                borderRadius: '50%',
                border: `2px solid ${style.borderColor}`,
                backgroundColor: style.backgroundColor,
                boxShadow: style.boxShadow,
                animation: style.animation,
                transition: 'all 0.15s ease',
                pointerEvents: 'none',
                zIndex: 2,
              }}
            />
          );
        }

        // Rectangle hotspot
        return (
          <div
            key={key}
            title={key.toUpperCase()}
            style={{
              position: 'absolute',
              left: `${spot.x}%`,
              top: `${spot.y}%`,
              width: `${spot.w}%`,
              height: `${spot.h}%`,
              borderRadius: '4px',
              border: `2px solid ${style.borderColor}`,
              backgroundColor: style.backgroundColor,
              boxShadow: style.boxShadow,
              animation: style.animation,
              transition: 'all 0.15s ease',
              pointerEvents: 'none',
              zIndex: 2,
            }}
          />
        );
      })}

      {/* Profile badge */}
      <div
        style={{
          position: 'absolute',
          bottom: '8px',
          right: '12px',
          fontSize: '0.65rem',
          fontWeight: 700,
          color: '#64748b',
          background: 'rgba(15, 23, 42, 0.8)',
          padding: '2px 8px',
          borderRadius: '6px',
          zIndex: 3,
        }}
      >
        {profile.label}
      </div>
    </div>
  );
}

export default memo(ControllerSVG);
