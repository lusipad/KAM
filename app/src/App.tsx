import { MainLayout } from '@/components/Layout/MainLayout';
import { WorkspaceView } from '@/components/V2/WorkspaceView';
import { ThemeProvider } from '@/components/Theme/ThemeProvider';
import { Toaster } from '@/components/ui/sonner';
import './App.css';

function App() {
  return (
    <ThemeProvider>
      <MainLayout>
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-4 px-1 pt-1">
            <div>
              <div className="font-display text-2xl font-semibold tracking-tight">KAM</div>
              <div className="text-sm text-muted-foreground">个人 AI 指挥台 · Project / Thread / Run / Memory</div>
            </div>
          </div>
          <WorkspaceView />
        </div>
        <Toaster />
      </MainLayout>
    </ThemeProvider>
  );
}

export default App;
