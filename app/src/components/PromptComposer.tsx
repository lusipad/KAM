import { useEffect, useRef } from 'react'
import type { FormEvent } from 'react'

type PromptComposerProps = {
  value: string
  placeholder: string
  isSending?: boolean
  toneLabel?: string
  detailLabel?: string
  onChange: (value: string) => void
  onSubmit: () => void
}

export function PromptComposer({
  value,
  placeholder,
  isSending = false,
  toneLabel = '自动选择',
  detailLabel = '当前会按任务判断',
  onChange,
  onSubmit,
}: PromptComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) {
      return
    }
    textarea.style.height = '0px'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 168)}px`
  }, [value])

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit()
  }

  return (
    <form className="message-composer" onSubmit={handleSubmit}>
      <div className="composer-shell">
        <textarea
          ref={textareaRef}
          className="composer-textarea"
          placeholder={placeholder}
          value={value}
          rows={1}
          onChange={(event) => onChange(event.target.value)}
        />
        <button type="submit" className="composer-submit" disabled={isSending || !value.trim()}>
          {isSending ? '…' : '↗'}
        </button>
      </div>
      <div className="composer-meta">
        <span className="composer-agent">
          <span className="status-dot is-amber" />
          {toneLabel}
        </span>
        <span>{detailLabel}</span>
      </div>
    </form>
  )
}
