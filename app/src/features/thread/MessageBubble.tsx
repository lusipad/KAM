import type { MessageRecord } from '@/types/v3'

export function MessageBubble({ message }: { message: MessageRecord }) {
  if (message.role === 'user') {
    return (
      <div className="message-row is-user">
        <div className="message-bubble">{message.content}</div>
      </div>
    )
  }

  return (
    <div className="message-row is-assistant">
      <div className="assistant-copy">{message.content}</div>
    </div>
  )
}
