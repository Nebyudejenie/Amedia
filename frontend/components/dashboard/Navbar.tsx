'use client';

import { useUiStore } from '@/stores/ui';
import { UserMenu } from '@/components/dashboard/UserMenu';

export function Navbar() {
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-gray-200 bg-white px-4 dark:border-gray-700 dark:bg-gray-800 lg:px-6">
      <button
        onClick={toggleSidebar}
        aria-label="Toggle navigation"
        className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 lg:hidden"
      >
        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <div className="hidden lg:block" />

      <UserMenu />
    </header>
  );
}
