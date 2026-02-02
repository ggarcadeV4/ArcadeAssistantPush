// Minimal STT shim (Deepgram). Enable via env DEEPGRAM_API_KEY.
export async function transcribePcm16le(buffer) {
  if (!process.env.DEEPGRAM_API_KEY) return { code: 'NOT_CONFIGURED' };
  const r = await fetch('https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true', {
    method: 'POST',
    headers: {
      'Authorization': `Token ${process.env.DEEPGRAM_API_KEY}`,
      'Content-Type': 'audio/wav'
    },
    body: buffer
  });
  if (!r.ok) return { error: await r.text() };
  const j = await r.json();
  const text = j?.results?.channels?.[0]?.alternatives?.[0]?.transcript || '';
  return { text };
}

