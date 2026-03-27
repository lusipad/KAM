import type { ReactNode } from 'react'

import type { ToastItem } from '@/layout/Toast'
import { Toast } from '@/layout/Toast'

type AppShellProps = {
  sidebar: ReactNode
  main: ReactNode
  panel: ReactNode
  memoryOpen: boolean
  breadcrumb: string
  onToggleMemory: () => void
  toasts: ToastItem[]
}

export function AppShell({ sidebar, main, panel, memoryOpen, breadcrumb, onToggleMemory, toasts }: AppShellProps) {
  return (
    <div className={`kam-shell ${memoryOpen ? 'memory-open' : ''}`}>
      {sidebar}

      <div className="shell-main">
        <header className="topbar">
          <div className="breadcrumb">{breadcrumb}</div>
          <button type="button" className={`memory-toggle ${memoryOpen ? 'is-active' : ''}`} onClick={onToggleMemory}>
            记忆
          </button>
        </header>

        <main className="main-stage">{main}</main>

        {toasts.length ? (
          <div className="toast-stack">
            {toasts.map((toast) => (
              <Toast key={toast.id} toast={toast} />
            ))}
          </div>
        ) : null}
      </div>

      <aside className={`memory-panel-shell ${memoryOpen ? 'is-open' : ''}`}>{panel}</aside>
    </div>
  )
}
