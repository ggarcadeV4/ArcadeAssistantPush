import React from 'react'
import { diffLines } from '../../utils/diffPreview'

export default function DiffPreview({ oldText, newText }: { oldText: string; newText: string }) {
  const lines = diffLines(oldText, newText)
  return (
    <pre className="aa-diff">
      {lines.map((l, i) => (
        <div key={i} className={`ln ${l.op === '+' ? 'add' : l.op === '-' ? 'del' : 'same'}`}>
          <span className="op">{l.op}</span> {l.text}
        </div>
      ))}
    </pre>
  )
}

