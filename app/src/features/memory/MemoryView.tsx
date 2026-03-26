import { ArrowLeft, Search } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import type { DecisionRecord, ProjectLearningRecord, ProjectRecord, UserPreferenceRecord } from '@/types/v2';

function MemorySearchBadges({
  item,
}: {
  item: UserPreferenceRecord | DecisionRecord | ProjectLearningRecord;
}) {
  const lexical = typeof item.searchScore === 'number' ? item.searchScore.toFixed(3) : null;
  const semantic = typeof item.semanticScore === 'number' ? item.semanticScore.toFixed(3) : null;
  if (!item.matchType && !lexical && !semantic) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {item.matchType ? <Badge variant="outline">{item.matchType}</Badge> : null}
      {lexical ? <Badge variant="outline">lexical {lexical}</Badge> : null}
      {semantic ? <Badge variant="outline">semantic {semantic}</Badge> : null}
    </div>
  );
}

function SectionLabel({ children }: { children: string }) {
  return <div className="lite-eyebrow">{children}</div>;
}

export function MemoryView({
  selectedProject,
  selectedProjectId,
  memoryQuery,
  onMemoryQueryChange,
  onBack,
  preferences,
  decisions,
  learnings,
  preferenceForm,
  decisionForm,
  learningForm,
  preferenceDrafts,
  decisionDrafts,
  learningDrafts,
  onPreferenceFormChange,
  onDecisionFormChange,
  onLearningFormChange,
  onPreferenceDraftChange,
  onDecisionDraftChange,
  onLearningDraftChange,
  onCreatePreference,
  onCreateDecision,
  onCreateLearning,
  onSavePreference,
  onSaveDecision,
  onSaveLearning,
  isLoading,
}: {
  selectedProject: ProjectRecord | null;
  selectedProjectId: string | null;
  memoryQuery: string;
  onMemoryQueryChange: (value: string) => void;
  onBack: () => void;
  preferences: UserPreferenceRecord[];
  decisions: DecisionRecord[];
  learnings: ProjectLearningRecord[];
  preferenceForm: { category: string; key: string; value: string };
  decisionForm: { question: string; decision: string; reasoning: string };
  learningForm: { content: string };
  preferenceDrafts: Record<string, string>;
  decisionDrafts: Record<string, { question: string; decision: string; reasoning: string }>;
  learningDrafts: Record<string, string>;
  onPreferenceFormChange: (next: { category: string; key: string; value: string }) => void;
  onDecisionFormChange: (next: { question: string; decision: string; reasoning: string }) => void;
  onLearningFormChange: (next: { content: string }) => void;
  onPreferenceDraftChange: (id: string, value: string) => void;
  onDecisionDraftChange: (id: string, next: { question: string; decision: string; reasoning: string }) => void;
  onLearningDraftChange: (id: string, value: string) => void;
  onCreatePreference: () => void;
  onCreateDecision: () => void;
  onCreateLearning: () => void;
  onSavePreference: (id: string) => void;
  onSaveDecision: (id: string) => void;
  onSaveLearning: (id: string) => void;
  isLoading: boolean;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/70 px-6 py-5">
        <div className="flex items-center gap-3">
          <Button type="button" variant="ghost" size="icon-sm" onClick={onBack} aria-label="返回工作区">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <div className="font-display text-xl font-semibold">Memory</div>
            <div className="mt-1 text-sm text-muted-foreground">
              {selectedProject ? `当前聚焦：${selectedProject.title}` : '跨项目偏好、决策与经验沉淀'}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">{preferences.length} Preferences</Badge>
          <Badge variant="outline">{decisions.length} Decisions</Badge>
          <Badge variant="outline">{learnings.length} Learnings</Badge>
        </div>
      </div>

      <div className="border-b border-border/70 px-6 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={memoryQuery}
              onChange={(event) => onMemoryQueryChange(event.target.value)}
              placeholder="搜索偏好、决策与经验..."
              className="pl-9"
            />
          </div>
          <div className="text-sm text-muted-foreground">
            {selectedProject ? '正在查看当前项目的决策与经验，偏好保持全局视图。' : '当前展示全局记忆。'}
          </div>
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="grid gap-4 px-6 py-6 xl:grid-cols-3">
          <section className="lite-panel rounded-[1.5rem] p-4">
            <SectionLabel>PREFERENCES</SectionLabel>
            <div className="mt-4 space-y-3">
              <Input value={preferenceForm.category} onChange={(event) => onPreferenceFormChange({ ...preferenceForm, category: event.target.value })} placeholder="category" />
              <Input value={preferenceForm.key} onChange={(event) => onPreferenceFormChange({ ...preferenceForm, key: event.target.value })} placeholder="key" />
              <Textarea value={preferenceForm.value} onChange={(event) => onPreferenceFormChange({ ...preferenceForm, value: event.target.value })} placeholder="例如：优先用 pnpm / 回复保持简洁" className="min-h-[96px]" />
              <Button type="button" className="w-full" onClick={onCreatePreference}>记录偏好</Button>
            </div>
            <div className="mt-5 space-y-3">
              {preferences.map((item) => (
                <div key={item.id} className="rounded-[1.1rem] border border-border/70 bg-background/70 px-3 py-3">
                  <div className="flex items-center gap-2 text-sm">
                    <Badge variant="outline">{item.category}</Badge>
                    <span className="font-medium">{item.key}</span>
                  </div>
                  <MemorySearchBadges item={item} />
                  <Textarea value={preferenceDrafts[item.id] ?? item.value} onChange={(event) => onPreferenceDraftChange(item.id, event.target.value)} className="mt-3 min-h-[88px]" />
                  <Button type="button" size="sm" className="mt-3" onClick={() => onSavePreference(item.id)}>保存</Button>
                </div>
              ))}
              {!preferences.length && !isLoading ? <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">还没有记录偏好。</div> : null}
            </div>
          </section>

          <section className="lite-panel rounded-[1.5rem] p-4">
            <SectionLabel>DECISIONS</SectionLabel>
            <div className="mt-4 space-y-3">
              <Input value={decisionForm.question} onChange={(event) => onDecisionFormChange({ ...decisionForm, question: event.target.value })} placeholder="问题" disabled={!selectedProjectId} />
              <Input value={decisionForm.decision} onChange={(event) => onDecisionFormChange({ ...decisionForm, decision: event.target.value })} placeholder="决策" disabled={!selectedProjectId} />
              <Textarea value={decisionForm.reasoning} onChange={(event) => onDecisionFormChange({ ...decisionForm, reasoning: event.target.value })} placeholder={selectedProjectId ? '为什么这么决定' : '选择项目后可记录决策'} className="min-h-[96px]" disabled={!selectedProjectId} />
              <Button type="button" className="w-full" onClick={onCreateDecision} disabled={!selectedProjectId}>记录决策</Button>
            </div>
            <div className="mt-5 space-y-3">
              {decisions.map((item) => {
                const draft = decisionDrafts[item.id] || { question: item.question, decision: item.decision, reasoning: item.reasoning || '' };
                return (
                  <div key={item.id} className="rounded-[1.1rem] border border-border/70 bg-background/70 px-3 py-3">
                    <MemorySearchBadges item={item} />
                    <Input value={draft.question} onChange={(event) => onDecisionDraftChange(item.id, { ...draft, question: event.target.value })} className="mt-3" />
                    <Input value={draft.decision} onChange={(event) => onDecisionDraftChange(item.id, { ...draft, decision: event.target.value })} className="mt-3" />
                    <Textarea value={draft.reasoning} onChange={(event) => onDecisionDraftChange(item.id, { ...draft, reasoning: event.target.value })} className="mt-3 min-h-[88px]" />
                    <Button type="button" size="sm" className="mt-3" onClick={() => onSaveDecision(item.id)}>保存</Button>
                  </div>
                );
              })}
              {!decisions.length && !isLoading ? <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">还没有记录决策。</div> : null}
            </div>
          </section>

          <section className="lite-panel rounded-[1.5rem] p-4">
            <SectionLabel>LEARNINGS</SectionLabel>
            <div className="mt-4 space-y-3">
              <Textarea value={learningForm.content} onChange={(event) => onLearningFormChange({ content: event.target.value })} placeholder={selectedProjectId ? '记录这次工作沉淀出的经验' : '选择项目后可记录经验'} className="min-h-[120px]" disabled={!selectedProjectId} />
              <Button type="button" className="w-full" onClick={onCreateLearning} disabled={!selectedProjectId}>记录经验</Button>
            </div>
            <div className="mt-5 space-y-3">
              {learnings.map((item) => (
                <div key={item.id} className="rounded-[1.1rem] border border-border/70 bg-background/70 px-3 py-3">
                  <MemorySearchBadges item={item} />
                  <Textarea value={learningDrafts[item.id] ?? item.content} onChange={(event) => onLearningDraftChange(item.id, event.target.value)} className="mt-3 min-h-[96px]" />
                  <Button type="button" size="sm" className="mt-3" onClick={() => onSaveLearning(item.id)}>保存</Button>
                </div>
              ))}
              {!learnings.length && !isLoading ? <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">还没有记录经验。</div> : null}
            </div>
          </section>
        </div>
      </ScrollArea>
    </div>
  );
}
