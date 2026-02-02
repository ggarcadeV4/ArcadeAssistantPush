/**
 * TTS (Text-to-Speech) Client
 * Handles ElevenLabs TTS API calls via gateway
 */

const TTS_ENDPOINT = '/api/voice/tts'

// Force module inclusion
console.log('[TTS Client] Module loaded')

// Track currently playing audio so we can stop it
let currentAudio = null
let fallbackUtterance = null

/**
 * Stop any currently playing TTS audio
 * Uses try-catch to prevent any errors from bubbling up
 */
export function stopSpeaking() {
  if (currentAudio) {
    console.log('[TTS] Stopping current audio playback')
    try {
      // Store reference and clear immediately to prevent race conditions
      const audio = currentAudio
      currentAudio = null

      // Only manipulate audio if it's in a valid state
      if (audio.readyState > 0) {
        audio.pause()
        // Only seek if not already at start (avoids potential Windows audio driver issues)
        if (audio.currentTime > 0) {
          audio.currentTime = 0
        }
      }
    } catch (err) {
      console.warn('[TTS] Error while stopping audio (non-fatal):', err)
      // Ensure currentAudio is cleared even if there was an error
      currentAudio = null
    }
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
 * Check if TTS is currently speaking
 * @returns {boolean}
 */
export function isSpeaking() {
  return currentAudio !== null && !currentAudio.paused
}

/**
 * Speak text using ElevenLabs TTS
 * @param {string} text - Text to speak
 * @param {Object} options - TTS options
 * @param {string} options.voice_profile - Named voice profile (e.g., 'lora', 'adam')
 * @param {string} options.voice_id - Direct ElevenLabs voice ID (overrides profile)
 * @param {string} options.model_id - ElevenLabs model ID
 * @returns {Promise<void>} - Resolves when audio playback COMPLETES
 */
export async function speak(text, options = {}) {
  // Stop any currently playing audio before starting new one
  stopSpeaking()
  if (!text || typeof text !== 'string') {
    console.warn('[TTS] No text provided')
    return
  }

  const { voice_profile, voice_id, model_id } = options

  console.log('[TTS] Speaking:', {
    text: text.substring(0, 50) + (text.length > 50 ? '...' : ''),
    voice_profile,
    voice_id,
    model_id,
    textLength: text.length
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
        text,
        voice_profile,
        voice_id,
        model_id
      })
    })

    console.log('[TTS] Response status:', response.status, 'Content-Type:', response.headers.get('content-type'))

    if (response.status === 501) {
      console.warn('[TTS] TTS not configured (missing ElevenLabs API key) - falling back to browser speech if available')
      return speakWithBrowserVoice(text, { voice_profile: voice_profile || voice_id })
    }

    if (response.status === 429) {
      const data = await response.json()
      console.warn('[TTS] Daily quota exceeded:', data)
      return
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Unknown error' }))
      console.error('[TTS] Error:', error)
      return speakWithBrowserVoice(text, { voice_profile: voice_profile || voice_id })
    }

    // Get audio blob and play it
    const audioBlob = await response.blob()
    console.log('[TTS] Audio blob size:', audioBlob.size, 'bytes, type:', audioBlob.type)

    if (audioBlob.size === 0) {
      console.error('[TTS] Audio blob is empty (0 bytes)')
      return
    }

    if (!audioBlob.type || !audioBlob.type.startsWith('audio/')) {
      console.warn('[TTS] Unexpected blob type:', audioBlob.type, '- expected audio/*')
    }

    const audioUrl = URL.createObjectURL(audioBlob)
    console.log('[TTS] Created blob URL:', audioUrl)
    
    const audio = new Audio(audioUrl)
    currentAudio = audio  // Track the audio so we can stop it

    console.log('[TTS] Audio element created, attempting to play...')
    console.log('[TTS] Audio element state - readyState:', audio.readyState, 'paused:', audio.paused)

    // Return a promise that resolves when audio playback COMPLETES
    return new Promise((resolve, reject) => {
      // Clean up URL after playing
      audio.onended = () => {
        console.log('[TTS] Audio playback completed')
        URL.revokeObjectURL(audioUrl)
        if (currentAudio === audio) {
          currentAudio = null
        }
        resolve() // Resolve when audio finishes
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
        URL.revokeObjectURL(audioUrl)
        if (currentAudio === audio) {
          currentAudio = null
        }
        reject(new Error('Audio playback failed'))
      }

      // Start playing
      audio.play()
        .then(() => {
          console.log('[TTS] Audio.play() called successfully - now playing')
        })
        .catch((playError) => {
          console.error('[TTS] Audio.play() failed:', playError)
          console.error('[TTS] This may be due to browser autoplay policy. User interaction required.')
          // Try to play with volume set explicitly
          audio.volume = 1.0
          audio.play()
            .then(() => {
              console.log('[TTS] Retry with volume=1.0 succeeded')
            })
            .catch((retryError) => {
              console.error('[TTS] Retry failed:', retryError)
              reject(retryError)
            })
        })
    })

  } catch (error) {
    console.error('[TTS] Request error:', error)
    const fallback = speakWithBrowserVoice(text, { voice_profile: options.voice_profile || options.voice_id })
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

function speakWithBrowserVoice(text, { voice_profile } = {}) {
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
      fallbackUtterance = utterance
      utterance.onend = () => {
        fallbackUtterance = null
        resolve()
      }
      utterance.onerror = (err) => {
        console.error('[TTS] Browser speech synthesis failed:', err)
        fallbackUtterance = null
        reject(err.error || err)
      }

      try {
        synth.cancel()
        synth.speak(utterance)
      } catch (err) {
        fallbackUtterance = null
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
  return speak(text, { voice_id: 'bVMeCyTHy58xNoL34h3p' })
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
