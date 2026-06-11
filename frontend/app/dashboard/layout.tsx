'use client';

import { useEffect } from 'react';
import { Navbar } from '@/components/dashboard/Navbar';
import { Sidebar } from '@/components/dashboard/Sidebar';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { useAuthStore } from '@/stores/auth';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isInitialized, fetchUser } = useAuthStore();

  useEffect(() => {
    if (!user && !isInitialized) void fetchUser();
  }, [user, isInitialized, fetchUser]);

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <Navbar />
        <main className="flex-1 p-4 lg:p-8">
          <ErrorBoundary>{children}</ErrorBoundary>
        </main>
        <footer className="border-t border-gray-200 px-6 py-4 text-center text-xs text-gray-400 dark:border-gray-700">
          Arada Intelligence OS ·{' '}
          <a href="/docs" className="hover:text-gray-600">Help</a> ·{' '}
          <a href="/dashboard/settings" className="hover:text-gray-600">Settings</a>
        </footer>
      </div>
    </div>
  );
}
