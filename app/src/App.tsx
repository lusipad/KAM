import { useEffect } from 'react';
import { MainLayout } from '@/components/Layout/MainLayout';
import { TasksView } from '@/components/Tasks/TasksView';
import { KnowledgeView } from '@/components/Knowledge/KnowledgeView';
import { MemoryView } from '@/components/Memory/MemoryView';
import { ClawTeamView } from '@/components/ClawTeam/ClawTeamView';
import { AzureDevOpsView } from '@/components/AzureDevOps/AzureDevOpsView';
import { ChatView } from '@/components/Chat/ChatView';
import { ThemeProvider } from '@/components/Theme/ThemeProvider';
import { useApiStore } from '@/store/apiStore';
import { Toaster } from '@/components/ui/sonner';
import './App.css';

function App() {
  const currentView = useApiStore((state) => state.currentView);
  
  // 初始化数据
  useEffect(() => {
    // 加载初始数据
    useApiStore.getState().knowledge.fetchNotes();
    useApiStore.getState().memory.fetchMemories();
    useApiStore.getState().clawteam.fetchAgents();
    useApiStore.getState().clawteam.fetchTeams();
    useApiStore.getState().azureDevOps.fetchConfigs();
    useApiStore.getState().chat.fetchConversations();
  }, []);

  const renderView = () => {
    switch (currentView) {
      case 'tasks':
        return <TasksView />;
      case 'knowledge':
        return <KnowledgeView />;
      case 'memory':
        return <MemoryView />;
      case 'clawteam':
        return <ClawTeamView />;
      case 'azure-devops':
        return <AzureDevOpsView />;
      case 'chat':
        return <ChatView />;
      default:
        return <TasksView />;
    }
  };

  return (
    <ThemeProvider>
      <MainLayout>
        <div className="h-full">
          {renderView()}
        </div>
        <Toaster />
      </MainLayout>
    </ThemeProvider>
  );
}

export default App;
