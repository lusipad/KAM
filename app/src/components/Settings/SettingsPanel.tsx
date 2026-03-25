import { Monitor, Moon, Palette, Sun, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTheme } from '@/components/Theme/ThemeProvider';
import { cn } from '@/lib/utils';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const colorOptions = [
  { id: 'default', name: '赭石', swatch: '#ca6331', darkSwatch: '#dd814c' },
  { id: 'graphite', name: '石墨', swatch: '#374151', darkSwatch: '#d1d5db' },
  { id: 'moss', name: '苔绿', swatch: '#627c43', darkSwatch: '#8ca46a' },
  { id: 'teal', name: '深青', swatch: '#2f7a7d', darkSwatch: '#62afb1' },
  { id: 'brick', name: '陶红', swatch: '#ca583c', darkSwatch: '#e47b5f' },
  { id: 'amber', name: '琥珀', swatch: '#d39a12', darkSwatch: '#e5b844' },
] as const;

export function SettingsPanel({ isOpen, onClose }: SettingsPanelProps) {
  const { theme, colorTheme, setTheme, setColorTheme } = useTheme();

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 px-4 backdrop-blur-sm">
      <div className="flex max-h-[84vh] w-full max-w-2xl flex-col overflow-hidden rounded-[2rem] border border-border/70 bg-card/95 shadow-[0_30px_120px_rgba(20,18,14,0.25)]">
        <div className="flex items-start justify-between border-b border-border/70 px-6 py-5">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">Workspace Look</div>
            <h2 className="font-display mt-2 text-2xl font-semibold">外观设置</h2>
            <p className="mt-2 max-w-[42ch] text-sm leading-6 text-muted-foreground">
              调整工作台的昼夜模式与强调色，让任务、运行态和收口信息有更稳定的视觉重心。
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="grid gap-8 overflow-auto px-6 py-6 lg:grid-cols-[0.92fr_1.08fr]">
          <section>
            <div className="mb-4 flex items-center gap-2 text-sm font-medium">
              <Palette className="h-4 w-4" />
              主题模式
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <button
                onClick={() => setTheme('light')}
                className={cn(
                  'rounded-[1.5rem] border border-border/70 bg-background/80 p-4 text-left transition-all duration-200',
                  theme === 'light'
                    ? 'border-primary/40 bg-primary/10 shadow-[0_16px_30px_rgba(202,99,49,0.12)]'
                    : 'hover:-translate-y-0.5 hover:bg-accent/60'
                )}
              >
                <Sun className="h-5 w-5" />
                <div className="mt-3 text-sm font-medium">浅色</div>
                <div className="mt-1 text-xs leading-5 text-muted-foreground">纸面感更强，适合审阅长上下文和任务清单。</div>
              </button>
              <button
                onClick={() => setTheme('dark')}
                className={cn(
                  'rounded-[1.5rem] border border-border/70 bg-background/80 p-4 text-left transition-all duration-200',
                  theme === 'dark'
                    ? 'border-primary/40 bg-primary/10 shadow-[0_16px_30px_rgba(202,99,49,0.12)]'
                    : 'hover:-translate-y-0.5 hover:bg-accent/60'
                )}
              >
                <Moon className="h-5 w-5" />
                <div className="mt-3 text-sm font-medium">深色</div>
                <div className="mt-1 text-xs leading-5 text-muted-foreground">更适合盯日志、diff、patch 和长时间调试。</div>
              </button>
              <button
                onClick={() => setTheme('system')}
                className={cn(
                  'rounded-[1.5rem] border border-border/70 bg-background/80 p-4 text-left transition-all duration-200',
                  theme === 'system'
                    ? 'border-primary/40 bg-primary/10 shadow-[0_16px_30px_rgba(202,99,49,0.12)]'
                    : 'hover:-translate-y-0.5 hover:bg-accent/60'
                )}
              >
                <Monitor className="h-5 w-5" />
                <div className="mt-3 text-sm font-medium">跟随系统</div>
                <div className="mt-1 text-xs leading-5 text-muted-foreground">保持系统一致，不需要单独切换工作台色温。</div>
              </button>
            </div>
          </section>

          <section>
            <div className="mb-4 text-sm font-medium">强调色</div>
            <div className="grid gap-3 sm:grid-cols-2">
              {colorOptions.map((option) => (
                <button
                  key={option.id}
                  onClick={() => setColorTheme(option.id)}
                  className={cn(
                    'flex items-start gap-4 rounded-[1.5rem] border border-border/70 bg-background/80 p-4 text-left transition-all duration-200',
                    colorTheme === option.id
                      ? 'border-primary/40 bg-primary/10 shadow-[0_16px_30px_rgba(202,99,49,0.12)]'
                      : 'hover:-translate-y-0.5 hover:bg-accent/60'
                  )}
                >
                  <div className="mt-0.5 flex gap-2">
                    <span
                      className="h-5 w-5 rounded-full border border-black/10"
                      style={{ backgroundColor: theme === 'dark' ? option.darkSwatch : option.swatch }}
                    />
                    <span className="h-5 w-5 rounded-full border border-black/10 bg-white/70" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">{option.name}</div>
                    <div className="mt-1 text-xs leading-5 text-muted-foreground">
                      调整按钮、高亮标签与操作反馈的焦点颜色。
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
