/* eslint-disable react-refresh/only-export-components */
import { useMemo } from 'react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { GitChangedFileRecord, ThreadRunArtifactRecord } from '@/types/v2';

type PatchLineKind = 'meta' | 'context' | 'add' | 'delete';

type PatchLineRecord = {
  kind: PatchLineKind;
  content: string;
  oldNumber: number | null;
  newNumber: number | null;
};

type PatchHunkRecord = {
  header: string;
  lines: PatchLineRecord[];
};

type PatchFileRecord = {
  path: string;
  originalPath?: string;
  status: string;
  label: string;
  binary: boolean;
  hunks: PatchHunkRecord[];
};

export type RunChangeFileRecord = GitChangedFileRecord & {
  tracked?: boolean;
};

type RunChangePreviewProps = {
  changesArtifact?: ThreadRunArtifactRecord;
  patchArtifact?: ThreadRunArtifactRecord;
  selectedPath?: string | null;
  onSelectPath?: (path: string) => void;
  showSelector?: boolean;
  strictPath?: boolean;
  compact?: boolean;
  className?: string;
};

function asString(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object';
}

function statusTone(status: string) {
  if (status === 'deleted') return 'destructive';
  if (status === 'renamed' || status === 'copied') return 'secondary';
  if (status === 'added') return 'default';
  return 'outline';
}

function statusLabel(status: string, label: string) {
  if (label) return label;
  if (status === '??') return 'untracked';
  if (status.includes('R')) return 'renamed';
  if (status.includes('A')) return 'added';
  if (status.includes('D')) return 'deleted';
  if (status.includes('C')) return 'copied';
  if (status.includes('M')) return 'modified';
  return status || 'changed';
}

function readMetadataFiles(artifact?: ThreadRunArtifactRecord) {
  const files = artifact?.metadata?.files;
  if (!Array.isArray(files)) return [] as RunChangeFileRecord[];

  const rows: RunChangeFileRecord[] = [];
  files.forEach((item) => {
    if (typeof item === 'string') {
      rows.push({
        path: item,
        status: '',
        label: 'changed',
        tracked: true,
      });
      return;
    }
    if (!isRecord(item)) return;
    const path = asString(item.path);
    if (!path) return;
    const status = asString(item.status);
    rows.push({
      path,
      status,
      label: statusLabel(status, asString(item.label)),
      originalPath: asString(item.originalPath) || undefined,
      tracked: status !== '??',
    });
  });
  return rows;
}

function parseHunkHeader(header: string) {
  const match = header.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
  if (!match) {
    return { oldLine: 0, newLine: 0 };
  }
  return {
    oldLine: Number(match[1]),
    newLine: Number(match[2]),
  };
}

function normalizeDiffPath(rawPath: string) {
  if (rawPath.startsWith('a/') || rawPath.startsWith('b/')) {
    return rawPath.slice(2);
  }
  return rawPath;
}

function derivePatchStatus(lines: string[]) {
  if (lines.some((line) => line.startsWith('new file mode '))) return 'added';
  if (lines.some((line) => line.startsWith('deleted file mode '))) return 'deleted';
  if (lines.some((line) => line.startsWith('rename from '))) return 'renamed';
  if (lines.some((line) => line.startsWith('copy from '))) return 'copied';
  return 'modified';
}

function parseGitPatch(content: string) {
  const lines = content.split('\n');
  const files: PatchFileRecord[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.startsWith('diff --git ')) {
      index += 1;
      continue;
    }

    const diffHeader = line.match(/^diff --git a\/(.+?) b\/(.+)$/);
    const fallbackPath = diffHeader ? normalizeDiffPath(diffHeader[2]) : '';
    const chunk: string[] = [line];
    index += 1;

    while (index < lines.length && !lines[index].startsWith('diff --git ')) {
      chunk.push(lines[index]);
      index += 1;
    }

    let path = fallbackPath;
    let originalPath: string | undefined;
    const hunks: PatchHunkRecord[] = [];
    let currentHunk: PatchHunkRecord | null = null;
    let oldLine = 0;
    let newLine = 0;
    let binary = false;

    for (const chunkLine of chunk.slice(1)) {
      if (chunkLine.startsWith('rename from ')) {
        originalPath = chunkLine.slice('rename from '.length).trim();
        continue;
      }
      if (chunkLine.startsWith('rename to ')) {
        path = chunkLine.slice('rename to '.length).trim() || path;
        continue;
      }
      if (chunkLine.startsWith('Binary files ')) {
        binary = true;
        continue;
      }
      if (chunkLine.startsWith('--- ') || chunkLine.startsWith('+++ ')) {
        if (chunkLine.startsWith('+++ ')) {
          const nextPath = chunkLine.slice(4).trim();
          if (nextPath !== '/dev/null') {
            path = normalizeDiffPath(nextPath);
          }
        }
        continue;
      }
      if (chunkLine.startsWith('@@ ')) {
        const position = parseHunkHeader(chunkLine);
        oldLine = position.oldLine;
        newLine = position.newLine;
        currentHunk = {
          header: chunkLine,
          lines: [],
        };
        hunks.push(currentHunk);
        continue;
      }
      if (!currentHunk) {
        continue;
      }

      if (chunkLine.startsWith('+') && !chunkLine.startsWith('+++')) {
        currentHunk.lines.push({
          kind: 'add',
          content: chunkLine,
          oldNumber: null,
          newNumber: newLine,
        });
        newLine += 1;
        continue;
      }
      if (chunkLine.startsWith('-') && !chunkLine.startsWith('---')) {
        currentHunk.lines.push({
          kind: 'delete',
          content: chunkLine,
          oldNumber: oldLine,
          newNumber: null,
        });
        oldLine += 1;
        continue;
      }
      if (chunkLine.startsWith('\\')) {
        currentHunk.lines.push({
          kind: 'meta',
          content: chunkLine,
          oldNumber: null,
          newNumber: null,
        });
        continue;
      }
      currentHunk.lines.push({
        kind: 'context',
        content: chunkLine,
        oldNumber: oldLine,
        newNumber: newLine,
      });
      oldLine += 1;
      newLine += 1;
    }

    if (!path) {
      continue;
    }

    const status = derivePatchStatus(chunk);
    files.push({
      path,
      originalPath,
      status,
      label: statusLabel(status, ''),
      binary,
      hunks,
    });
  }

  return files;
}

export function collectRunChangeFiles(changesArtifact?: ThreadRunArtifactRecord, patchArtifact?: ThreadRunArtifactRecord) {
  const files = new Map<string, RunChangeFileRecord>();

  for (const item of readMetadataFiles(changesArtifact)) {
    files.set(item.path, item);
  }

  for (const patchFile of parseGitPatch(patchArtifact?.content || '')) {
    const current = files.get(patchFile.path);
    files.set(patchFile.path, {
      path: patchFile.path,
      status: current?.status || patchFile.status,
      label: current?.label || patchFile.label,
      originalPath: current?.originalPath || patchFile.originalPath,
      tracked: current?.tracked ?? !patchFile.binary,
    });
  }

  return Array.from(files.values());
}

function flattenPatchLines(file: PatchFileRecord, compact: boolean) {
  const maxLines = compact ? 80 : 240;
  const flattened: Array<PatchLineRecord & { id: string }> = [];

  file.hunks.forEach((hunk, hunkIndex) => {
    flattened.push({
      id: `${file.path}-header-${hunkIndex}`,
      kind: 'meta',
      content: hunk.header,
      oldNumber: null,
      newNumber: null,
    });
    hunk.lines.forEach((line, lineIndex) => {
      flattened.push({
        ...line,
        id: `${file.path}-${hunkIndex}-${lineIndex}`,
      });
    });
  });

  return flattened.slice(0, maxLines);
}

function lineTone(kind: PatchLineKind) {
  if (kind === 'add') return 'bg-emerald-500/8 text-emerald-300';
  if (kind === 'delete') return 'bg-rose-500/8 text-rose-300';
  if (kind === 'meta') return 'bg-amber-500/8 text-amber-200';
  return 'text-muted-foreground';
}

function renderLineNumber(value: number | null) {
  return value == null ? '' : String(value);
}

export function RunChangePreview({
  changesArtifact,
  patchArtifact,
  selectedPath,
  onSelectPath,
  showSelector = true,
  strictPath = false,
  compact = false,
  className,
}: RunChangePreviewProps) {
  const files = useMemo(() => collectRunChangeFiles(changesArtifact, patchArtifact), [changesArtifact, patchArtifact]);
  const patchFiles = useMemo(() => parseGitPatch(patchArtifact?.content || ''), [patchArtifact?.content]);
  const fileMap = useMemo(() => new Map(files.map((file) => [file.path, file])), [files]);
  const patchMap = useMemo(() => new Map(patchFiles.map((file) => [file.path, file])), [patchFiles]);

  const hasRequestedPath = !!selectedPath && fileMap.has(selectedPath);
  const activePath = strictPath
    ? (selectedPath || null)
    : (hasRequestedPath ? selectedPath : files[0]?.path || null);
  const activeFile = activePath ? fileMap.get(activePath) || null : files[0] || null;
  const activePatch = activePath ? patchMap.get(activePath) || null : null;
  const flattenedLines = activePatch ? flattenPatchLines(activePatch, compact) : [];

  if (!files.length) {
    return (
      <div className={cn('rounded-xl border border-border/50 bg-background/80 px-3 py-3 text-xs text-muted-foreground', className)}>
        这个 Run 还没有可预览的文件级变更。
      </div>
    );
  }

  return (
    <div className={cn('space-y-3', className)}>
      {showSelector ? (
        <div className="flex flex-wrap gap-2">
          {files.map((file) => (
            <button
              key={file.path}
              type="button"
              onClick={() => onSelectPath?.(file.path)}
              className={cn(
                'rounded-full border px-3 py-1 text-left text-[11px] transition',
                activePath === file.path ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/60 bg-background/80 text-muted-foreground',
              )}
            >
              <span className="font-mono">{file.path}</span>
            </button>
          ))}
        </div>
      ) : null}

      {strictPath && selectedPath && !hasRequestedPath ? (
        <div className="rounded-xl border border-dashed border-border/60 bg-background/80 px-3 py-4 text-xs text-muted-foreground">
          这个方案没有改动 <span className="font-mono text-foreground">{selectedPath}</span>。
        </div>
      ) : activeFile ? (
        <>
          <div className="rounded-xl border border-border/50 bg-background/80 px-3 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="font-mono text-xs text-foreground">{activeFile.path}</div>
              <Badge variant={statusTone(activeFile.label || activeFile.status) as never}>{activeFile.label || activeFile.status || 'changed'}</Badge>
              {activeFile.tracked === false ? <Badge variant="outline">untracked</Badge> : null}
            </div>
            {activeFile.originalPath ? (
              <div className="mt-2 text-[11px] text-muted-foreground">
                from <span className="font-mono">{activeFile.originalPath}</span>
              </div>
            ) : null}
          </div>

          {activePatch?.binary ? (
            <div className="rounded-xl border border-border/50 bg-background/80 px-3 py-4 text-xs text-muted-foreground">
              这是 binary patch，当前只展示文件级摘要。
            </div>
          ) : flattenedLines.length ? (
            <div className="overflow-hidden rounded-xl border border-border/50 bg-slate-950/70">
              <div className="grid grid-cols-[56px_56px_minmax(0,1fr)] border-b border-white/10 bg-slate-900/80 px-3 py-2 text-[11px] uppercase tracking-wide text-slate-400">
                <div>Old</div>
                <div>New</div>
                <div>Patch</div>
              </div>
              <div className={cn('overflow-auto font-mono text-[11px] leading-6', compact ? 'max-h-[260px]' : 'max-h-[520px]')}>
                {flattenedLines.map((line) => (
                  <div key={line.id} className={cn('grid grid-cols-[56px_56px_minmax(0,1fr)] px-3', lineTone(line.kind))}>
                    <div className="select-none pr-2 text-right text-slate-500">{renderLineNumber(line.oldNumber)}</div>
                    <div className="select-none pr-2 text-right text-slate-500">{renderLineNumber(line.newNumber)}</div>
                    <pre className="overflow-x-auto whitespace-pre-wrap break-words">{line.content || ' '}</pre>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-border/50 bg-background/80 px-3 py-4 text-xs text-muted-foreground">
              当前文件没有 tracked patch，通常意味着它是 untracked 文件，或只有 summary 没有 diff。
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
