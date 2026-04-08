/**
 * deweyResolve.js — Deterministic Media Resolver
 *
 * This endpoint decouples image/media resolution from Dewey's chat.
 * The frontend calls this IN PARALLEL with the chat request.
 * 
 * Flow:
 *   1. Receives raw user message
 *   2. Extracts game subject using the LaunchBox index (no AI call)
 *   3. Resolves local media assets for that game
 *   4. Returns structured result: game metadata + image URLs
 *
 * This replaces the fragile chain of:
 *   chat AI → historian AI → fuzzy title extraction → filesystem scan
 * With:
 *   user text → deterministic index lookup → local file paths
 */

import { Router } from 'express';
import { extractSubject, resolvePreferredMedia, getIndexStats, getPreferredPlatformsFromQuery } from '../services/launchboxIndex.js';

const router = Router();

function cleanField(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function buildResolveQuery(message, activeTitle, activePlatform, activeVisualIntent) {
  const raw = cleanField(message);
  if (!raw) {
    return { query: '', usedActiveSubject: false };
  }

  const explicitGame = extractSubject(raw);
  if (explicitGame || !activeTitle) {
    return { query: raw, usedActiveSubject: false };
  }

  const explicitPlatforms = getPreferredPlatformsFromQuery(raw);
  const parts = [raw, activeTitle];

  if (explicitPlatforms.length === 0 && activePlatform) {
    parts.push(activePlatform);
  }
  if (activeVisualIntent) {
    parts.push(activeVisualIntent);
  }

  return {
    query: parts.filter(Boolean).join(' '),
    usedActiveSubject: true,
  };
}

/**
 * POST /api/dewey/resolve
 * Body: { message: "show me what Pac-Man looks like" }
 * Returns: { found: true, game: { title, platform, ... }, images: [...], source: 'launchbox-xml' }
 */
router.post('/', (req, res) => {
  try {
    const { message, active_title, active_platform, active_visual_intent } = req.body || {};
    if (!message || typeof message !== 'string' || message.trim().length === 0) {
      return res.status(400).json({ error: 'message string required' });
    }

    const raw = message.trim();
    const activeTitle = cleanField(active_title);
    const activePlatform = cleanField(active_platform);
    const activeVisualIntent = cleanField(active_visual_intent);
    console.log(`[Dewey Resolve] Input: "${raw}"`);

    const { query: resolveQuery, usedActiveSubject } = buildResolveQuery(
      raw,
      activeTitle,
      activePlatform,
      activeVisualIntent,
    );
    if (usedActiveSubject) {
      console.log(`[Dewey Resolve] Reused active subject -> "${resolveQuery}"`);
    }

    // Extract game subject from raw user text
    const game = extractSubject(resolveQuery);

    if (!game) {
      console.log('[Dewey Resolve] No game subject found in message');
      return res.status(200).json({
        found: false,
        game: null,
        images: [],
        source: 'none'
      });
    }

    console.log(`[Dewey Resolve] Matched: "${game.title}" (${game.platform})`);

    // Resolve local media assets
    const { resolvedGame, primaryMedia, images, video } = resolvePreferredMedia(game, resolveQuery);
    const activeGame = resolvedGame || game;
    console.log(`[Dewey Resolve] Resolved ${images.length} image assets${video ? ' plus video snap' : ''} for "${activeGame.title}" (${activeGame.platform})`);

    return res.status(200).json({
      found: true,
      game: {
        title: activeGame.title,
        platform: activeGame.platform,
        developer: activeGame.developer || '',
        publisher: activeGame.publisher || '',
        genre: activeGame.genre || '',
        releaseDate: activeGame.releaseDate || '',
        year: activeGame.releaseDate ? activeGame.releaseDate.split('-')[0] : '',
        notes: activeGame.notes || '',
        videoUrl: activeGame.videoUrl || '',
        series: activeGame.series || '',
        maxPlayers: activeGame.maxPlayers || '',
      },
      images,
      videos: video ? [video] : [],
      primaryImage: images[0] || null,
      primaryVideo: video || null,
      primaryMedia: primaryMedia || images[0] || video || null,
      source: 'launchbox-xml'
    });
  } catch (err) {
    console.error('[Dewey Resolve] Error:', err);
    return res.status(500).json({ error: 'resolve failed' });
  }
});

/**
 * GET /api/dewey/resolve/health
 * Returns index health and stats.
 */
router.get('/health', (req, res) => {
  const stats = getIndexStats();
  res.status(200).json({
    status: stats.ready ? 'ok' : 'initializing',
    ...stats
  });
});

export default router;
