// Single source of truth for known arcade encoder board identifiers.
// All panels must import from here — never hardcode board strings inline.

export const KNOWN_ENCODER_BOARDS = [
  { type: 'pacto_2000t', vid: '0x045E', pid: '0x028E', nodeCount: 2, label: 'Pacto Tech 2000T' },
  { type: 'pacto_4000t', vid: '0x045E', pid: '0x028E', nodeCount: 4, label: 'Pacto Tech 4000T' },
  { type: 'ipac',        vid: '0xD209', pid: '0x0301', nodeCount: null, label: 'Ultimarc I-PAC' },
  { type: 'ipac_mini',   vid: '0xD209', pid: '0x0310', nodeCount: null, label: 'Ultimarc Mini-PAC' },
  { type: 'brook_ufb',   vid: null,     pid: null,     nodeCount: 1,    label: 'Brook UFB' },
];

export const ENCODER_BOARD_LABELS = KNOWN_ENCODER_BOARDS.map(b => b.label);

/**
 * Determines whether a hardware payload from the backend WebSocket
 * represents a known arcade encoder node (not a handheld gamepad).
 * Never use hardcoded strings in components — call this instead.
 *
 * @param {object} hardwarePayload - The validated JSON from /ws/encoder-events
 * @returns {boolean}
 */
export function isConfirmedEncoderNode(hardwarePayload) {
  if (!hardwarePayload) return false;
  const { vid, pid, board_type } = hardwarePayload;
  if (board_type) {
    return KNOWN_ENCODER_BOARDS.some(b => b.type === board_type.toLowerCase());
  }
  if (vid && pid) {
    return KNOWN_ENCODER_BOARDS.some(b => b.vid === vid && b.pid === pid);
  }
  return false;
}
