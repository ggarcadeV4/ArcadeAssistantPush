export type DiffLine = { op: ' ' | '-' | '+', text: string }

export function diffLines(oldText: string, newText: string): DiffLine[] {
  const a = oldText.split(/\r?\n/), b = newText.split(/\r?\n/)
  const out: DiffLine[] = []; let i = 0, j = 0
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) { out.push({ op:' ', text:a[i++] }); j++; continue }
    if (j + 1 < b.length && i < a.length && a[i] === b[j + 1]) { out.push({ op:'+', text:b[j++] }); continue }
    if (i + 1 < a.length && j < b.length && a[i + 1] === b[j]) { out.push({ op:'-', text:a[i++] }); continue }
    if (i < a.length && j < b.length) { out.push({ op:'-', text:a[i++] }); out.push({ op:'+', text:b[j++] }); continue }
    if (i < a.length) { out.push({ op:'-', text:a[i++] }); continue }
    if (j < b.length) { out.push({ op:'+', text:b[j++] }); continue }
  }
  return out
}

export function toUnified(out: DiffLine[]): string {
  return out.map(d => `${d.op} ${d.text}`).join('\n')
}

