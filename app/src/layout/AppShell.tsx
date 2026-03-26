import type { ReactNode } from 'react';

export function AppShell({
  sidebar,
  children,
}: {
  sidebar: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 lg:grid lg:grid-cols-[296px_minmax(0,1fr)]">
      <div className="order-2 min-h-0 lg:order-1">{sidebar}</div>
      <div className="order-1 min-h-0 lg:order-2">{children}</div>
    </div>
  );
}
