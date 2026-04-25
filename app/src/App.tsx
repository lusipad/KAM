import { useCallback, useMemo, useRef, useState } from 'react'

import { FrontDoorPanel } from '@/features/operator/FrontDoorPanel'
import { OperatorPanel } from '@/features/operator/OperatorPanel'
import { TaskPanel } from '@/features/tasks/TaskPanel'
import { TaskSidebar } from '@/features/tasks/TaskSidebar'
import { TaskWorkbench } from '@/features/tasks/TaskWorkbench'
import { useOperator } from '@/hooks/useOperator'
import { useTaskSession } from '@/hooks/useTaskSession'
import { useTasks } from '@/hooks/useTasks'
import { useToast } from '@/hooks/useToast'
import { AppShell } from '@/layout/AppShell'

function EmptyTaskState({
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
      <div className="empty-icon">T</div>
      <div className="empty-title">先创建一张真实任务</div>
      <div className="empty-copy">写清楚你要推进的目标。创建后，KAM 才能围绕 refs、snapshot、runs 和后续计划继续工作。</div>
      <div className="empty-composer">
        <textarea
          className="task-empty-textarea"
          placeholder="例如：把首页改成用户能一眼看懂当前状态和下一步的界面"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <button type="button" className="button-primary task-empty-button" disabled={isBusy || !value.trim()} onClick={onSubmit}>
          创建任务
        </button>
      </div>
    </div>
  )
}

function App() {
  const { toasts, pushToast, onError } = useToast()

  const {
    tasks,
    selectedTaskId,
    setSelectedTaskId,
    includeArchived,
    setIncludeArchived,
    taskPrompt,
    setTaskPrompt,
    creatingTask,
    refreshTasks,
    handleCreateTask,
  } = useTasks({ pushToast, onError })

  const refreshOperatorControlRef = useRef<((taskId?: string | null) => Promise<unknown>) | null>(null)
  const handleRefreshOperatorControl: (taskId?: string | null) => Promise<unknown> = useCallback(
    async (taskId) => { await refreshOperatorControlRef.current?.(taskId) },
    [],
  )

  const {
    task,
    taskDraft,
    setTaskDraft,
    loading,
    artifacts,
    selectedRunId,
    setSelectedRunId,
    runPrompt,
    setRunPrompt,
    runAgent,
    setRunAgent,
    refDraft,
    setRefDraft,
    dependencyDraft,
    setDependencyDraft,
    snapshotFocus,
    setSnapshotFocus,
    plannedTasks,
    planSuggestions,
    creatingRun,
    addingRef,
    creatingSnapshot,
    creatingCompare,
    creatingPlan,
    addingDependency,
    savingTask,
    taskBlocked,
    selectedRunLabel,
    refreshTask,
    handleSaveTask,
    handleAddRef,
    handleDeleteRef,
    handleAddDependency,
    handleDeleteDependency,
    handleCreateSnapshot,
    handleCreateRun,
    handleCreateCompare,
    handleCreatePlan,
    handleOpenPlannedTask,
    handleRunPlannedTask,
    handleAdoptRun,
    handleRetryRun,
    handleCancelRun,
    handleArchiveTask,
  } = useTaskSession({
    selectedTaskId,
    setSelectedTaskId,
    refreshTasks,
    pushToast,
    onError,
    refreshOperatorControl: handleRefreshOperatorControl,
  })

  const {
    operatorControl,
    operatorActionPending,
    refreshingOperatorControl,
    issueMonitorDraft,
    setIssueMonitorDraft,
    issueMonitorPending,
    continueDecision,
    refreshOperatorControl,
    handleOperatorAction,
    handleSaveIssueMonitor,
    handleRunIssueMonitor,
    handleDeleteIssueMonitor,
  } = useOperator({
    selectedTaskId,
    setSelectedTaskId,
    refreshTasks,
    refreshTask,
    setSelectedRunId,
    pushToast,
    onError,
    taskDependencyReady: task?.dependencyState?.ready,
    taskDependencySummary: task?.dependencyState?.summary,
    taskUpdatedAt: task?.updatedAt,
  })

  // Wire the ref bridge after both hooks are initialized
  refreshOperatorControlRef.current = refreshOperatorControl

  const [panelOpen, setPanelOpen] = useState(true)

  const breadcrumb = useMemo(() => (task ? `Tasks / ${task.title}` : 'Tasks'), [task])

  return (
    <AppShell
      sidebar={
        <TaskSidebar
          tasks={tasks}
          activeTaskId={selectedTaskId}
          includeArchived={includeArchived}
          onSelectTask={setSelectedTaskId}
          onCreateTask={() => setSelectedTaskId(null)}
          onToggleArchived={() => setIncludeArchived((current) => !current)}
        />
      }
      breadcrumb={breadcrumb}
      memoryOpen={panelOpen}
      onToggleMemory={() => setPanelOpen((current) => !current)}
      panelToggleLabel="详情"
      toasts={toasts}
      panel={
        <TaskPanel
          artifacts={artifacts}
          snapshots={task?.snapshots ?? []}
          reviews={task?.reviews ?? []}
          selectedRunLabel={selectedRunLabel}
        />
      }
      main={
        <div className="task-main-shell">
          <FrontDoorPanel
            controlPlane={operatorControl}
            tasksCount={tasks.length}
            actionPending={operatorActionPending}
            onAction={(action) => {
              void handleOperatorAction(action)
            }}
            onOpenTask={setSelectedTaskId}
            onCreateTask={() => setSelectedTaskId(null)}
          />

          <OperatorPanel
            controlPlane={operatorControl}
            actionPending={operatorActionPending}
            issueMonitorDraft={issueMonitorDraft}
            issueMonitorPending={issueMonitorPending}
            refreshing={refreshingOperatorControl}
            selectedTaskBlockedReason={taskBlocked ? task?.dependencyState?.summary ?? '当前任务仍被依赖阻塞。' : null}
            onRefresh={() => {
              void refreshOperatorControl()
            }}
            onAction={(action) => {
              void handleOperatorAction(action)
            }}
            onIssueMonitorDraftChange={setIssueMonitorDraft}
            onSaveIssueMonitor={() => {
              void handleSaveIssueMonitor()
            }}
            onRunIssueMonitor={(repo) => {
              void handleRunIssueMonitor(repo)
            }}
            onDeleteIssueMonitor={(repo) => {
              void handleDeleteIssueMonitor(repo)
            }}
            onSelectTask={setSelectedTaskId}
          />

          {selectedTaskId ? (
            <>
              <div className="task-main-actions">
                <button type="button" className="button-secondary" onClick={() => setSelectedTaskId(null)}>
                  新建任务
                </button>
                {task ? (
                  <button type="button" className="button-secondary" onClick={handleArchiveTask}>
                    归档任务
                  </button>
                ) : null}
              </div>
              <TaskWorkbench
                task={task}
                taskDraft={taskDraft}
                loading={loading}
                runPrompt={runPrompt}
                runAgent={runAgent}
                refDraft={refDraft}
                dependencyDraft={dependencyDraft}
                snapshotFocus={snapshotFocus}
                selectedRunId={selectedRunId}
                creatingRun={creatingRun}
                addingRef={addingRef}
                addingDependency={addingDependency}
                creatingSnapshot={creatingSnapshot}
                creatingCompare={creatingCompare}
                creatingPlan={creatingPlan}
                continueDecision={continueDecision}
                savingTask={savingTask}
                taskBlocked={taskBlocked}
                plannedTasks={plannedTasks}
                planSuggestions={planSuggestions}
                onRunPromptChange={setRunPrompt}
                onRunAgentChange={setRunAgent}
                onTaskDraftChange={setTaskDraft}
                onSaveTask={handleSaveTask}
                onCreatePlan={handleCreatePlan}
                onRunRecommendedTask={() => {
                  if (task) {
                    void handleRunPlannedTask(task)
                  }
                }}
                onCreateRun={handleCreateRun}
                onRefDraftChange={setRefDraft}
                onAddRef={handleAddRef}
                onDeleteRef={handleDeleteRef}
                onDependencyDraftChange={setDependencyDraft}
                onAddDependency={handleAddDependency}
                onDeleteDependency={handleDeleteDependency}
                onSnapshotFocusChange={setSnapshotFocus}
                onCreateSnapshot={handleCreateSnapshot}
                onCreateCompare={handleCreateCompare}
                onSelectRun={(runId) => {
                  setSelectedRunId(runId)
                  setPanelOpen(true)
                }}
                onOpenPlannedTask={handleOpenPlannedTask}
                onRunPlannedTask={handleRunPlannedTask}
                onAdoptRun={handleAdoptRun}
                onRetryRun={handleRetryRun}
                onCancelRun={handleCancelRun}
              />
            </>
          ) : (
            <EmptyTaskState value={taskPrompt} onChange={setTaskPrompt} onSubmit={handleCreateTask} isBusy={creatingTask} />
          )}
        </div>
      }
    />
  )
}

export default App
