import { MainLayout } from '@/components/Layout/MainLayout';
import { TasksView } from '@/components/Tasks/TasksView';
import { ThemeProvider } from '@/components/Theme/ThemeProvider';
import { Toaster } from '@/components/ui/sonner';
import './App.css';

function App() {
  return (
    <ThemeProvider>
      <MainLayout>
        <TasksView />
        <Toaster />
      </MainLayout>
    </ThemeProvider>
  );
}

export default App;
