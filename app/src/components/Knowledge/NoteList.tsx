import { useState } from 'react';
import { 
  FileText, MoreVertical, Search, Plus, 
  Clock, Hash, Link2, Loader2, Trash2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { useApiStore } from '@/store/apiStore';
import { cn } from '@/lib/utils';
import type { Note } from '@/types';

interface NoteListProps {
  onSelectNote: (note: Note) => void;
  selectedNoteId?: string;
}

export function NoteList({ onSelectNote, selectedNoteId }: NoteListProps) {
  const [searchQuery, setSearchQuery] = useState('');
  
  const notes = useApiStore((state) => state.knowledge.notes);
  const isLoading = useApiStore((state) => state.knowledge.isLoading);
  const createNote = useApiStore((state) => state.knowledge.createNote);
  const deleteNote = useApiStore((state) => state.knowledge.deleteNote);

  const filteredNotes = notes.filter(note => 
    note.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    note.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
    note.metadata?.tags?.some((tag: string) => tag.toLowerCase().includes(searchQuery.toLowerCase()))
  ).sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());

  const handleCreateNote = async () => {
    await createNote({
      title: '未命名笔记',
      content: '',
    });
  };

  return (
    <div className="flex flex-col h-full border-r bg-card/30">
      {/* 头部工具栏 */}
      <div className="flex items-center justify-between p-3 border-b">
        <h2 className="font-semibold text-sm">笔记列表</h2>
        <div className="flex items-center gap-1">
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-7 w-7"
            onClick={handleCreateNote}
            disabled={isLoading}
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {/* 搜索框 */}
      <div className="p-3 border-b">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索笔记..."
            className="pl-8 h-8 text-sm"
          />
        </div>
      </div>

      {/* 笔记列表 */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {isLoading && notes.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : filteredNotes.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              {searchQuery ? '没有找到匹配的笔记' : '暂无笔记，点击 + 创建'}
            </div>
          ) : (
            filteredNotes.map((note) => (
              <div
                key={note.id}
                onClick={() => onSelectNote(note)}
                className={cn(
                  "group flex items-start gap-2 p-2 rounded-lg cursor-pointer transition-all",
                  "hover:bg-accent hover:text-accent-foreground",
                  selectedNoteId === note.id 
                    ? "bg-primary/10 text-primary border border-primary/20" 
                    : "text-muted-foreground"
                )}
              >
                <FileText className={cn(
                  "h-4 w-4 mt-0.5 flex-shrink-0",
                  selectedNoteId === note.id && "text-primary"
                )} />
                
                <div className="flex-1 min-w-0">
                  <div className={cn(
                    "font-medium text-sm truncate",
                    selectedNoteId === note.id && "text-primary"
                  )}>
                    {note.title || '未命名笔记'}
                  </div>
                  
                  <div className="flex items-center gap-2 mt-1 text-xs">
                    <span className="flex items-center gap-0.5">
                      <Clock className="h-3 w-3" />
                      {new Date(note.updatedAt).toLocaleDateString()}
                    </span>
                    {note.metadata?.tags?.length > 0 && (
                      <span className="flex items-center gap-0.5">
                        <Hash className="h-3 w-3" />
                        {note.metadata.tags.length}
                      </span>
                    )}
                    {note.stats?.backlinkCount > 0 && (
                      <span className="flex items-center gap-0.5">
                        <Link2 className="h-3 w-3" />
                        {note.stats.backlinkCount}
                      </span>
                    )}
                  </div>
                  
                  {note.metadata?.tags?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {note.metadata.tags.slice(0, 3).map((tag: string) => (
                        <span 
                          key={tag} 
                          className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground"
                        >
                          #{tag}
                        </span>
                      ))}
                      {note.metadata.tags.length > 3 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground">
                          +{note.metadata.tags.length - 3}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="h-6 w-6 opacity-0 group-hover:opacity-100"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreVertical className="h-3 w-3" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={(e) => e.stopPropagation()}>
                      重命名
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={(e) => e.stopPropagation()}>
                      复制链接
                    </DropdownMenuItem>
                    <DropdownMenuItem 
                      className="text-destructive"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteNote(note.id);
                      }}
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      删除
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ))
          )}
        </div>
      </ScrollArea>

      {/* 底部统计 */}
      <div className="p-2 border-t text-xs text-muted-foreground">
        <div className="flex items-center justify-between">
          <span>{filteredNotes.length} 个笔记</span>
          <span>{notes.reduce((acc, n) => acc + (n.stats?.wordCount || 0), 0)} 词</span>
        </div>
      </div>
    </div>
  );
}
