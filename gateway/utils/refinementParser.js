export function parseRefinementText(rawText) {
  const text = (rawText || '').toString().trim();
  const lower = text.toLowerCase();

  const cancel = /^(?:cancel|never\s*mind|nevermind|stop|forget\s*it|start\s*over|exit)\b/i.test(lower);
  if (cancel) return { cancel: true };

  const yearMatch = lower.match(/\b(19\d{2}|20\d{2})\b/);
  const year = yearMatch ? Number(yearMatch[1]) : null;

  const ordinals = {
    first: 1,
    '1st': 1,
    second: 2,
    '2nd': 2,
    third: 3,
    '3rd': 3,
    fourth: 4,
    '4th': 4,
    fifth: 5,
    '5th': 5,
    last: -1
  };

  let ordinalIndex = null;
  for (const [k, v] of Object.entries(ordinals)) {
    if (new RegExp(`\\b${k}\\b`, 'i').test(lower)) {
      ordinalIndex = v;
      break;
    }
  }

  const original = /\boriginal\b/i.test(lower);

  const tokenMatch = lower.match(/\b(?:the\s+)?(.+?)\s+(?:one|version)\b/);
  const tokenText = tokenMatch ? tokenMatch[1].trim() : lower;

  return {
    cancel: false,
    year,
    ordinalIndex,
    original,
    tokenText
  };
}

export function matchPlatformKeys(tokenText, platformAliases) {
  const aliases = platformAliases && typeof platformAliases === 'object' ? platformAliases : {};
  const lower = (tokenText || '').toString().toLowerCase();

  const matched = [];
  for (const key of Object.keys(aliases)) {
    if (new RegExp(`\\b${escapeRegex(key)}\\b`, 'i').test(lower)) matched.push(key);
  }

  if (/\b(mame|arcade)\b/i.test(lower) && !matched.includes('arcade') && aliases.arcade) {
    matched.push('arcade');
  }

  return matched;
}

export function applyRefinement({ candidates, originalCandidates, refinement, platformAliases }) {
  const base = Array.isArray(candidates) ? candidates : [];
  const orig = Array.isArray(originalCandidates) ? originalCandidates : base;
  const r = refinement || {};

  if (r.ordinalIndex) {
    const idx = r.ordinalIndex === -1 ? base.length - 1 : r.ordinalIndex - 1;
    if (idx >= 0 && idx < base.length) {
      return { candidates: [base[idx]], reason: `ordinal:${r.ordinalIndex}` };
    }
    return { candidates: [], reason: `ordinal:${r.ordinalIndex}` };
  }

  let filtered = base;

  const platformKeys = matchPlatformKeys(r.tokenText, platformAliases);
  if (platformKeys.length > 0) {
    const allowed = new Set();
    for (const k of platformKeys) {
      const list = platformAliases?.[k];
      if (Array.isArray(list)) {
        for (const item of list) allowed.add((item || '').toString().toLowerCase());
      }
    }

    filtered = filtered.filter((c) => {
      const plat = (c?.platform || '').toString().toLowerCase();
      return allowed.has(plat);
    });
  }

  if (Number.isFinite(r.year)) {
    filtered = filtered.filter((c) => Number(c?.year) === r.year);
  }

  if (r.original) {
    const withYear = filtered.filter((c) => Number.isFinite(Number(c?.year)));
    if (withYear.length > 0) {
      const minYear = Math.min(...withYear.map((c) => Number(c.year)));
      filtered = filtered.filter((c) => Number(c?.year) === minYear);
    }

    const clean = filtered.filter((c) => !hasRemakeQualifier(c?.title));
    if (clean.length > 0) filtered = clean;
  }

  if (filtered.length === 0) {
    return { candidates: [], reason: buildRefinementReason(r), fallbackOriginal: orig };
  }

  return { candidates: filtered, reason: buildRefinementReason(r) };
}

function hasRemakeQualifier(title) {
  const t = (title || '').toString().toLowerCase();
  return /\b(remake|remaster|remastered|port)\b/.test(t);
}

function buildRefinementReason(r) {
  const parts = [];
  if (r.original) parts.push('original');
  if (Number.isFinite(r.year)) parts.push(String(r.year));
  const platformKeys = (r.tokenText && r.tokenText.length > 0) ? null : null;
  void platformKeys;
  return parts.join(' + ') || 'refinement';
}

function escapeRegex(s) {
  return (s || '').toString().replace(/[.*+?^${}()|[\\]\\]/g, '\\$&');
}
