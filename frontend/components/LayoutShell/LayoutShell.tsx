"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider, ToastViewport } from "@radix-ui/react-toast";
import { TopNav } from "./TopNav";

interface LayoutShellProps {
  children: ReactNode;
}

export function LayoutShell({ children }: LayoutShellProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: 1
          }
        }
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider swipeDirection="right">
        <div className="min-h-screen bg-background text-foreground antialiased">
          <TopNav />
          <main className="relative flex h-[calc(100vh-4rem)] flex-col overflow-hidden">
            {children}
          </main>
        </div>
        <ToastViewport className="fixed bottom-0 right-0 z-50 m-4 flex max-w-xs flex-col gap-2" />
      </ToastProvider>
    </QueryClientProvider>
  );
}
