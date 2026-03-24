import { useState } from 'react';
import { 
  BookOpen, Brain, Bot, ClipboardList, GitBranch, MessageSquare, 
  ChevronLeft, ChevronRight, Settings, User 
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useApiStore } from '@/store/apiStore';
import { SettingsPanel } from '@/components/Settings/SettingsPanel';
import { cn } from '@/lib/utils';

interface NavItem {
  id: 'tasks' | 'knowledge' | 'memory' | 'clawteam' | 'azure-devops' | 'chat';
  label: string;
  icon: React.ElementType;
  description: string;
}

const navItems: NavItem[] = [
  {
    id: 'tasks',
    label: '任务台',
    icon: ClipboardList,
    description: '任务、上下文、Agent runs'
  },
  { 
    id: 'knowledge', 
    label: '知识管理', 
    icon: BookOpen,
    description: '笔记、双链、知识图谱'
  },
  { 
    id: 'memory', 
    label: '长期记忆', 
    icon: Brain,
    description: '记忆存储与检索'
  },
  { 
    id: 'clawteam', 
    label: 'ClawTeam', 
    icon: Bot,
    description: 'AI代理团队协作'
  },
  { 
    id: 'azure-devops', 
    label: 'Azure DevOps', 
    icon: GitBranch,
    description: '项目同步与集成'
  },
  { 
    id: 'chat', 
    label: 'AI对话', 
    icon: MessageSquare,
    description: '智能助手对话'
  },
];

export function Sidebar() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  
  const { 
    currentView, 
    sidebarCollapsed, 
    setCurrentView, 
    toggleSidebar,
  } = useApiStore();

  return (
    <div 
      className={cn(
        "flex flex-col h-full bg-card border-r transition-all duration-300",
        sidebarCollapsed ? "w-16" : "w-64"
      )}
    >
      {/* Logo区域 */}
      <div className="flex items-center justify-between p-4 border-b">
        {!sidebarCollapsed && (
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <span className="font-semibold text-lg">AI助手</span>
          </div>
        )}
        {sidebarCollapsed && (
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center mx-auto">
            <Bot className="w-5 h-5 text-white" />
          </div>
        )}
        {!sidebarCollapsed && (
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={toggleSidebar}
            className="h-8 w-8"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* 导航菜单 */}
      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentView === item.id;
          
          return (
            <button
              key={item.id}
              onClick={() => setCurrentView(item.id)}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all",
                "hover:bg-accent hover:text-accent-foreground",
                isActive 
                  ? "bg-primary/10 text-primary border border-primary/20" 
                  : "text-muted-foreground",
                sidebarCollapsed && "justify-center px-2"
              )}
              title={sidebarCollapsed ? item.label : undefined}
            >
              <Icon className={cn("w-5 h-5 flex-shrink-0", isActive && "text-primary")} />
              {!sidebarCollapsed && (
                <div className="flex flex-col items-start text-left">
                  <span className={cn("text-sm font-medium", isActive && "text-primary")}>
                    {item.label}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {item.description}
                  </span>
                </div>
              )}
            </button>
          );
        })}
      </nav>

      {/* 底部区域 */}
      <div className="p-2 border-t space-y-1">
        <button
          onClick={() => setIsSettingsOpen(true)}
          className={cn(
            "w-full flex items-center gap-3 px-3 py-2 rounded-lg",
            "hover:bg-accent hover:text-accent-foreground text-muted-foreground",
            sidebarCollapsed && "justify-center px-2"
          )}
        >
          <Settings className="w-5 h-5" />
          {!sidebarCollapsed && <span className="text-sm">设置</span>}
        </button>
        
        {!sidebarCollapsed && (
          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
              <User className="w-4 h-4" />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-medium">用户</span>
              <span className="text-xs text-muted-foreground">user@example.com</span>
            </div>
          </div>
        )}
      </div>

      {/* 展开按钮（折叠时显示） */}
      {sidebarCollapsed && (
        <Button 
          variant="ghost" 
          size="icon" 
          onClick={toggleSidebar}
          className="absolute -right-3 top-20 h-6 w-6 rounded-full border bg-background"
        >
          <ChevronRight className="h-3 w-3" />
        </Button>
      )}
      
      {/* 设置面板 */}
      <SettingsPanel isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  );
}
