import { useCallback, useState } from 'react'

import { getErrorMessage } from '@/api/client'
import type { ToastItem } from '@/layout/Toast'

export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const pushToast = useCallback((toast: ToastItem) => {
    setToasts((current) => [...current, toast])
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== toast.id))
    }, 10000)
  }, [])

  const onError = useCallback(
    (error: unknown, fallback: string) => {
      pushToast({
        id: `error-${Date.now()}`,
        message: getErrorMessage(error, fallback),
        tone: 'red',
      })
    },
    [pushToast],
  )

  return { toasts, pushToast, onError }
}
