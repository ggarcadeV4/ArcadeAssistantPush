import { Router } from 'express';
import { ensureConfigured } from '../config/env.js';
import openaiChat from '../adapters/openai.js';
import anthropicChat from '../adapters/anthropic.js';
import geminiChat from '../adapters/gemini.js';
import { errors, toJson } from '../lib/errors.js';

const router = Router();

// Wikipedia article name overrides for games whose article title differs from game title
const WIKI_ARTICLE_MAP = {
  'pac-man': 'Pac-Man',
  'ms. pac-man': 'Ms._Pac-Man',
  'donkey kong': 'Donkey_Kong_(video_game)',
  'donkey kong jr.': 'Donkey_Kong_Jr.',
  'space invaders': 'Space_Invaders',
  'street fighter ii': 'Street_Fighter_II',
  'mortal kombat': 'Mortal_Kombat_(1992_video_game)',
  'double dragon': 'Double_Dragon_(video_game)',
  "dragon's lair": "Dragon%27s_Lair",
  'q*bert': 'Q*bert',
  'out run': 'Out_Run',
  'after burner': 'After_Burner_(video_game)',
  'r-type': 'R-Type',
  'metal slug': 'Metal_Slug_(video_game)',
  'punch-out!!': 'Punch-Out!!_(arcade_game)',
  'tron': 'Tron_(video_game)',
  'burger time': 'BurgerTime',
  'spy hunter': 'Spy_Hunter',
  'missile command': 'Missile_Command',
  'crazy kong': 'Crazy_Kong',
  'galaxian': 'Galaxian',
  'galaga': 'Galaga',
  'centipede': 'Centipede_(video_game)',
  'defender': 'Defender_(1981_video_game)',
  'robotron: 2084': 'Robotron:_2084',
  'tempest': 'Tempest_(video_game)',
  'joust': 'Joust_(video_game)',
  'dig dug': 'Dig_Dug',
  'frogger': 'Frogger',
  'asteroids': 'Asteroids_(video_game)',
  'battlezone': 'Battlezone_(1980_video_game)',
  'golden axe': 'Golden_Axe_(video_game)',
  'gauntlet': 'Gauntlet_(1985_video_game)',
  'paperboy': 'Paperboy_(video_game)',
  '1942': '1942_(video_game)',
};

// In-memory cache to avoid repeated Wikipedia lookups
const imageCache = new Map();

// Resolve image URL via Wikipedia REST API (returns servable upload.wikimedia.org thumbnails)
async function resolveImageUrl(title) {
  const key = (title || '').toLowerCase().trim();
  if (!key) return null;

  // Check cache first
  if (imageCache.has(key)) return imageCache.get(key);

  // Determine Wikipedia article name
  let articleName = WIKI_ARTICLE_MAP[key];
  if (!articleName) {
    // Fuzzy match
    for (const [mapKey, article] of Object.entries(WIKI_ARTICLE_MAP)) {
      if (key.includes(mapKey) || mapKey.includes(key)) {
        articleName = article;
        break;
      }
    }
  }
  if (!articleName) {
    // Default: title with spaces replaced by underscores
    articleName = title.replace(/ /g, '_');
  }

  // Query Wikipedia REST API for page summary (includes thumbnail)
  const attempts = [
    articleName,
    articleName + '_(video_game)',
    articleName + '_(arcade_game)'
  ];

  for (const attempt of attempts) {
    try {
      const wikiUrl = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(attempt)}`;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 4000);
      const res = await fetch(wikiUrl, {
        signal: controller.signal,
        headers: {
          'User-Agent': 'ArcadeAssistant/1.0 (arcade cabinet history project)',
          'Accept': 'application/json'
        }
      });
      clearTimeout(timeout);

      if (res.ok) {
        const data = await res.json();
        const imgUrl = data.thumbnail?.source || data.originalimage?.source || null;
        if (imgUrl) {
          console.log(`[Dewey Search] Image resolved for "${title}": ${imgUrl.slice(0, 80)}...`);
          imageCache.set(key, imgUrl);
          return imgUrl;
        }
      }
    } catch { /* timeout or network error — try next */ }
  }

  console.log(`[Dewey Search] No image found for "${title}"`);
  imageCache.set(key, null);
  return null;
}

const SEARCH_SYSTEM_PROMPT = `You are an arcade game historian database. When given a game title or arcade topic, return ONLY a JSON array (no markdown, no explanation) of 1-3 game objects.

Each object MUST have these fields:
{
  "title": "Full Game Title",
  "publisher": "Publisher/Developer",
  "year": "Release Year",
  "genre": "Genre",
  "cpu": "CPU specification (e.g. Z80 @ 3.072 MHz)",
  "resolution": "Screen resolution (e.g. 224x288)",
  "description": "2-3 sentence historical lore about this game",
  "tags": ["tag1", "tag2"],
  "era": "Era name (e.g. Golden Age 1978-1983)",
  "eraDescription": "1-2 sentence summary of this era in arcade history"
}

The first item should be the PRIMARY game the user asked about.
Include 1-2 related games from the same era or genre as side entries.
Be historically accurate. Include real CPU specs, release years, and developer info.
Return ONLY valid JSON — no markdown fences, no prose.`;

router.post('/', async (req, res) => {
  try {
    const { query } = req.body || {};
    if (!query || typeof query !== 'string' || query.trim().length === 0) {
      return res.status(400).json({ error: 'query string required' });
    }

    const provider = process.env.DEWEY_PROVIDER || 'gemini';
    if (!ensureConfigured(provider)) {
      return res.status(503).json({ error: 'AI provider not configured' });
    }

    const messages = [
      { role: 'system', content: SEARCH_SYSTEM_PROMPT },
      { role: 'user', content: query.trim() }
    ];

    const input = {
      messages,
      temperature: 0.3,
      max_tokens: 1200,
      timeout_ms: 15000
    };

    let out;
    if (provider === 'gpt' || provider === 'openai') {
      out = await openaiChat(input);
    } else if (provider === 'gemini' || provider === 'google') {
      out = await geminiChat(input);
    } else {
      out = await anthropicChat(input);
    }

    const raw = out?.message?.content || '';

    // Try to parse the JSON response
    let items = [];
    try {
      // Strip markdown fences if the model included them
      const cleaned = raw.replace(/```json\s*/g, '').replace(/```\s*/g, '').trim();
      const parsed = JSON.parse(cleaned);
      items = Array.isArray(parsed) ? parsed : [parsed];
    } catch (parseErr) {
      console.warn('[Dewey Search] Failed to parse AI response as JSON:', parseErr.message);
      console.warn('[Dewey Search] Raw response:', raw.slice(0, 300));
      return res.status(200).json({ items: [], raw, parseError: true });
    }

    // Normalize items and resolve real cabinet images in parallel
    items = await Promise.all(items.map(async (g) => {
      const title = g.title || 'Unknown';
      const imageUrl = await resolveImageUrl(title);
      return {
        title,
        publisher: g.publisher || g.developer || '',
        year: String(g.year || ''),
        genre: g.genre || '',
        cpu: g.cpu || '',
        resolution: g.resolution || '',
        description: g.description || '',
        tags: Array.isArray(g.tags) ? g.tags : [],
        era: g.era || '',
        eraDescription: g.eraDescription || g.era_description || '',
        image: imageUrl || null
      };
    }));

    console.log(`[Dewey Search] Query: "${query}" → ${items.length} results: ${items.map(g => g.title).join(', ')}`);
    res.status(200).json({ items });
  } catch (err) {
    console.error('[Dewey Search] Error:', err);
    const { status, body } = toJson(err);
    res.status(status).json(body);
  }
});

export default router;
