/**
 * ProfileSelect: Lightweight user profile selector
 * Used to tag panel operations by user (e.g., scorekeeper:dad, led:mom)
 */

export default function ProfileSelect({ value, onChange }) {
  const profiles = ['guest', 'dad', 'mom', 'tim', 'sarah']

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="input w-40"
      style={{
        padding: '8px 12px',
        background: '#0a0a0a',
        border: '1px solid rgba(200, 255, 0, 0.3)',
        borderRadius: '6px',
        color: '#ffffff',
        fontSize: '14px',
        cursor: 'pointer'
      }}
    >
      {profiles.map((profile) => (
        <option key={profile} value={profile}>
          {profile.charAt(0).toUpperCase() + profile.slice(1)}
        </option>
      ))}
    </select>
  )
}
