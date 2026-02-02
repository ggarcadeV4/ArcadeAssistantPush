export function sentenceBoundaryAccumulator(onSentence: (s: string) => void) {
  let buf = "";
  const end = /[.!?](\s|$)/;
  return (chunk: string) => {
    buf += chunk;
    const m = buf.match(end);
    if (m && m.index != null) {
      const first = buf.slice(0, m.index + 1);
      buf = buf.slice(m.index + 1);
      const s = first.trim();
      if (s) onSentence(s);
    }
  };
}

