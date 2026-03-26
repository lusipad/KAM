import { Badge } from '@/components/ui/badge';
import type { ProjectRecord } from '@/types/v2';
import { cn } from '@/lib/utils';

function projectDotClass(status: string) {
  if (status === 'active') return 'bg-emerald-500';
  if (status === 'paused') return 'bg-amber-500';
  if (status === 'done') return 'bg-muted-foreground/70';
  return 'bg-muted-foreground/50';
}

export function ProjectList({
  projects,
  selectedProjectId,
  onSelectProject,
  isLoading,
}: {
  projects: ProjectRecord[];
  selectedProjectId: string | null;
  onSelectProject: (projectId: string) => void;
  isLoading: boolean;
}) {
  return (
    <section>
      <div className="lite-eyebrow">PROJECTS</div>
      <div className="mt-3 space-y-2">
        {projects.map((project) => (
          <button
            key={project.id}
            type="button"
            onClick={() => onSelectProject(project.id)}
            className={cn(
              'w-full rounded-[1.2rem] border px-3 py-3 text-left transition',
              selectedProjectId === project.id
                ? 'border-primary/40 bg-primary/8 shadow-[0_12px_30px_rgba(202,99,49,0.10)]'
                : 'border-border/70 bg-background/60 hover:border-primary/30 hover:bg-primary/5',
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className={cn('mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full', projectDotClass(project.status))} />
                  <div className="truncate text-sm font-medium">{project.title}</div>
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  {project.threadCount} thread{project.threadCount === 1 ? '' : 's'}
                </div>
              </div>
              <Badge variant="outline">{project.status}</Badge>
            </div>
          </button>
        ))}

        {!projects.length && !isLoading ? (
          <div className="rounded-[1.2rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">
            No projects yet
          </div>
        ) : null}
      </div>
    </section>
  );
}
