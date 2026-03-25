import { MainLayout } from '@/components/Layout/MainLayout';
import { WorkspaceView } from '@/components/V2/WorkspaceView';
import { ThemeProvider } from '@/components/Theme/ThemeProvider';
import { Toaster } from '@/components/ui/sonner';
import './App.css';

function App() {
  return (
    <ThemeProvider>
      <MainLayout>
        <WorkspaceView />
        <Toaster />
      </MainLayout>
    </ThemeProvider>
  );
}

export default App;
