interface MainLayoutProps {
  children: React.ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
  return (
    <div className="lite-shell flex min-h-[100dvh] bg-background text-foreground">
      <main className="relative min-w-0 flex-1">
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="lite-orb lite-orb-primary" />
          <div className="lite-orb lite-orb-secondary" />
          <div className="lite-grid-haze" />
        </div>
        <div className="relative mx-auto min-h-[100dvh] max-w-[1680px] px-4 py-4 lg:px-5 lg:py-5">
          {children}
        </div>
      </main>
    </div>
  );
}
