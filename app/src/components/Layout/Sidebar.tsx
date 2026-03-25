import { useState } from 'react';
import { ArrowRight, Bot, Compass, FolderInput, GitCompareArrows, Settings2, Sparkles, Workflow } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SettingsPanel } from '@/components/Settings/SettingsPanel';
import { cn } from '@/lib/utils';

const focusAreas = [
  {
    label: '任务定焦',
    description: '把目标、边界和优先级压成一张可派发的任务卡。',
    icon: Compass,
  },
  {
    label: '引用封包',
    description: '只保留当前任务真正需要的链接、路径、PR 与工单。',
    icon: FolderInput,
  },
  {
    label: '结果收口',
    description: '并行看多个 Agent run，再在一个地方完成 compare。',
    icon: GitCompareArrows,
  },
];

export function Sidebar() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <>
      <div className="sticky top-0 z-40 border-b border-border/70 bg-background/80 px-4 py-3 backdrop-blur lg:hidden">
        <div className="mx-auto flex max-w-[1680px] items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-[1.35rem] bg-primary text-primary-foreground shadow-[0_16px_32px_rgba(202,99,49,0.22)]">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <div className="font-display text-base font-semibold">KAM Lite</div>
              <div className="text-xs text-muted-foreground">任务到结果的单一工作带</div>
            </div>
          </div>
          <Button variant="outline" onClick={() => setIsSettingsOpen(true)} className="rounded-full px-4">
            <Settings2 className="h-4 w-4" />
            外观
          </Button>
        </div>
      </div>

      <aside className="sticky top-0 hidden h-[100dvh] w-[22rem] shrink-0 border-r border-border/70 bg-card/58 backdrop-blur-2xl lg:flex lg:flex-col">
        <div className="border-b border-border/70 px-6 py-6">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-[1.5rem] bg-primary text-primary-foreground shadow-[0_16px_32px_rgba(202,99,49,0.22)]">
              <Bot className="h-6 w-6" />
            </div>
            <div>
              <div className="font-display text-xl font-semibold">KAM Lite</div>
              <div className="text-sm text-muted-foreground">External Brain for Agent Work</div>
            </div>
          </div>
          <p className="mt-5 text-sm leading-6 text-muted-foreground">
            不再堆模块。这里只保留一条干净主线，把任务定焦、上下文封包、Agent 并行执行和结果收口放在同一张工作台里。
          </p>
        </div>

        <div className="flex-1 overflow-auto px-6 py-6">
          <div className="rounded-[2rem] border border-border/70 bg-background/78 p-5 shadow-[0_20px_50px_rgba(24,20,14,0.08)]">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              <Workflow className="h-3.5 w-3.5" />
              Lite Core
            </div>
            <div className="font-display mt-4 text-2xl font-semibold">唯一工作带</div>
            <div className="mt-2 text-sm leading-6 text-muted-foreground">
              任务卡
              <ArrowRight className="mx-2 inline h-3.5 w-3.5" />
              引用
              <ArrowRight className="mx-2 inline h-3.5 w-3.5" />
              Context
              <ArrowRight className="mx-2 inline h-3.5 w-3.5" />
              Runs
              <ArrowRight className="mx-2 inline h-3.5 w-3.5" />
              Compare
            </div>
          </div>

          <div className="mt-6 space-y-3">
            {focusAreas.map((item, index) => {
              const Icon = item.icon;

              return (
                <div
                  key={item.label}
                  className={cn(
                    'rounded-[1.75rem] border border-border/70 bg-background/78 p-4 transition-all duration-200',
                    'hover:-translate-y-0.5 hover:border-primary/20 hover:bg-background/92'
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 rounded-[1rem] bg-primary/10 p-2.5 text-primary">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <div className="font-display text-base font-semibold">{item.label}</div>
                      </div>
                      <div className="mt-2 text-sm leading-6 text-muted-foreground">{item.description}</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-6 rounded-[2rem] bg-foreground px-5 py-5 text-background shadow-[0_24px_60px_rgba(20,18,14,0.22)]">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-background/60">
              <Sparkles className="h-3.5 w-3.5" />
              Design Intent
            </div>
            <div className="font-display mt-3 text-xl font-semibold">减少界面噪音，让每一块都服务当前任务。</div>
            <ul className="mt-4 space-y-3 text-sm leading-6 text-background/76">
              <li>左侧只看任务池与当前阶段。</li>
              <li>中间锁定任务焦点和上下文。</li>
              <li>右侧只处理运行与收口。</li>
            </ul>
          </div>
        </div>

        <div className="border-t border-border/70 px-6 py-5">
          <Button
            variant="outline"
            onClick={() => setIsSettingsOpen(true)}
            className="w-full justify-between rounded-full border-border/80 bg-background/80 px-5"
          >
            <span className="flex items-center gap-2">
              <Settings2 className="h-4 w-4" />
              外观设置
            </span>
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </aside>

      <SettingsPanel isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </>
  );
}
