import { useState } from 'react';
import { 
  Search, Brain, Clock, Star, Trash2, 
  TrendingUp, Database, Zap
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useApiStore } from '@/store/apiStore';
import { useEffect } from 'react';
import { cn } from '@/lib/utils';
import type { MemoryType } from '@/types';

const memoryTypeConfig: Record<MemoryType, { label: string; color: string; icon: React.ElementType }> = {
  fact: { label: '事实记忆', color: 'bg-blue-500', icon: Database },
  procedure: { label: '程序记忆', color: 'bg-green-500', icon: Zap },
  episodic: { label: '情境记忆', color: 'bg-purple-500', icon: Clock },
};

export function MemoryView() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState<MemoryType | 'all'>('all');
  
  const memories = useApiStore((state) => state.memory.memories);
  const searchResults = useApiStore((state) => state.memory.searchResults);
  const isSearching = useApiStore((state) => state.memory.isSearching);
  const isLoading = useApiStore((state) => state.memory.isLoading);
  const searchMemories = useApiStore((state) => state.memory.searchMemories);
  const fetchMemories = useApiStore((state) => state.memory.fetchMemories);
  const deleteMemory = useApiStore((state) => state.memory.deleteMemory);

  // 加载记忆数据
  useEffect(() => {
    fetchMemories();
  }, [fetchMemories]);

  const displayMemories = searchQuery ? searchResults : memories;

  const filteredMemories = displayMemories.filter(memory => {
    if (selectedType !== 'all' && memory.memoryType !== selectedType) return false;
    if (searchQuery) {
      return memory.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
             memory.metadata.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()));
    }
    return true;
  });

  const handleSearch = async (query: string) => {
    setSearchQuery(query);
    if (query) {
      await searchMemories(query);
    }
  };

  const getImportanceColor = (score: number) => {
    if (score >= 0.8) return 'text-red-500';
    if (score >= 0.6) return 'text-orange-500';
    if (score >= 0.4) return 'text-yellow-500';
    return 'text-gray-400';
  };

  return (
    <div className="flex h-full">
      {/* 左侧搜索和筛选 */}
      <div className="w-80 flex-shrink-0 border-r bg-card/30 p-4">
        <div className="space-y-4">
          {/* 搜索框 */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder="搜索记忆..."
              className="pl-9"
            />
          </div>

          {/* 记忆类型筛选 */}
          <div>
            <h3 className="text-sm font-medium mb-2">记忆类型</h3>
            <div className="space-y-1">
              <button
                onClick={() => setSelectedType('all')}
                className={cn(
                  "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                  selectedType === 'all' 
                    ? "bg-primary/10 text-primary" 
                    : "hover:bg-accent text-muted-foreground"
                )}
              >
                <Brain className="h-4 w-4" />
                全部记忆
                <span className="ml-auto text-xs">{memories.length}</span>
              </button>
              {(Object.keys(memoryTypeConfig) as MemoryType[]).map((type) => {
                const config = memoryTypeConfig[type];
                const count = memories.filter(m => m.memoryType === type).length;
                return (
                  <button
                    key={type}
                    onClick={() => setSelectedType(type)}
                    className={cn(
                      "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                      selectedType === type 
                        ? "bg-primary/10 text-primary" 
                        : "hover:bg-accent text-muted-foreground"
                    )}
                  >
                    <config.icon className="h-4 w-4" />
                    {config.label}
                    <span className="ml-auto text-xs">{count}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 统计卡片 */}
          <div className="grid grid-cols-2 gap-2">
            <Card>
              <CardContent className="p-3">
                <div className="text-2xl font-bold">{memories.length}</div>
                <div className="text-xs text-muted-foreground">总记忆数</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <div className="text-2xl font-bold">
                  {memories.filter(m => m.metadata.importanceScore > 0.7).length}
                </div>
                <div className="text-xs text-muted-foreground">重要记忆</div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* 右侧内容区 */}
      <div className="flex-1 flex flex-col">
        <Tabs defaultValue="list" className="flex-1 flex flex-col">
          <div className="flex items-center justify-between px-4 py-2 border-b bg-card/50">
            <TabsList>
              <TabsTrigger value="list">列表视图</TabsTrigger>
              <TabsTrigger value="stats">统计分析</TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="list" className="flex-1 m-0">
            <ScrollArea className="h-[calc(100vh-10rem)]">
              <div className="p-4 space-y-3">
                {isLoading || isSearching ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                  </div>
                ) : filteredMemories.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground">
                    <Brain className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>暂无记忆数据</p>
                    <p className="text-sm mt-1">与AI对话后，重要信息会自动保存为记忆</p>
                  </div>
                ) : (
                  filteredMemories.map((memory) => {
                    const typeConfig = memoryTypeConfig[memory.memoryType];
                    return (
                      <Card 
                        key={memory.id} 
                        className="hover:border-primary/50 transition-colors cursor-pointer"
                      >
                        <CardContent className="p-4">
                          <div className="flex items-start gap-3">
                            <div className={cn(
                              "w-2 h-2 rounded-full mt-2 flex-shrink-0",
                              typeConfig.color
                            )} />
                            
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <Badge variant="outline" className="text-xs">
                                  {typeConfig.label}
                                </Badge>
                                <span className="text-xs text-muted-foreground">
                                  {memory.category}
                                </span>
                              </div>
                              
                              <p className="text-sm line-clamp-3">
                                {memory.content}
                              </p>
                              
                              {memory.summary && (
                                <p className="text-xs text-muted-foreground mt-2 line-clamp-2">
                                  摘要: {memory.summary}
                                </p>
                              )}
                              
                              <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
                                <div className="flex items-center gap-1">
                                  <Star className={cn(
                                    "h-3 w-3",
                                    getImportanceColor(memory.metadata.importanceScore)
                                  )} />
                                  <span>{(memory.metadata.importanceScore * 100).toFixed(0)}%</span>
                                </div>
                                <div className="flex items-center gap-1">
                                  <TrendingUp className="h-3 w-3" />
                                  <span>{memory.metadata.accessCount} 次访问</span>
                                </div>
                                <div className="flex items-center gap-1">
                                  <Clock className="h-3 w-3" />
                                  <span>{new Date(memory.metadata.lastAccessed).toLocaleDateString()}</span>
                                </div>
                              </div>
                              
                              {memory.metadata.tags.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-2">
                                  {memory.metadata.tags.map((tag) => (
                                    <Badge key={tag} variant="secondary" className="text-[10px]">
                                      {tag}
                                    </Badge>
                                  ))}
                                </div>
                              )}
                            </div>
                            
                            <Button 
                              variant="ghost" 
                              size="icon" 
                              className="h-7 w-7 text-muted-foreground hover:text-destructive"
                              onClick={() => deleteMemory(memory.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })
                )}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="stats" className="flex-1 m-0 p-4">
            <div className="grid grid-cols-3 gap-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">记忆类型分布</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {(Object.keys(memoryTypeConfig) as MemoryType[]).map((type) => {
                      const count = memories.filter(m => m.memoryType === type).length;
                      const percentage = memories.length > 0 ? (count / memories.length * 100).toFixed(1) : '0';
                      const config = memoryTypeConfig[type];
                      return (
                        <div key={type} className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className={cn("w-3 h-3 rounded-full", config.color)} />
                            <span className="text-sm">{config.label}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{count}</span>
                            <span className="text-xs text-muted-foreground">({percentage}%)</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">重要性分布</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {[
                      { label: '高重要性 (0.8+)', min: 0.8, color: 'text-red-500' },
                      { label: '中高重要性 (0.6-0.8)', min: 0.6, max: 0.8, color: 'text-orange-500' },
                      { label: '中等重要性 (0.4-0.6)', min: 0.4, max: 0.6, color: 'text-yellow-500' },
                      { label: '低重要性 (<0.4)', max: 0.4, color: 'text-gray-400' },
                    ].map((range) => {
                      const count = memories.filter(m => {
                        const score = m.metadata.importanceScore;
                        if (range.min !== undefined && score < range.min) return false;
                        if (range.max !== undefined && score >= range.max) return false;
                        return true;
                      }).length;
                      return (
                        <div key={range.label} className="flex items-center justify-between">
                          <span className={cn("text-sm", range.color)}>{range.label}</span>
                          <span className="text-sm font-medium">{count}</span>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">访问统计</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm">总访问次数</span>
                      <span className="text-sm font-medium">
                        {memories.reduce((acc, m) => acc + m.metadata.accessCount, 0)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">平均访问次数</span>
                      <span className="text-sm font-medium">
                        {memories.length > 0 
                          ? (memories.reduce((acc, m) => acc + m.metadata.accessCount, 0) / memories.length).toFixed(1)
                          : '0'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm">最近7天新增</span>
                      <span className="text-sm font-medium">
                        {memories.filter(m => {
                          const daysSinceCreation = (Date.now() - new Date(m.metadata.createdAt).getTime()) / (1000 * 60 * 60 * 24);
                          return daysSinceCreation <= 7;
                        }).length}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
