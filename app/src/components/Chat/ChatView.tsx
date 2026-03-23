import { useState, useRef, useEffect } from 'react';
import { 
  Send, Plus, MoreVertical, Trash2, Edit, 
  Bot, User, Sparkles, Brain, BookOpen, GitBranch
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { useApiStore } from '@/store/apiStore';
import { cn } from '@/lib/utils';

export function ChatView() {
  const [inputMessage, setInputMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  const conversations = useApiStore((state) => state.chat.conversations);
  const currentConversationId = useApiStore((state) => state.chat.currentConversationId);
  const isGenerating = useApiStore((state) => state.chat.isGenerating);
  const deleteConversation = useApiStore((state) => state.chat.deleteConversation);
  const setCurrentConversation = useApiStore((state) => state.chat.setCurrentConversation);
  const sendMessage = useApiStore((state) => state.chat.sendMessage);
  const createConversation = useApiStore((state) => state.chat.createConversation);
  const fetchConversations = useApiStore((state) => state.chat.fetchConversations);

  const currentConversation = conversations.find(c => c.id === currentConversationId);

  // 加载对话列表
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentConversation?.messages]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isGenerating) return;
    
    await sendMessage(inputMessage);
    setInputMessage('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const formatTime = (date: Date) => {
    return new Date(date).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="flex h-full">
      {/* 左侧对话列表 */}
      <div className="w-72 flex-shrink-0 border-r bg-card/30 flex flex-col">
        <div className="flex items-center justify-between p-3 border-b">
          <h2 className="font-semibold text-sm">对话历史</h2>
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-7 w-7"
            onClick={createConversation}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-2 space-y-1">
            {conversations.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">
                <p>暂无对话</p>
                <p className="text-xs mt-1">点击 + 开始新对话</p>
              </div>
            ) : (
              conversations
                .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
                .map((conversation) => (
                <div
                  key={conversation.id}
                  onClick={() => setCurrentConversation(conversation.id)}
                  className={cn(
                    "group flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-all",
                    currentConversationId === conversation.id
                      ? "bg-primary/10 text-primary border border-primary/20"
                      : "hover:bg-accent text-muted-foreground"
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <div className={cn(
                      "font-medium text-sm truncate",
                      currentConversationId === conversation.id && "text-primary"
                    )}>
                      {conversation.title}
                    </div>
                    <div className="text-xs opacity-70 truncate">
                      {conversation.messages.length > 0
                        ? conversation.messages[conversation.messages.length - 1].content.slice(0, 30) + '...'
                        : '新对话'}
                    </div>
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
                        <Edit className="h-4 w-4 mr-2" />
                        重命名
                      </DropdownMenuItem>
                      <DropdownMenuItem 
                        className="text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteConversation(conversation.id);
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
      </div>

      {/* 右侧对话区 */}
      <div className="flex-1 flex flex-col">
        {currentConversation ? (
          <>
            {/* 消息列表 */}
            <ScrollArea className="flex-1 p-4">
              <div className="space-y-4 max-w-4xl mx-auto">
                {currentConversation.messages.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground">
                    <Bot className="h-16 w-16 mx-auto mb-4 opacity-50" />
                    <p className="text-lg font-medium">开始新的对话</p>
                    <p className="text-sm mt-2">我可以帮您：</p>
                    <div className="flex flex-wrap justify-center gap-2 mt-4">
                      <Badge variant="outline" className="gap-1">
                        <BookOpen className="h-3 w-3" />
                        管理知识笔记
                      </Badge>
                      <Badge variant="outline" className="gap-1">
                        <Brain className="h-3 w-3" />
                        检索长期记忆
                      </Badge>
                      <Badge variant="outline" className="gap-1">
                        <Sparkles className="h-3 w-3" />
                        执行代理任务
                      </Badge>
                      <Badge variant="outline" className="gap-1">
                        <GitBranch className="h-3 w-3" />
                        同步项目数据
                      </Badge>
                    </div>
                  </div>
                ) : (
                  currentConversation.messages.map((message) => (
                    <div
                      key={message.id}
                      className={cn(
                        "flex gap-3",
                        message.role === 'user' ? "flex-row-reverse" : "flex-row"
                      )}
                    >
                      <div className={cn(
                        "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0",
                        message.role === 'user' 
                          ? "bg-primary/10" 
                          : "bg-gradient-to-br from-blue-500 to-purple-600"
                      )}>
                        {message.role === 'user' ? (
                          <User className="h-4 w-4 text-primary" />
                        ) : (
                          <Bot className="h-4 w-4 text-white" />
                        )}
                      </div>
                      
                      <div className={cn(
                        "max-w-[80%] space-y-1",
                        message.role === 'user' ? "items-end" : "items-start"
                      )}>
                        <div className={cn(
                          "px-4 py-2 rounded-lg",
                          message.role === 'user'
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted"
                        )}>
                          <div className="whitespace-pre-wrap text-sm">
                            {message.content}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span>{formatTime(message.timestamp)}</span>
                          {message.metadata?.model && (
                            <span>· {message.metadata.model}</span>
                          )}
                          {message.metadata?.tokens && (
                            <span>· {message.metadata.tokens} tokens</span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))
                )}
                
                {isGenerating && (
                  <div className="flex gap-3">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                      <Bot className="h-4 w-4 text-white" />
                    </div>
                    <div className="bg-muted px-4 py-2 rounded-lg">
                      <div className="flex items-center gap-2">
                        <div className="animate-bounce">
                          <div className="w-2 h-2 rounded-full bg-primary" />
                        </div>
                        <div className="animate-bounce delay-100">
                          <div className="w-2 h-2 rounded-full bg-primary" />
                        </div>
                        <div className="animate-bounce delay-200">
                          <div className="w-2 h-2 rounded-full bg-primary" />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
                
                <div ref={messagesEndRef} />
              </div>
            </ScrollArea>

            {/* 输入框 */}
            <div className="p-4 border-t bg-card/50">
              <div className="max-w-4xl mx-auto flex gap-2">
                <Textarea
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="输入消息... (Shift+Enter 换行)"
                  className="min-h-[60px] resize-none"
                  disabled={isGenerating}
                />
                <Button 
                  onClick={handleSendMessage}
                  disabled={!inputMessage.trim() || isGenerating}
                  className="h-[60px] px-4"
                >
                  {isGenerating ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                </Button>
              </div>
              <div className="max-w-4xl mx-auto mt-2 text-xs text-center text-muted-foreground">
                AI助手可以访问您的知识库、记忆和项目数据来提供个性化响应
              </div>
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center">
              <Bot className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium">选择一个对话或开始新对话</p>
              <Button 
                className="mt-4 gap-1"
                onClick={createConversation}
              >
                <Plus className="h-4 w-4" />
                新对话
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
