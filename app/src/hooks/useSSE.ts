import { useEffect } from 'react'

export function useSSE(url: string | null, onEvent: (event: MessageEvent<string>) => void) {
  useEffect(() => {
    if (!url) {
      return
    }

    const source = new EventSource(url)
    source.onmessage = onEvent
    source.addEventListener('run_finished', onEvent as EventListener)
    source.addEventListener('run_progress', onEvent as EventListener)
    source.addEventListener('watcher_event', onEvent as EventListener)
    source.addEventListener('thread_updated', onEvent as EventListener)

    return () => {
      source.close()
    }
  }, [onEvent, url])
}
