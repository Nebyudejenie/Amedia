import type { ReactNode } from 'react';

export function Card({
  title,
  children,
  className = '',
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800 ${className}`}>
      {title && <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>}
      {children}
    </div>
  );
}
