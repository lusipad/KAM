import { useState, useEffect, useCallback } from 'react';
import { 
  Bold, Italic, List, ListOrdered, Link as LinkIcon, 
  Code, Quote, Heading1, Heading2, Save,
  MoreHorizontal, Tag, Share2, History, Loader2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { useApiStore } from '@/store/apiStore';
import type { Note } from '@/types';

interface NoteEditorProps {
  note?: Note;
}

export function NoteEditor({ note }: NoteEditorProps) {
  const [title, setTitle] = useState(note?.title || '');
  const [content, setContent] = useState(note?.content || '');
  const [tags, setTags] = useState<string[]>(note?.metadata?.tags || []);
  const [newTag, setNewTag] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(note?.updatedAt ? new Date(note.updatedAt) : null);

  const updateNote = useApiStore((state) => state.knowledge.updateNote);
  const isLoading = useApiStore((state) => state.knowledge.isLoading);

  useEffect(() => {
    if (note) {
      setTitle(note.title);
      setContent(note.content);
      setTags(note.metadata?.tags || []);
      setLastSaved(note.updatedAt ? new Date(note.updatedAt) : null);
      setIsDirty(false);
    }
  }, [note?.id]);

  const handleSave = useCallback(async () => {
    if (!note || !isDirty) return;
    
    await updateNote(note.id, {
      title,
      content,
      metadata: {
        ...note.metadata,
        tags,
      },
    });
    
    setLastSaved(new Date());
    setIsDirty(false);
  }, [note, title, content, tags, isDirty, updateNote]);

  // 自动保存
  useEffect(() => {
    if (!isDirty || !note) return;
    
    const timer = setTimeout(() => {
      handleSave();
    }, 3000);
    
    return () => clearTimeout(timer);
  }, [isDirty, title, content, tags, note, handleSave]);

  const handleContentChange = (value: string) => {
    setContent(value);
    setIsDirty(true);
  };

  const handleTitleChange = (value: string) => {
    setTitle(value);
    setIsDirty(true);
  };

  const addTag = () => {
    if (newTag && !tags.includes(newTag)) {
      setTags([...tags, newTag]);
      setNewTag('');
      setIsDirty(true);
    }
  };

  const removeTag = (tagToRemove: string) => {
    setTags(tags.filter(tag => tag !== tagToRemove));
    setIsDirty(true);
  };

  const insertMarkdown = (before: string, after: string = '') => {
    const textarea = document.getElementById('note-editor') as HTMLTextAreaElement;
    if (!textarea) return;
    
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = content.substring(start, end);
    const newText = content.substring(0, start) + before + selectedText + after + content.substring(end);
    
    setContent(newText);
    setIsDirty(true);
    
    setTimeout(() => {
      textarea.focus();
      const newCursorPos = start + before.length + selectedText.length;
      textarea.setSelectionRange(newCursorPos, newCursorPos);
    }, 0);
  };

  if (!note) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <div className="text-center">
          <p>选择一个笔记或创建新笔记</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* 顶部工具栏 */}
      <div className="flex items-center justify-between px-4 py-2 border-b bg-card/50">
        <div className="flex items-center gap-2">
          {isDirty && (
            <Badge variant="secondary" className="text-xs">
              未保存
            </Badge>
          )}
          {lastSaved && !isDirty && (
            <span className="text-xs text-muted-foreground">
              已保存 {lastSaved.toLocaleTimeString()}
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-1">
          {/* Markdown工具栏 */}
          <div className="flex items-center gap-0.5 mr-4">
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-8 w-8"
              onClick={() => insertMarkdown('**', '**')}
              title="粗体"
            >
              <Bold className="h-4 w-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-8 w-8"
              onClick={() => insertMarkdown('*', '*')}
              title="斜体"
            >
              <Italic className="h-4 w-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-8 w-8"
              onClick={() => insertMarkdown('# ')}
              title="标题1"
            >
              <Heading1 className="h-4 w-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-8 w-8"
              onClick={() => insertMarkdown('## ')}
              title="标题2"
            >
              <Heading2 className="h-4 w-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-8 w-8"
              onClick={() => insertMarkdown('- ')}
              title="无序列表"
            >
              <List className="h-4 w-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-8 w-8"
              onClick={() => insertMarkdown('1. ')}
              title="有序列表"
            >
              <ListOrdered className="h-4 w-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-8 w-8"
              onClick={() => insertMarkdown('> ')}
              title="引用"
            >
              <Quote className="h-4 w-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-8 w-8"
              onClick={() => insertMarkdown('`', '`')}
              title="代码"
            >
              <Code className="h-4 w-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-8 w-8"
              onClick={() => insertMarkdown('[', '](url)')}
              title="链接"
            >
              <LinkIcon className="h-4 w-4" />
            </Button>
          </div>
          
          <Button 
            size="sm" 
            onClick={handleSave}
            disabled={!isDirty || isLoading}
            className="gap-1"
          >
            {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            保存
          </Button>
          
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem>
                <Share2 className="h-4 w-4 mr-2" />
                分享
              </DropdownMenuItem>
              <DropdownMenuItem>
                <History className="h-4 w-4 mr-2" />
                历史版本
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* 编辑器内容 */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-4xl mx-auto p-6">
          {/* 标题输入 */}
          <Input
            value={title}
            onChange={(e) => handleTitleChange(e.target.value)}
            placeholder="笔记标题..."
            className="text-2xl font-bold border-0 bg-transparent px-0 focus-visible:ring-0 placeholder:text-muted-foreground/50"
          />
          
          {/* 标签管理 */}
          <div className="flex items-center gap-2 mt-4 mb-6">
            <div className="flex flex-wrap gap-1">
              {tags.map((tag) => (
                <Badge 
                  key={tag} 
                  variant="secondary"
                  className="cursor-pointer hover:bg-destructive/20"
                  onClick={() => removeTag(tag)}
                >
                  #{tag} ×
                </Badge>
              ))}
            </div>
            <div className="flex items-center gap-1">
              <Input
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addTag()}
                placeholder="添加标签..."
                className="h-7 w-32 text-sm"
              />
              <Button 
                variant="ghost" 
                size="icon" 
                className="h-7 w-7"
                onClick={addTag}
              >
                <Tag className="h-3 w-3" />
              </Button>
            </div>
          </div>
          
          {/* 内容编辑区 */}
          <Textarea
            id="note-editor"
            value={content}
            onChange={(e) => handleContentChange(e.target.value)}
            placeholder="开始写作... 使用 Markdown 语法"
            className="min-h-[500px] resize-none border-0 bg-transparent px-0 font-mono text-sm leading-relaxed focus-visible:ring-0"
          />
        </div>
      </div>

      {/* 底部状态栏 */}
      <div className="flex items-center justify-between px-4 py-2 border-t bg-card/50 text-xs text-muted-foreground">
        <div className="flex items-center gap-4">
          <span>{content.split(/\s+/).filter(Boolean).length} 词</span>
          <span>{content.length} 字符</span>
          <span>预计阅读 {Math.ceil(content.split(/\s+/).filter(Boolean).length / 200)} 分钟</span>
        </div>
        <div className="flex items-center gap-2">
          <span>版本 {note.version}</span>
        </div>
      </div>
    </div>
  );
}
