'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useUiStore } from '@/stores/ui';
import { useAuthStore } from '@/stores/auth';

const NAV_ITEMS = [
  { href: '/dashboard', label: 'Overview', icon: 'M3 12l9-9 9 9M5 10v10a1 1 0 001 1h3a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1h3a1 1 0 001-1V10' },
  { href: '/dashboard/content', label: 'Content', icon: 'M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10l6 6v8a2 2 0 01-2 2zM15 4v6h6' },
  { href: '/dashboard/analytics', label: 'Analytics', icon: 'M9 19v-6m4 6V9m4 10V5M5 19h16' },
  { href: '/dashboard/settings', label: 'Settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
];

const ADMIN_ITEMS = [
  { href: '/dashboard/admin/users', label: 'Users', icon: 'M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6-4a4 4 0 11-8 0' },
];

function NavLink({ href, label, icon, onClick }: { href: string; label: string; icon: string; onClick?: () => void }) {
  const pathname = usePathname();
  const active = href === '/dashboard' ? pathname === href : pathname.startsWith(href);

  return (
    <Link
      href={href}
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
        active
          ? 'bg-brand-600 text-white'
          : 'text-gray-300 hover:bg-gray-800 hover:text-white'
      }`}
    >
      <svg className="h-5 w-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={icon} />
      </svg>
      {label}
    </Link>
  );
}

export function Sidebar() {
  const { sidebarOpen, setSidebarOpen } = useUiStore();
  const user = useAuthStore((s) => s.user);
  const close = () => setSidebarOpen(false);

  return (
    <>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={close} aria-hidden />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 transform bg-gray-900 transition-transform lg:static lg:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-label="Main navigation"
      >
        <div className="flex h-16 items-center gap-2 border-b border-gray-800 px-6">
          <div className="h-8 w-8 rounded-lg bg-brand-600 text-center text-lg font-bold leading-8 text-white">
            A
          </div>
          <span className="font-semibold text-white">Arada OS</span>
        </div>

        <nav className="space-y-1 p-4">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.href} {...item} onClick={close} />
          ))}

          {user?.is_admin && (
            <>
              <p className="px-3 pb-1 pt-4 text-xs font-semibold uppercase tracking-wider text-gray-500">
                Admin
              </p>
              {ADMIN_ITEMS.map((item) => (
                <NavLink key={item.href} {...item} onClick={close} />
              ))}
            </>
          )}
        </nav>
      </aside>
    </>
  );
}
