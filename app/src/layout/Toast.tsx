export interface ToastAction {
  label: string
  onClick: () => void
}

export interface ToastItem {
  id: string
  message: string
  tone?: 'amber' | 'green' | 'red' | 'gray'
  action?: ToastAction
}

const toneClass = {
  amber: 'is-amber',
  green: 'is-green',
  red: 'is-red',
  gray: 'is-gray',
}

export function Toast({ toast }: { toast: ToastItem }) {
  return (
    <div className={`toast ${toneClass[toast.tone ?? 'gray']}`}>
      <span className="toast-dot" />
      <span className="toast-copy">{toast.message}</span>
      {toast.action ? (
        <button type="button" className="toast-link" onClick={toast.action.onClick}>
          {toast.action.label}
        </button>
      ) : null}
    </div>
  )
}
