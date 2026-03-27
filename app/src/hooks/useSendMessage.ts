import { useState } from 'react'

type SendHandlers = {
  onDelta: (delta: string) => void
  onToolResult?: () => void
  onDone?: () => void
}

function parseEventBlock(block: string) {
  const lines = block.split('\n')
  let event = 'message'
  const dataLines: string[] = []

  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  return {
    event,
    data: dataLines.join('\n'),
  }
}

export function useSendMessage(threadId: string | null, handlers: SendHandlers) {
  const [isSending, setIsSending] = useState(false)

  const send = async (content: string) => {
    if (!threadId || !content.trim() || isSending) {
      return
    }

    setIsSending(true)
    try {
      const response = await fetch(`/api/threads/${threadId}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ content }),
      })

      if (!response.ok || !response.body) {
        throw new Error(await response.text())
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() ?? ''

        for (const block of blocks) {
          const parsed = parseEventBlock(block)
          if (!parsed.data) {
            continue
          }

          const payload = JSON.parse(parsed.data) as { delta?: string }
          if (parsed.event === 'text_delta' && payload.delta) {
            handlers.onDelta(payload.delta)
          }
          if (parsed.event === 'tool_result') {
            handlers.onToolResult?.()
          }
          if (parsed.event === 'done') {
            handlers.onDone?.()
          }
        }
      }

      handlers.onDone?.()
    } finally {
      setIsSending(false)
    }
  }

  return {
    isSending,
    send,
  }
}
