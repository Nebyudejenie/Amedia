'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useAuthStore } from '@/stores/auth';

export function UserMenu() {
  const { user, logout } = useAuthStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const initials = (user?.full_name ?? user?.email ?? '?')
    .split(' ')
    .map((s) => s[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-full p-1 hover:bg-gray-100 dark:hover:bg-gray-700"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">
          {initials}
        </span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-56 rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-800"
        >
          <div className="border-b border-gray-100 px-4 py-2 dark:border-gray-700">
            <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
              {user?.full_name ?? 'User'}
            </p>
            <p className="truncate text-xs text-gray-500">{user?.email}</p>
          </div>
          <Link
            href="/dashboard/settings"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700"
          >
            Settings
          </Link>
          <button
            role="menuitem"
            onClick={logout}
            className="block w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
