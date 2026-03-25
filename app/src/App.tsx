import { MainLayout } from '@/components/Layout/MainLayout';
import { TasksView } from '@/components/Tasks/TasksView';
import { V2PreviewView } from '@/components/V2/V2PreviewView';
import { ThemeProvider } from '@/components/Theme/ThemeProvider';
import { Toaster } from '@/components/ui/sonner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import './App.css';

function App() {
  return (
    <ThemeProvider>
      <MainLayout>
        <Tabs defaultValue="v2" className="space-y-4">
          <div className="flex items-center justify-between gap-4 px-1 pt-1">
            <div>
              <div className="font-display text-2xl font-semibold tracking-tight">KAM</div>
              <div className="text-sm text-muted-foreground">v2 Preview 与 Lite Core 并行</div>
            </div>
            <TabsList className="rounded-full border border-border/70 bg-background/80 p-1">
              <TabsTrigger value="v2" className="rounded-full px-4">V2 Preview</TabsTrigger>
              <TabsTrigger value="lite" className="rounded-full px-4">Lite Core</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="v2" className="mt-0">
            <V2PreviewView />
          </TabsContent>
          <TabsContent value="lite" className="mt-0">
            <TasksView />
          </TabsContent>
        </Tabs>
        <Toaster />
      </MainLayout>
    </ThemeProvider>
  );
}

export default App;
