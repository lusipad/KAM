import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

export type ProjectCreateForm = {
  title: string;
  description: string;
  repoPath: string;
  checkCommands: string;
};

export function ProjectCreateModal({
  open,
  onOpenChange,
  form,
  onFormChange,
  onSubmit,
  isMutating,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  form: ProjectCreateForm;
  onFormChange: (next: ProjectCreateForm) => void;
  onSubmit: () => void;
  isMutating: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[620px]">
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>只保留最少信息，后续细节可以在 Context 里补齐。</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <Input
            value={form.title}
            onChange={(event) => onFormChange({ ...form, title: event.target.value })}
            placeholder="项目标题"
          />
          <Textarea
            value={form.description}
            onChange={(event) => onFormChange({ ...form, description: event.target.value })}
            placeholder="项目描述（可选）"
            className="min-h-[110px]"
          />
          <Input
            value={form.repoPath}
            onChange={(event) => onFormChange({ ...form, repoPath: event.target.value })}
            placeholder="仓库路径（可选）"
          />
          <Textarea
            value={form.checkCommands}
            onChange={(event) => onFormChange({ ...form, checkCommands: event.target.value })}
            placeholder="检查命令，每行一个（可选）"
            className="min-h-[110px] font-mono text-xs"
          />
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button type="button" onClick={onSubmit} disabled={!form.title.trim() || isMutating}>
            创建项目
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
