export function streamChat(onChunk: (t: string) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const es = new EventSource("/api/ai/chat/stream");
    es.onmessage = (ev) => {
      try {
        const { chunk } = JSON.parse(ev.data);
        if (chunk) onChunk(chunk);
      } catch {}
    };
    es.onerror = () => { es.close(); reject(new Error("SSE error")); };
    es.onopen = () => {};
    // We resolve when server closes the stream
    es.addEventListener("end", () => { es.close(); resolve(); });
  });
}
