import { useState, useEffect } from 'react';
import { BookOpen, Share2, GitGraph, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { NoteList } from './NoteList';
import { NoteEditor } from './NoteEditor';
import { KnowledgeGraph } from './KnowledgeGraph';
import { useApiStore } from '@/store/apiStore';
import type { Note } from '@/types';

export function KnowledgeView() {
  const [selectedNote, setSelectedNote] = useState<Note | undefined>();
  const [activeTab, setActiveTab] = useState('editor');
  
  const notes = useApiStore((state) => state.knowledge.notes);
  const isLoading = useApiStore((state) => state.knowledge.isLoading);
  const createNote = useApiStore((state) => state.knowledge.createNote);

  // 当笔记列表更新时，更新选中的笔记
  useEffect(() => {
    if (selectedNote) {
      const updated = notes.find(n => n.id === selectedNote.id);
      if (updated) {
        setSelectedNote(updated);
      }
    }
  }, [notes]);

  const handleSelectNote = (note: Note) => {
    setSelectedNote(note);
    setActiveTab('editor');
  };

  const handleCreateNote = async () => {
    const newNote = await createNote({
      title: '未命名笔记',
      content: '',
    });
    if (newNote) {
      setSelectedNote(newNote);
      setActiveTab('editor');
    }
  };

  return (
    <div className="flex h-full">
      {/* 左侧笔记列表 */}
      <div className="w-72 flex-shrink-0">
        <NoteList 
          onSelectNote={handleSelectNote}
          selectedNoteId={selectedNote?.id}
        />
      </div>

      {/* 右侧内容区 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 顶部标签栏 */}
        <div className="flex items-center justify-between px-4 py-2 border-b bg-card/50">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <div className="flex items-center justify-between">
              <TabsList className="grid w-auto grid-cols-3">
                <TabsTrigger value="editor" className="gap-1">
                  <BookOpen className="h-4 w-4" />
                  编辑器
                </TabsTrigger>
                <TabsTrigger value="graph" className="gap-1">
                  <GitGraph className="h-4 w-4" />
                  知识图谱
                </TabsTrigger>
                <TabsTrigger value="backlinks" className="gap-1">
                  <Share2 className="h-4 w-4" />
                  双向链接
                </TabsTrigger>
              </TabsList>
              
              <div className="flex items-center gap-2">
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={handleCreateNote}
                  disabled={isLoading}
                >
                  {isLoading && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                  新建笔记
                </Button>
              </div>
            </div>

            <TabsContent value="editor" className="m-0 h-[calc(100vh-8rem)]">
              <NoteEditor note={selectedNote} />
            </TabsContent>

            <TabsContent value="graph" className="m-0 h-[calc(100vh-8rem)]">
              <KnowledgeGraph 
                onSelectNode={(nodeId) => {
                  const note = notes.find(n => n.id === nodeId);
                  if (note) {
                    setSelectedNote(note);
                    setActiveTab('editor');
                  }
                }}
                highlightNodeId={selectedNote?.id}
              />
            </TabsContent>

            <TabsContent value="backlinks" className="m-0 h-[calc(100vh-8rem)]">
              <div className="p-6">
                <h3 className="text-lg font-semibold mb-4">双向链接</h3>
                {selectedNote ? (
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-sm font-medium text-muted-foreground mb-2">
                        引用此笔记的笔记
                      </h4>
                      <div className="space-y-2">
                        <p className="text-sm text-muted-foreground">
                          暂无反向链接
                        </p>
                      </div>
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-muted-foreground mb-2">
                        此笔记引用的笔记
                      </h4>
                      <div className="space-y-2">
                        <p className="text-sm text-muted-foreground">
                          提取链接功能开发中...
                        </p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-muted-foreground">选择一个笔记查看链接关系</p>
                )}
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
