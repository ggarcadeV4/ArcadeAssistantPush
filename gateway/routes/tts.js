import express from 'express';
import { errors } from '../lib/errors.js';

const router = express.Router();

// In-memory, non-persistent quota tracker (keyed by x-device-id)
const ttsUsage = new Map(); // deviceId -> { day: 'YYYY-MM-DD', chars: number }
const DAILY_LIMIT = Number(process.env.TTS_DAILY_LIMIT || 250000);
function today() { return new Date().toISOString().slice(0, 10); }
function bump(deviceId, chars) {
  const d = today();
  const cur = ttsUsage.get(deviceId) || { day: d, chars: 0 };
  if (cur.day !== d) { cur.day = d; cur.chars = 0; }
  cur.chars += chars;
  ttsUsage.set(deviceId, cur);
  return cur.chars;
}

// ElevenLabs configuration
const ELEVENLABS_CONFIG = {
  baseUrl: 'https://api.elevenlabs.io/v1',
  defaultVoiceId: 'pNInz6obpgDQGcFmaJgB', // Adam voice
  maxTextLength: 2500,
  timeoutMs: 30000,
  voiceProfiles: {
    vicky: process.env.VICKY_VOICE_ID || 'ThT5KcBeYPX3keUQqHPh',
    lora: process.env.LORA_VOICE_ID || 'pFZP5JQG7iQjIQuC4Bku',
    sam: process.env.SAM_VOICE_ID || 'bIHbv24MWmeRgasZH58o', // Scorekeeper Sam - enthusiastic referee voice
    doc: process.env.DOC_VOICE_ID || 'pNInz6obpgDQGcFmaJgB', // Doc health assistant voice (defaults to Adam)
    adam: 'pNInz6obpgDQGcFmaJgB',
    blinky: process.env.BLINKY_VOICE_ID || 'DTKMou8ccj1ZaWGBiotd',
    godot: process.env.GODOT_VOICE_ID || 'OYWwCdDHouzDwiZJWOOu', // Godot voice
    chuck: process.env.CHUCK_VOICE_ID || '5Q0t7uMcjvnagumLfvZi',
    gunner: process.env.GUNNER_VOICE_ID || '5Q0t7uMcjvnagumLfvZi',
    wiz: process.env.WIZ_VOICE_ID || 'CwhRBWXzGAHq8TQ4Fs17' // Console Wizard voice
  }
};

router.post('/tts', async (req, res) => {
  console.log('[TTS Route] Request received:', {
    body: req.body,
    headers: req.headers['x-device-id']
  })

  // Guard: Return 501 if neither ELEVENLABS_API_KEY nor Supabase is configured
  if (!process.env.ELEVENLABS_API_KEY && (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY)) {
    console.log('[TTS Route] Not configured - missing API key or Supabase credentials')
    return res.status(501).json({ code: 'NOT_CONFIGURED', service: 'tts' });
  }

  try {
    // Use turbo_v2_5 for lowest latency (faster response time)
    const { text, voice_id, voice_profile, model_id = 'eleven_turbo_v2_5' } = req.body;

    if (!text || typeof text !== 'string') {
      return res.status(400).json({
        error: 'Invalid request',
        message: 'text is required and must be a string'
      });
    }

    // Resolve voice ID: support named profiles (e.g., 'lora') or direct IDs
    let resolvedVoiceId = voice_id || ELEVENLABS_CONFIG.defaultVoiceId;
    if (voice_profile && ELEVENLABS_CONFIG.voiceProfiles[voice_profile]) {
      resolvedVoiceId = ELEVENLABS_CONFIG.voiceProfiles[voice_profile];
    }

    if (text.length > ELEVENLABS_CONFIG.maxTextLength) {
      return res.status(400).json({
        error: 'Text too long',
        message: `Text must be less than ${ELEVENLABS_CONFIG.maxTextLength} characters`
      });
    }

    // Soft in-memory quota gate keyed by device
    const deviceId = req.headers['x-device-id'] || 'unknown';
    const projected = bump(deviceId, 0) + text.length;
    if (projected > DAILY_LIMIT) {
      return res.status(429).json({ code: 'TTS_QUOTA_EXCEEDED', deviceId, used: projected, limit: DAILY_LIMIT });
    }

    // Determine API endpoint and headers
    let apiUrl, headers, body;

    // Optional override to force direct ElevenLabs (skip Supabase proxy)
    const forceDirect = ['1', 'true', 'yes', 'on'].includes(String(process.env.TTS_FORCE_DIRECT || '').trim().toLowerCase())

    if (!forceDirect && process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY) {
      // Use Supabase Edge Function
      apiUrl = `${process.env.SUPABASE_URL}/functions/v1/elevenlabs-proxy`;
      headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`
      };
      body = {
        text,
        voice_id: resolvedVoiceId, // Pass voice_id in body for proxy
        model_id,
        voice_settings: {
          stability: 0.4,
          similarity_boost: 0.7,
          style: 0,
          use_speaker_boost: true
        },
        optimize_streaming_latency: 4
      };
    } else {
      // Use Direct ElevenLabs API (Legacy)
      apiUrl = `${ELEVENLABS_CONFIG.baseUrl}/text-to-speech/${resolvedVoiceId}`;
      headers = {
        'Content-Type': 'application/json',
        'xi-api-key': process.env.ELEVENLABS_API_KEY
      };
      body = {
        text,
        model_id,
        voice_settings: {
          stability: 0.4,
          similarity_boost: 0.7,
          style: 0,
          use_speaker_boost: true
        },
        optimize_streaming_latency: 4
      };
    }

    // Call API
    const elevenLabsResponse = await Promise.race([
      fetch(apiUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(body)
      }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Request timeout')), ELEVENLABS_CONFIG.timeoutMs)
      )
    ]);

    if (!elevenLabsResponse.ok) {
      const error = await elevenLabsResponse.text();
      console.error('ElevenLabs API error:', error);

      return res.status(elevenLabsResponse.status).json({
        error: 'TTS API error',
        message: 'Failed to generate speech'
      });
    }

    // Stream audio response back to client
    res.setHeader('Content-Type', 'audio/mpeg');
    res.setHeader('Content-Disposition', 'attachment; filename="speech.mp3"');

    // Pipe the audio stream directly to response
    const audioBuffer = await elevenLabsResponse.arrayBuffer();
    // Update usage after success; warn at 80%
    const used = bump(deviceId, text.length);
    if (used / DAILY_LIMIT >= 0.8) res.setHeader('X-TTS-Quota-Warn', '80%');
    res.send(Buffer.from(audioBuffer));

  } catch (err) {
    console.error('TTS error:', err);

    if (err.message === 'Request timeout') {
      res.status(408).json({
        error: 'Request timeout',
        message: 'TTS request timed out'
      });
    } else {
      res.status(500).json({
        error: 'Internal error',
        message: 'Failed to process TTS request'
      });
    }
  }
});

// List available voices
router.get('/voices', async (req, res) => {
  // Guard: Return 501 if ELEVENLABS_API_KEY is not configured
  if (!process.env.ELEVENLABS_API_KEY) {
    return res.status(501).json({ code: 'NOT_CONFIGURED', service: 'tts' });
  }

  try {
    const voicesResponse = await fetch(`${ELEVENLABS_CONFIG.baseUrl}/voices`, {
      headers: {
        'xi-api-key': process.env.ELEVENLABS_API_KEY
      }
    });

    if (!voicesResponse.ok) {
      return res.status(voicesResponse.status).json({
        error: 'Failed to fetch voices'
      });
    }

    const voices = await voicesResponse.json();
    res.json(voices);

  } catch (err) {
    console.error('Voices fetch error:', err);
    res.status(500).json({
      error: 'Failed to fetch voices',
      message: err.message
    });
  }
});

export default router;

