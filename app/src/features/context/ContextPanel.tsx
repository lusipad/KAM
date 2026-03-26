import { Archive, ArrowLeft, File, Folder, Pin, Plus, RefreshCcw, Save, Trash2 } from 'lucide-react';

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import type { ConversationRun, ProjectFileTreeRecord, ProjectRecord, ProjectResourceRecord } from '@/types/v2';
import { cn } from '@/lib/utils';

function formatAgentLabel(agent: string) {
  if (agent === 'codex') return 'Codex';
  if (agent === 'claude-code') return 'Claude Code';
  if (agent === 'custom') return 'Custom';
  return agent || 'Agent';
}

function splitCommands(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
}

function runStatusMeta(status: string) {
  if (status === 'running' || status === 'checking') return { label: status === 'checking' ? 'Checking' : 'Running', toneClass: 'text-sky-500', iconClass: 'animate-spin' };
  if (status === 'passed') return { label: 'Passed', toneClass: 'text-emerald-500', iconClass: '' };
  if (status === 'failed') return { label: 'Failed', toneClass: 'text-rose-500', iconClass: '' };
  if (status === 'cancelled') return { label: 'Cancelled', toneClass: 'text-muted-foreground', iconClass: '' };
  return { label: 'Pending', toneClass: 'text-muted-foreground', iconClass: '' };
}

function ContextSummaryLine({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn('max-w-[62%] text-right', mono && 'font-mono text-xs')}>{value}</span>
    </div>
  );
}

function ResourceRow({ resource, onDelete }: { resource: ProjectResourceRecord; onDelete: () => void }) {
  const Icon =
    resource.type === 'repo-path' || resource.type === 'path'
      ? Folder
      : resource.type === 'file'
        ? File
        : Pin;

  return (
    <div className="flex items-start gap-3 rounded-[1.1rem] border border-border/70 bg-background/70 px-3 py-3">
      <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-xl bg-secondary text-muted-foreground">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <div className="truncate text-sm font-medium">{resource.title || resource.uri}</div>
          {resource.pinned ? <Badge variant="outline">Pinned</Badge> : null}
        </div>
        <div className="mt-1 truncate text-xs text-muted-foreground">{resource.uri}</div>
      </div>
      <Button type="button" size="icon-sm" variant="ghost" onClick={onDelete} aria-label="删除资源">
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}

export function ContextPanel({
  open,
  onOpenChange,
  selectedProject,
  projectForm,
  onProjectFormChange,
  showProjectEditor,
  onProjectEditorToggle,
  pinnedResources,
  resourceForm,
  onResourceFormChange,
  showResourceComposer,
  onResourceComposerToggle,
  activeRuns,
  fileTree,
  fileTreeQuery,
  onFileTreeQueryChange,
  isFilesLoading,
  onRefreshFiles,
  onOpenRun,
  onSaveProject,
  onArchiveProject,
  onAddResource,
  onDeleteResource,
  onLoadPath,
  onPinRepoEntry,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedProject: ProjectRecord | null;
  projectForm: { title: string; description: string; repoPath: string; status: string; checkCommands: string };
  onProjectFormChange: (next: { title: string; description: string; repoPath: string; status: string; checkCommands: string }) => void;
  showProjectEditor: boolean;
  onProjectEditorToggle: (open: boolean) => void;
  pinnedResources: ProjectResourceRecord[];
  resourceForm: { type: string; title: string; uri: string; pinned: boolean };
  onResourceFormChange: (next: { type: string; title: string; uri: string; pinned: boolean }) => void;
  showResourceComposer: boolean;
  onResourceComposerToggle: (open: boolean) => void;
  activeRuns: ConversationRun[];
  fileTree: ProjectFileTreeRecord | null;
  fileTreeQuery: string;
  onFileTreeQueryChange: (value: string) => void;
  isFilesLoading: boolean;
  onRefreshFiles: () => void;
  onOpenRun: (runId: string, artifactType?: string) => void;
  onSaveProject: () => void;
  onArchiveProject: () => void;
  onAddResource: () => void;
  onDeleteResource: (resourceId: string) => void;
  onLoadPath: (path: string) => void;
  onPinRepoEntry: (path: string, name: string) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-[380px]">
        <SheetHeader className="border-b border-border/70 px-5 py-5">
          <SheetTitle>{selectedProject?.title || 'Context'}</SheetTitle>
          <SheetDescription>{selectedProject?.repoPath || '当前项目的设置、资源与运行态'}</SheetDescription>
        </SheetHeader>

        {!selectedProject ? (
          <div className="px-5 py-6 text-sm text-muted-foreground">先选中一个项目，再打开 Context。</div>
        ) : (
          <ScrollArea className="min-h-0 flex-1">
            <div className="px-5 py-4">
              <Accordion type="multiple" defaultValue={['settings', 'resources', 'runs', 'files']} className="w-full">
                <AccordionItem value="settings">
                  <AccordionTrigger>SETTINGS</AccordionTrigger>
                  <AccordionContent className="space-y-4">
                    <ContextSummaryLine label="Repo" value={projectForm.repoPath || '未设置'} mono />
                    <ContextSummaryLine label="Status" value={projectForm.status} />
                    <ContextSummaryLine label="Checks" value={splitCommands(projectForm.checkCommands).length ? splitCommands(projectForm.checkCommands).join(', ') : '未设置'} />

                    {!showProjectEditor ? (
                      <Button type="button" variant="outline" size="sm" onClick={() => onProjectEditorToggle(true)}>Edit settings</Button>
                    ) : (
                      <div className="space-y-3 rounded-[1.1rem] border border-border/70 bg-background/70 p-3">
                        <Input value={projectForm.title} onChange={(event) => onProjectFormChange({ ...projectForm, title: event.target.value })} placeholder="项目标题" />
                        <Input value={projectForm.repoPath} onChange={(event) => onProjectFormChange({ ...projectForm, repoPath: event.target.value })} placeholder="仓库路径" />
                        <select value={projectForm.status} onChange={(event) => onProjectFormChange({ ...projectForm, status: event.target.value })} className="h-10 rounded-xl border border-input bg-background px-3 text-sm">
                          <option value="active">active</option>
                          <option value="paused">paused</option>
                          <option value="done">done</option>
                        </select>
                        <Textarea value={projectForm.description} onChange={(event) => onProjectFormChange({ ...projectForm, description: event.target.value })} placeholder="项目描述" className="min-h-[100px]" />
                        <Textarea value={projectForm.checkCommands} onChange={(event) => onProjectFormChange({ ...projectForm, checkCommands: event.target.value })} placeholder="每行一个检查命令" className="min-h-[100px] font-mono text-xs" />
                        <div className="flex flex-wrap gap-2">
                          <Button type="button" size="sm" onClick={onSaveProject}><Save className="h-4 w-4" />保存</Button>
                          <Button type="button" size="sm" variant="outline" onClick={() => onProjectEditorToggle(false)}>收起</Button>
                          <Button type="button" size="sm" variant="outline" onClick={onArchiveProject}><Archive className="h-4 w-4" />归档</Button>
                        </div>
                      </div>
                    )}
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem value="resources">
                  <AccordionTrigger>PINNED RESOURCES</AccordionTrigger>
                  <AccordionContent className="space-y-3">
                    {pinnedResources.map((resource) => (
                      <ResourceRow key={resource.id} resource={resource} onDelete={() => onDeleteResource(resource.id)} />
                    ))}
                    {!pinnedResources.length ? <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">还没有 pinned resource。</div> : null}

                    {!showResourceComposer ? (
                      <Button type="button" size="sm" variant="outline" onClick={() => onResourceComposerToggle(true)}><Plus className="h-4 w-4" />Add resource</Button>
                    ) : (
                      <div className="space-y-3 rounded-[1.1rem] border border-border/70 bg-background/70 p-3">
                        <Select value={resourceForm.type} onValueChange={(value) => onResourceFormChange({ ...resourceForm, type: value })}>
                          <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="note">note</SelectItem>
                            <SelectItem value="url">url</SelectItem>
                            <SelectItem value="file">file</SelectItem>
                            <SelectItem value="repo-path">repo-path</SelectItem>
                          </SelectContent>
                        </Select>
                        <Input value={resourceForm.title} onChange={(event) => onResourceFormChange({ ...resourceForm, title: event.target.value })} placeholder="标题（可选）" />
                        <Textarea value={resourceForm.uri} onChange={(event) => onResourceFormChange({ ...resourceForm, uri: event.target.value })} placeholder="URL / 路径 / 备注" className="min-h-[96px]" />
                        <div className="flex flex-wrap gap-2">
                          <Button type="button" size="sm" onClick={onAddResource}>保存资源</Button>
                          <Button type="button" size="sm" variant="outline" onClick={() => onResourceComposerToggle(false)}>取消</Button>
                        </div>
                      </div>
                    )}
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem value="runs">
                  <AccordionTrigger>ACTIVE RUNS</AccordionTrigger>
                  <AccordionContent className="space-y-2">
                    {activeRuns.length ? activeRuns.map((run) => (
                      <button key={run.id} type="button" onClick={() => onOpenRun(run.id, 'summary')} className="flex w-full items-center justify-between gap-3 rounded-[1rem] border border-border/70 bg-background/70 px-3 py-3 text-left transition hover:border-primary/40 hover:bg-primary/5">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium">{typeof run.metadata?.compareLabel === 'string' ? run.metadata.compareLabel : `Run ${run.id.slice(0, 6)}`}</div>
                          <div className="mt-1 truncate text-xs text-muted-foreground">{formatAgentLabel(run.agent)}</div>
                        </div>
                        <div className={cn('shrink-0 text-xs', runStatusMeta(run.status).toneClass)}>{runStatusMeta(run.status).label}</div>
                      </button>
                    )) : <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">当前没有活跃 run。</div>}
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem value="files">
                  <AccordionTrigger>FILE TREE</AccordionTrigger>
                  <AccordionContent className="space-y-3">
                    {!selectedProject.repoPath ? (
                      <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">当前项目还没有关联仓库路径。</div>
                    ) : (
                      <>
                        <div className="flex gap-2">
                          <Input value={fileTreeQuery} onChange={(event) => onFileTreeQueryChange(event.target.value)} placeholder="搜索文件" />
                          <Button type="button" size="icon-sm" variant="outline" onClick={onRefreshFiles} aria-label="刷新文件树">
                            <RefreshCcw className={cn('h-4 w-4', isFilesLoading && 'animate-spin')} />
                          </Button>
                        </div>
                        {fileTree?.parentPath !== undefined && fileTree?.parentPath !== null ? (
                          <Button type="button" size="sm" variant="ghost" onClick={() => onLoadPath(fileTree.parentPath || '')}>
                            <ArrowLeft className="h-4 w-4" />
                            返回上一级
                          </Button>
                        ) : null}
                        <div className="rounded-[1.1rem] border border-border/70 bg-background/70">
                          <div className="border-b border-border/70 px-3 py-2 text-xs text-muted-foreground">{fileTree?.currentPath || selectedProject.repoPath}</div>
                          <div className="divide-y divide-border/60">
                            {(fileTree?.entries || []).map((entry) => (
                              <div key={entry.path} className="flex items-center gap-3 px-3 py-3">
                                <button type="button" className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={() => { if (entry.type === 'dir') onLoadPath(entry.path); }}>
                                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary text-muted-foreground">{entry.type === 'dir' ? <Folder className="h-4 w-4" /> : <File className="h-4 w-4" />}</div>
                                  <div className="min-w-0">
                                    <div className="truncate text-sm">{entry.name}</div>
                                    <div className="truncate text-xs text-muted-foreground">{entry.path}</div>
                                  </div>
                                </button>
                                <Button type="button" size="icon-sm" variant="ghost" onClick={() => onPinRepoEntry(entry.path, entry.name)} aria-label="固定到资源">
                                  <Pin className="h-4 w-4" />
                                </Button>
                              </div>
                            ))}
                            {!fileTree?.entries.length ? <div className="px-3 py-4 text-sm text-muted-foreground">{isFilesLoading ? '文件树加载中...' : '当前路径没有匹配项。'}</div> : null}
                          </div>
                        </div>
                      </>
                    )}
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
          </ScrollArea>
        )}
      </SheetContent>
    </Sheet>
  );
}
