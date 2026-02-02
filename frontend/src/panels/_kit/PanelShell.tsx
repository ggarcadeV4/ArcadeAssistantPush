import React from 'react'

type PanelShellProps = {
  title: string
  subtitle?: string
  icon?: string
  status?: 'online' | 'degraded' | 'offline'
  headerActions?: React.ReactNode
  className?: string
  bodyClassName?: string
  children: React.ReactNode
}

export default function PanelShell({
  title,
  subtitle,
  icon,
  children,
  status,
  headerActions,
  className,
  bodyClassName
}: PanelShellProps) {
  const panelClassName = ['aa-panel', className].filter(Boolean).join(' ')
  const bodyClass = ['aa-body', bodyClassName].filter(Boolean).join(' ')
  return (
    <div className={panelClassName}>
      <div className="aa-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {icon && <span style={{ fontSize: '24px' }}>{icon}</span>}
          <div>
            <h2 style={{ color: '#ffffff' }}>{title}</h2>
            {subtitle && <p style={{ fontSize: '12px', color: '#d1d5db', margin: 0 }}>{subtitle}</p>}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {headerActions}
          <span className={`aa-status ${status || 'online'}`}>{status || 'online'}</span>
        </div>
      </div>
      <div className={bodyClass}>{children}</div>
    </div>
  )
}
