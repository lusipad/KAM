import { Brain, Plus, Settings2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { ProjectList } from '@/features/projects/ProjectList';
import { ThreadList } from '@/features/threads/ThreadList';
import type { ProjectRecord, ProjectThread } from '@/types/v2';

export function Sidebar({
  projects,
  selectedProjectId,
  selectedProject,
  threads,
  selectedThreadId,
  workspaceMode,
  isLoading,
  onSelectProject,
  onSelectThread,
  onCreateProject,
  onOpenMemory,
  onOpenSettings,
  onOpenWorkspace,
}: {
  projects: ProjectRecord[];
  selectedProjectId: string | null;
  selectedProject: ProjectRecord | null;
  threads: ProjectThread[];
  selectedThreadId: string | null;
  workspaceMode: 'workspace' | 'memory';
  isLoading: boolean;
  onSelectProject: (projectId: string) => void;
  onSelectThread: (threadId: string) => void;
  onCreateProject: () => void;
  onOpenMemory: () => void;
  onOpenSettings: () => void;
  onOpenWorkspace: () => void;
}) {
  return (
    <aside className="lite-panel flex h-full min-h-0 flex-col rounded-[1.9rem] p-4 lg:p-5">
      <button
        type="button"
        onClick={onOpenWorkspace}
        className="flex items-center gap-3 rounded-[1.3rem] px-2 py-2 text-left transition hover:bg-accent/60"
      >
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 font-display text-sm font-semibold text-primary">
          K
        </div>
        <div className="font-display text-xl font-semibold">KAM</div>
      </button>

      <ScrollArea className="mt-6 min-h-0 flex-1 pr-2">
        <ProjectList
          projects={projects}
          selectedProjectId={selectedProjectId}
          onSelectProject={onSelectProject}
          isLoading={isLoading}
        />
        {selectedProject ? (
          <ThreadList threads={threads} selectedThreadId={selectedThreadId} onSelectThread={onSelectThread} />
        ) : null}
      </ScrollArea>

      <Separator className="my-4" />

      <div className="space-y-2">
        <Button type="button" variant="ghost" className="w-full justify-start rounded-[1rem]" onClick={onCreateProject}>
          <Plus className="h-4 w-4" />
          New project
        </Button>
        <Button
          type="button"
          variant={workspaceMode === 'memory' ? 'secondary' : 'ghost'}
          className="w-full justify-start rounded-[1rem]"
          onClick={onOpenMemory}
        >
          <Brain className="h-4 w-4" />
          Memory
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="w-full justify-start rounded-[1rem]"
          onClick={onOpenSettings}
          aria-label="外观设置"
        >
          <Settings2 className="h-4 w-4" />
          外观设置
        </Button>
      </div>
    </aside>
  );
}
