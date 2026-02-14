/*
Add a tiny diff helper for previewing config changes in the UI:
- diffLines(oldText, newText)  returns an array of { op: ' ' | '-' | '+', text }
- toUnified(diff)              returns a printable string for <pre> blocks
Greedy algorithm (good enough for INI/JSON tweaks), no external deps, ESM-compatible.
*/

// src/utils/diffPreview.ts
// Greedy line diff: ' ' same, '-' removed, '+' added. No deps.
export type DiffLine = { op: ' ' | '-' | '+', text: string };

export function diffLines(oldText: string, newText: string): DiffLine[] {
  const a = oldText.split(/\r?\n/), b = newText.split(/\r?\n/);
  const out: DiffLine[] = []; let i = 0, j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) { out.push({ op:' ', text:a[i++] }); j++; continue; }
    if (j + 1 < b.length && i < a.length && a[i] === b[j + 1]) { out.push({ op:'+', text:b[j++] }); continue; } // insert in b
    if (i + 1 < a.length && j < b.length && a[i + 1] === b[j]) { out.push({ op:'-', text:a[i++] }); continue; } // delete from a
    if (i < a.length && j < b.length) { out.push({ op:'-', text:a[i++] }); out.push({ op:'+', text:b[j++] }); continue; }
    if (i < a.length) { out.push({ op:'-', text:a[i++] }); continue; }
    if (j < b.length) { out.push({ op:'+', text:b[j++] }); continue; }
  }
  return out;
}

export function toUnified(out: DiffLine[]): string {
  return out.map(d => `${d.op} ${d.text}`).join('\n');
}

