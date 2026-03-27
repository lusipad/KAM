import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  createProject,
  createThread,
  getHomeFeed,
  getMemory,
  getThread,
  listThreads,
  listWatchers,
} from '@/api/client'
import { HomeFeed } from '@/features/home/HomeFeed'
import { MemoryPanel } from '@/features/memory/MemoryPanel'
import { MessageInput } from '@/features/thread/MessageInput'
import { ThreadView } from '@/features/thread/ThreadView'
import { WatcherList } from '@/features/watcher/WatcherList'
import { useSSE } from '@/hooks/useSSE'
import { AppShell } from '@/layout/AppShell'
import { Sidebar } from '@/layout/Sidebar'
import type { ToastItem } from '@/layout/Toast'
import { inferProjectTitle, inferThreadTitle } from '@/lib/v3-ui'
import type { HomeFeedPayload, MemoryItem, ThreadDetail, ThreadSummary, WatcherRecord } from '@/types/v3'

type ViewMode = 'empty' | 'home' | 'thread' | 'watchers'

function EmptyState({
  value,
  onChange,
  onSubmit,
  isBusy,
}: {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  isBusy: boolean
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">+</div>
      <div className="empty-title">你现在要处理什么？</div>
      <div className="empty-copy">描述任务，或者直接贴仓库路径，剩下的交给 KAM。</div>
      <div className="empty-composer">
        <MessageInput
          value={value}
          placeholder="说下你要我做什么..."
          isSending={isBusy}
          onChange={onChange}
          onSubmit={onSubmit}
        />
      </div>
    </div>
  )
}

function App() {
  const [view, setView] = useState<ViewMode>('empty')
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [feed, setFeed] = useState<HomeFeedPayload | null>(null)
  const [watchers, setWatchers] = useState<WatcherRecord[]>([])
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null)
  const [thread, setThread] = useState<ThreadDetail | null>(null)
  const [threadLoading, setThreadLoading] = useState(false)
  const [memoryOpen, setMemoryOpen] = useState(false)
  const [emptyPrompt, setEmptyPrompt] = useState('')
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null)
  const [creatingThread, setCreatingThread] = useState(false)
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const pushToast = useCallback((toast: ToastItem) => {
    setToasts((current) => [...current, toast])
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== toast.id))
    }, 10000)
  }, [])

  const refreshThreads = useCallback(async () => {
    const data = await listThreads()
    setThreads(data.threads)
    return data.threads
  }, [])

  const refreshFeed = useCallback(async () => {
    const data = await getHomeFeed()
    setFeed(data)
    return data
  }, [])

  const refreshWatchers = useCallback(async () => {
    const data = await listWatchers()
    setWatchers(data.watchers)
    return data.watchers
  }, [])

  const refreshThread = useCallback(async (threadId: string) => {
    setThreadLoading(true)
    try {
      const data = await getThread(threadId)
      setThread(data)
      const memoryData = await getMemory(data.projectId)
      setMemories(memoryData.memories)
      return data
    } finally {
      setThreadLoading(false)
    }
  }, [])

  const refreshAll = useCallback(async () => {
    const [loadedThreads] = await Promise.all([refreshThreads(), refreshFeed(), refreshWatchers()])
    if (!loadedThreads.length) {
      setView('empty')
      return
    }

    setView((current) => (current === 'empty' ? 'home' : current))
  }, [refreshFeed, refreshThreads, refreshWatchers])

  useEffect(() => {
    void refreshAll()
  }, [refreshAll])

  useEffect(() => {
    if (!selectedThreadId) {
      setThread(null)
      setMemories([])
      return
    }
    void refreshThread(selectedThreadId)
  }, [refreshThread, selectedThreadId])

  const handleOpenThread = useCallback((threadId: string) => {
    setSelectedThreadId(threadId)
    setView('thread')
  }, [])

  const handleNewConversation = useCallback(async () => {
    if (!emptyPrompt.trim() || creatingThread) {
      return
    }

    setCreatingThread(true)
    try {
      const project = await createProject({
        title: inferProjectTitle(emptyPrompt),
        repoPath: emptyPrompt.includes(':\\') || emptyPrompt.startsWith('/') ? emptyPrompt : null,
      })
      const createdThread = await createThread(project.id, {
        title: inferThreadTitle(emptyPrompt),
      })
      await Promise.all([refreshThreads(), refreshFeed(), refreshWatchers()])
      setSelectedThreadId(createdThread.id)
      setPendingPrompt(emptyPrompt)
      setEmptyPrompt('')
      setView('thread')
    } finally {
      setCreatingThread(false)
    }
  }, [creatingThread, emptyPrompt, refreshFeed, refreshThreads, refreshWatchers])

  const homeEventsUrl = '/api/home/events'
  useSSE(
    homeEventsUrl,
    useCallback(
      (event) => {
        void refreshFeed()
        void refreshThreads()
        if (event.type === 'run_finished' && view !== 'home') {
          try {
            const payload = JSON.parse(event.data) as { runId: string; threadId: string; summary?: string; status?: string }
            pushToast({
              id: `${payload.runId}-${Date.now()}`,
              message: payload.summary || '一个后台任务刚刚完成。',
              tone: payload.status === 'failed' ? 'red' : 'green',
              action: {
                label: '查看',
                onClick: () => handleOpenThread(payload.threadId),
              },
            })
          } catch {
            // Ignore malformed payloads.
          }
        }
      },
      [handleOpenThread, pushToast, refreshFeed, refreshThreads, view],
    ),
  )

  useSSE(
    selectedThreadId ? `/api/threads/${selectedThreadId}/events` : null,
    useCallback(
      () => {
        if (selectedThreadId) {
          void refreshThread(selectedThreadId)
        }
        void refreshThreads()
        void refreshFeed()
      },
      [refreshFeed, refreshThread, refreshThreads, selectedThreadId],
    ),
  )

  const breadcrumb = useMemo(() => {
    if (view === 'thread' && thread) {
      return `${thread.project?.title ?? '项目'} / ${thread.title}`
    }
    if (view === 'watchers') {
      return '监控'
    }
    if (view === 'home') {
      return '首页'
    }
    return '新对话'
  }, [thread, view])

  const selectedProject = thread?.project ?? null
  const latestRun = thread?.runs.at(-1) ?? null
  const threadLookup = useMemo(() => Object.fromEntries(threads.map((item) => [item.id, item])), [threads])

  return (
    <AppShell
      sidebar={
        <Sidebar
          threads={threads}
          activeThreadId={selectedThreadId}
          activeView={view}
          memoryOpen={memoryOpen}
          summary={feed?.summary ?? '当前没有待处理项'}
          onSelectHome={() => setView('home')}
          onSelectThread={handleOpenThread}
          onSelectWatchers={() => setView('watchers')}
          onToggleMemory={() => setMemoryOpen((current) => !current)}
        />
      }
      breadcrumb={breadcrumb}
      memoryOpen={memoryOpen}
      onToggleMemory={() => setMemoryOpen((current) => !current)}
      toasts={toasts}
      panel={<MemoryPanel project={selectedProject} latestRun={latestRun} memories={memories} />}
      main={
        view === 'empty' ? (
          <EmptyState value={emptyPrompt} onChange={setEmptyPrompt} onSubmit={handleNewConversation} isBusy={creatingThread} />
        ) : view === 'watchers' ? (
          <WatcherList
            watchers={watchers}
            onCreateByConversation={() => {
              setView('empty')
              setEmptyPrompt('监控 ')
            }}
            onOpenThread={handleOpenThread}
            onRefresh={async () => {
              await refreshWatchers()
            }}
          />
        ) : view === 'thread' ? (
          <ThreadView
            thread={thread}
            loading={threadLoading}
            pendingPrompt={pendingPrompt}
            onPendingPromptConsumed={() => setPendingPrompt(null)}
            onRefresh={async () => {
              if (selectedThreadId) {
                await Promise.all([refreshThread(selectedThreadId), refreshThreads(), refreshFeed()])
              }
            }}
          />
        ) : (
          <HomeFeed
            feed={feed}
            threads={threadLookup}
            onOpenThread={handleOpenThread}
            onRefresh={async () => {
              await Promise.all([refreshFeed(), refreshThreads(), refreshWatchers()])
            }}
          />
        )
      }
    />
  )
}

export default App
