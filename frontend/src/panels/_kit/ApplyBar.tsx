import React from 'react'

export default function ApplyBar({ canApply, onApply, onRevert }: {
  canApply: boolean
  onApply: () => void
  onRevert: () => void
}) {
  return (
    <div className="aa-applybar">
      <button disabled={!canApply} onClick={onApply}>Apply</button>
      <button onClick={onRevert}>Revert</button>
    </div>
  )
}

