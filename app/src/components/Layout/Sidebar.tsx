import { useState } from 'react';
import { Bot, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SettingsPanel } from '@/components/Settings/SettingsPanel';

const railSteps = ['Projects', 'Threads', 'Runs'];

export function Sidebar() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <>
      <div className="sticky top-0 z-40 border-b border-border/70 bg-background/86 px-4 py-3 backdrop-blur lg:hidden">
        <div className="mx-auto flex max-w-[1560px] items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-[1.25rem] bg-primary text-primary-foreground shadow-[0_16px_30px_rgba(202,99,49,0.18)]">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <div className="font-display text-base font-semibold">KAM</div>
              <div className="text-xs text-muted-foreground">个人 AI 指挥台</div>
            </div>
          </div>

          <Button variant="outline" onClick={() => setIsSettingsOpen(true)} className="rounded-full px-4">
            <Settings2 className="h-4 w-4" />
            外观设置
          </Button>
        </div>
      </div>

      <aside className="sticky top-0 hidden h-[100dvh] w-[5.5rem] shrink-0 border-r border-border/70 bg-card/46 backdrop-blur-2xl lg:flex lg:flex-col lg:items-center lg:justify-between lg:py-5">
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-[1.5rem] bg-primary text-primary-foreground shadow-[0_18px_34px_rgba(202,99,49,0.2)]">
            <Bot className="h-6 w-6" />
          </div>
          <div className="text-center">
            <div className="font-display text-sm font-semibold tracking-[0.18em]">KAM</div>
            <div className="mt-1 text-[10px] uppercase tracking-[0.24em] text-muted-foreground">Command</div>
          </div>
        </div>

        <div className="flex flex-col items-center gap-3 text-[10px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
          {railSteps.map((step) => (
            <div key={step} className="flex flex-col items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-primary/40" />
              <span>{step}</span>
            </div>
          ))}
        </div>

        <div className="flex flex-col items-center gap-2">
          <Button
            variant="outline"
            size="icon-lg"
            onClick={() => setIsSettingsOpen(true)}
            className="rounded-[1.2rem] border-border/80 bg-background/82"
            aria-label="外观设置"
          >
            <Settings2 className="h-4 w-4" />
          </Button>
          <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Look</span>
        </div>
      </aside>

      <SettingsPanel isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </>
  );
}
