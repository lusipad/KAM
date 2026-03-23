import { Sidebar } from './Sidebar';
import { useAppStore } from '@/store/appStore';
import { cn } from '@/lib/utils';

interface MainLayoutProps {
  children: React.ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
  const { sidebarCollapsed } = useAppStore();

  return (
    <div className="flex h-screen w-full bg-background">
      <Sidebar />
      <main 
        className={cn(
          "flex-1 overflow-hidden transition-all duration-300",
          sidebarCollapsed ? "ml-16" : "ml-64"
        )}
      >
        <div className="h-full overflow-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
