/**
 * TTS (Text-to-Speech) Client
 * Handles ElevenLabs TTS API calls via gateway
 */

const TTS_ENDPOINT = '/api/voice/tts'
const TTS_DUPLICATE_SUPPRESS_MS = 7000

// Force module inclusion
console.log('[TTS Client] Module loaded')

// Track currently playing audio so we can stop it
let currentAudio = null
let currentAudioCancel = null
let fallbackUtterance = null
let fallbackCancel = null
let lastSpokenText = ''
let lastSpokenAtMs = 0

/**
 * Signal speaking mode to backend (fire-and-forget, non-blocking)
 * @param {boolean} enabled - true when speaking starts, false when done
 */
function signalSpeakingMode(enabled) {
  fetch('/api/cabinet/lighting/speaking', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled })
  }).catch(err => {
    console.warn('[TTS] Speaking mode signal failed (non-fatal):', err)
  })
}

function dedupeLeadingSentence(text) {
  const normalized = (text || '').trim()
  if (!normalized) return ''
  const repeat = normalized.match(/^([^.!?]{4,180}[.!?])(?:\s+\1)+\s*/i)
  if (!repeat) return normalized
  const tail = normalized.slice(repeat[0].length).trim()
  return [repeat[1], tail].filter(Boolean).join(' ')
}

function trimDeweyFiller(text) {
  let out = (text || '').trim()
  if (!out) return out

  // Remove common over-polite lead-ins that make users feel talked over.
  const fillerPatterns = [
    /^that's a great question[!.:\-\s]*/i,
    /^great question[!.:\-\s]*/i,
    /^excellent question[!.:\-\s]*/i,
    /^good question[!.:\-\s]*/i,
    /^absolutely[!.:\-\s]*/i,
    /^sure[!.:\-\s]*/i,
    /^well[,!\-\s]*/i
  ]

  for (const re of fillerPatterns) {
    out = out.replace(re, '').trim()
  }

  // If we trimmed too aggressively, keep original.
  return out || text.trim()
}

function normalizeSpeechText(text, { trimFiller = false } = {}) {
  let out = String(text || '').replace(/\s+/g, ' ').trim()
  if (!out) return ''
  out = dedupeLeadingSentence(out)
  if (trimFiller) {
    out = trimDeweyFiller(out)
  }
  return out
}

function isRapidDuplicateSpeech(text, windowMs = TTS_DUPLICATE_SUPPRESS_MS) {
  const now = Date.now()
  if (!text) return false
  const duplicate = lastSpokenText === text && (now - lastSpokenAtMs) < windowMs
  lastSpokenText = text
  lastSpokenAtMs = now
  return duplicate
}

/**
 * Stop any currently playing TTS audio.
 */
export function stopSpeaking() {
  try {
    if (typeof currentAudioCancel === 'function') {
      currentAudioCancel()
    }
  } catch (err) {
    console.warn('[TTS] Error while cancelling active audio promise:', err)
  } finally {
    currentAudioCancel = null
  }

  if (currentAudio) {
    console.log('[TTS] Stopping current audio playback')
    signalSpeakingMode(false)
    try {
      const audio = currentAudio
      currentAudio = null
      if (audio.readyState > 0) {
        audio.pause()
        if (audio.currentTime > 0) {
          audio.currentTime = 0
        }
      }
    } catch (err) {
      console.warn('[TTS] Error while stopping audio (non-fatal):', err)
      currentAudio = null
    }
  }

  try {
    if (typeof fallbackCancel === 'function') {
      fallbackCancel()
    }
  } catch (err) {
    console.warn('[TTS] Error while cancelling browser speech promise:', err)
  } finally {
    fallbackCancel = null
  }

  if (fallbackUtterance && typeof window !== 'undefined' && window.speechSynthesis) {
    try {
      window.speechSynthesis.cancel()
    } catch (err) {
      console.warn('[TTS] Error while cancelling browser speech synthesis:', err)
    } finally {
      fallbackUtterance = null
    }
  }
}

/**
 * Check if TTS is currently speaking.
 * @returns {boolean}
 */
export function isSpeaking() {
  const audioSpeaking = currentAudio !== null && !currentAudio.paused
  const browserSpeaking = typeof window !== 'undefined' &&
    !!fallbackUtterance &&
    !!window.speechSynthesis &&
    window.speechSynthesis.speaking
  return audioSpeaking || browserSpeaking
}

/**
 * Speak text using ElevenLabs TTS
 * @param {string} text - Text to speak
 * @param {Object} options - TTS options
 * @param {string} options.voice_profile - Named voice profile (e.g., 'lora', 'adam')
 * @param {string} options.voice_id - Direct ElevenLabs voice ID (overrides profile)
 * @param {string} options.model_id - ElevenLabs model ID
 * @param {number} options.maxDurationMs - Optional hard timeout for speech playback
 * @param {boolean} options.trimFiller - Optional lead-in trimming for concise delivery
 * @param {boolean} options.allowRapidRepeat - Allow repeated identical speech inside suppression window
 * @returns {Promise<void>} - Resolves when playback completes or is stopped
 */
export async function speak(text, options = {}) {
  stopSpeaking()

  const {
    voice_profile,
    voice_id,
    model_id,
    maxDurationMs,
    trimFiller = false,
    allowRapidRepeat = false
  } = options

  const speechText = normalizeSpeechText(text, { trimFiller })
  if (!speechText) {
    console.warn('[TTS] No text provided after normalization')
    return
  }

  if (!allowRapidRepeat && isRapidDuplicateSpeech(speechText)) {
    console.warn('[TTS] Suppressing rapid duplicate speech playback')
    return
  }

  console.log('[TTS] Speaking:', {
    text: speechText.substring(0, 50) + (speechText.length > 50 ? '...' : ''),
    voice_profile,
    voice_id,
    model_id,
    textLength: speechText.length,
    maxDurationMs: maxDurationMs || null
  })

  try {
    console.log('[TTS] Sending request to:', TTS_ENDPOINT)
    const response = await fetch(TTS_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-device-id': getDeviceId()
      },
      body: JSON.stringify({
        text: speechText,
        voice_profile,
        voice_id,
        model_id
      })
    })

    console.log('[TTS] Response status:', response.status, 'Content-Type:', response.headers.get('content-type'))

    if (response.status === 501) {
      console.warn('[TTS] TTS not configured; falling back to browser speech if available')
      return speakWithBrowserVoice(speechText, {
        voice_profile: voice_profile || voice_id,
        maxDurationMs
      })
    }

    if (response.status === 429) {
      const data = await response.json()
      console.warn('[TTS] Daily quota exceeded:', data)
      return
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Unknown error' }))
      console.error('[TTS] Error:', error)
      return speakWithBrowserVoice(speechText, {
        voice_profile: voice_profile || voice_id,
        maxDurationMs
      })
    }

    const audioBlob = await response.blob()
    console.log('[TTS] Audio received:', audioBlob.size, 'bytes, type:', audioBlob.type)

    if (audioBlob.size === 0) {
      console.error('[TTS] Audio blob is empty (0 bytes)')
      return
    }

    const audioUrl = URL.createObjectURL(audioBlob)
    const audio = new Audio()
    currentAudio = audio

    audio.preload = 'auto'
    audio.loop = false
    audio.src = audioUrl

    return new Promise((resolve, reject) => {
      let settled = false
      let forceStopTimer = null
      let playRequested = false

      const cleanup = () => {
        if (forceStopTimer) {
          clearTimeout(forceStopTimer)
          forceStopTimer = null
        }
        try { URL.revokeObjectURL(audioUrl) } catch {}
        if (currentAudio === audio) {
          currentAudio = null
        }
        if (currentAudioCancel) {
          currentAudioCancel = null
        }
      }

      const settle = (type, payload) => {
        if (settled) return
        settled = true
        signalSpeakingMode(false)
        cleanup()
        if (type === 'reject') {
          reject(payload)
        } else {
          resolve(payload)
        }
      }

      currentAudioCancel = () => {
        try {
          if (audio.readyState > 0) {
            audio.pause()
            if (audio.currentTime > 0) {
              audio.currentTime = 0
            }
          }
        } catch {}
        settle('resolve')
      }

      audio.onplaying = () => {
        console.log('[TTS] Audio playing')
        signalSpeakingMode(true)
      }

      audio.onended = () => {
        console.log('[TTS] Audio playback completed')
        settle('resolve')
      }

      audio.onerror = (err) => {
        console.error('[TTS] Audio playback error:', err)
        console.error('[TTS] Audio error details:', {
          code: audio.error?.code,
          message: audio.error?.message,
          MEDIA_ERR_ABORTED: audio.error?.code === 1,
          MEDIA_ERR_NETWORK: audio.error?.code === 2,
          MEDIA_ERR_DECODE: audio.error?.code === 3,
          MEDIA_ERR_SRC_NOT_SUPPORTED: audio.error?.code === 4
        })
        settle('reject', new Error('Audio playback failed'))
      }

      if (Number.isFinite(maxDurationMs) && maxDurationMs > 0) {
        forceStopTimer = setTimeout(() => {
          console.warn('[TTS] Max playback duration reached; stopping speech')
          if (typeof currentAudioCancel === 'function') {
            currentAudioCancel()
          }
        }, maxDurationMs)
      }

      audio.oncanplay = () => {
        if (playRequested || settled) return
        playRequested = true
        audio.oncanplay = null

        audio.play()
          .then(() => {
            console.log('[TTS] Audio.play() started')
          })
          .catch((playError) => {
            console.error('[TTS] Audio.play() failed:', playError)
            audio.volume = 1.0
            audio.play()
              .then(() => {
                console.log('[TTS] Retry with volume=1.0 succeeded')
              })
              .catch((retryError) => {
                settle('reject', retryError)
              })
          })
      }
    })

  } catch (error) {
    console.error('[TTS] Request error:', error)
    const fallback = speakWithBrowserVoice(speechText, {
      voice_profile: options.voice_profile || options.voice_id,
      maxDurationMs
    })
    if (fallback) return fallback
    throw error
  }
}

/**
 * Get or create device ID for quota tracking
 */
function getDeviceId() {
  let deviceId = localStorage.getItem('aa_device_id')
  if (!deviceId) {
    deviceId = `dev-${Date.now()}-${Math.random().toString(36).slice(2)}`
    localStorage.setItem('aa_device_id', deviceId)
  }
  return deviceId
}

function canUseBrowserSpeech() {
  return typeof window !== 'undefined' &&
    typeof window.speechSynthesis !== 'undefined' &&
    typeof window.SpeechSynthesisUtterance !== 'undefined'
}

function pickBrowserVoice(voices, hint) {
  if (!Array.isArray(voices) || voices.length === 0) return null
  if (!hint) {
    return voices.find(v => /en[-_]?US/i.test(v.lang)) || voices[0]
  }
  const lowerHint = hint.toLowerCase()
  return voices.find(v => v.name.toLowerCase().includes(lowerHint)) ||
    voices.find(v => /en[-_]?US/i.test(v.lang)) ||
    voices[0]
}

function speakWithBrowserVoice(text, { voice_profile, maxDurationMs } = {}) {
  if (!text || !canUseBrowserSpeech()) {
    return null
  }

  try {
    const synth = window.speechSynthesis
    const utterance = new SpeechSynthesisUtterance(text)
    const voices = synth.getVoices()
    const targetVoice = pickBrowserVoice(voices, voice_profile)
    if (targetVoice) {
      utterance.voice = targetVoice
    }
    utterance.rate = 1
    utterance.pitch = 1

    return new Promise((resolve, reject) => {
      let settled = false
      let forceStopTimer = null

      const settle = (type, payload) => {
        if (settled) return
        settled = true
        signalSpeakingMode(false)
        if (forceStopTimer) {
          clearTimeout(forceStopTimer)
          forceStopTimer = null
        }
        fallbackUtterance = null
        fallbackCancel = null
        if (type === 'reject') {
          reject(payload)
        } else {
          resolve(payload)
        }
      }

      fallbackUtterance = utterance
      fallbackCancel = () => {
        try { synth.cancel() } catch {}
        settle('resolve')
      }

      utterance.onstart = () => {
        console.log('[TTS] Browser speech started - signaling speaking mode ON')
        signalSpeakingMode(true)
      }

      utterance.onend = () => {
        console.log('[TTS] Browser speech ended - signaling speaking mode OFF')
        settle('resolve')
      }

      utterance.onerror = (err) => {
        console.error('[TTS] Browser speech synthesis failed:', err)
        settle('reject', err.error || err)
      }

      if (Number.isFinite(maxDurationMs) && maxDurationMs > 0) {
        forceStopTimer = setTimeout(() => {
          console.warn('[TTS] Browser speech max duration reached; stopping')
          if (typeof fallbackCancel === 'function') {
            fallbackCancel()
          }
        }, maxDurationMs)
      }

      try {
        synth.cancel()
        synth.speak(utterance)
      } catch (err) {
        fallbackUtterance = null
        fallbackCancel = null
        reject(err)
      }
    })
  } catch (err) {
    console.error('[TTS] Failed to use browser speech synthesis:', err)
    return null
  }
}

/**
 * Speak with Vicky's custom voice
 * @param {string} text - Text to speak
 */
export function speakAsVicky(text) {
  // TODO: Restore original Vicky ElevenLabs voice ID (Rachel / 21m00Tcm4TlvDq8ikWAM); frontend resolves via named profile only.
  return speak(text, { voice_profile: 'vicky' })
}

/**
 * Speak with LoRa's custom voice
 * @param {string} text - Text to speak
 */
export function speakAsLora(text) {
  return speak(text, { voice_profile: 'lora' })
}

/**
 * Speak with Doc's custom voice
 * @param {string} text - Text to speak
 */
export function speakAsDoc(text) {
  return speak(text, { voice_profile: 'doc' })
}

/**
 * Speak with Dewey's custom voice
 * @param {string} text - Text to speak
 */
export function speakAsDewey(text) {
  return speak(text, {
    // TODO: Verify Dewey ElevenLabs voice ID — current value may not
    // match original assigned voice. Backend profile uses
    // DEWEY_VOICE_ID (pNInz6obpgDQGcFmaJgB fallback) but frontend
    // overrides it here. Restore original assigned ID before V1 release.
    voice_id: 'bVMeCyTHy58xNoL34h3p',
    trimFiller: true
  })
}

/**
 * Speak with Sam's custom voice (Scorekeeper)
 * @param {string} text - Text to speak
 */
export function speakAsSam(text) {
  return speak(text, { voice_profile: 'sam' })
}

/**
 * Speak with LED Blinky's custom voice
 * @param {string} text - Text to speak
 */
export function speakAsBlinky(text) {
  return speak(text, { voice_profile: 'blinky' })
}

/**
 * Check if TTS is available
 * @returns {Promise<boolean>}
 */
export async function isTTSAvailable() {
  try {
    const response = await fetch('/api/health')
    if (!response.ok) return false
    const health = await response.json()
    return health.services?.tts?.available || false
  } catch {
    return false
  }
}
