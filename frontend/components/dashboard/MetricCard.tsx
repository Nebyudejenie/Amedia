import { memo, type ReactNode } from 'react';
import { compactNumber } from '@/lib/format';

interface MetricCardProps {
  label: string;
  value: number | string | null;
  hint?: string;
  /** Render a 0-100 progress bar instead of a big number. */
  percent?: boolean;
  icon?: ReactNode;
}

export const MetricCard = memo(function MetricCard({
  label,
  value,
  hint,
  percent = false,
  icon,
}: MetricCardProps) {
  const display =
    value === null ? '—' : typeof value === 'number' && !percent ? compactNumber(value) : value;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{label}</p>
        {icon && <span className="text-gray-400">{icon}</span>}
      </div>

      {percent && typeof value === 'number' ? (
        <div className="mt-3 space-y-2">
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}%</p>
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700"
            role="progressbar"
            aria-valuenow={value}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={label}
          >
            <div
              className={`h-full rounded-full transition-all ${
                value > 90 ? 'bg-red-500' : value > 70 ? 'bg-yellow-500' : 'bg-brand-600'
              }`}
              style={{ width: `${Math.min(value, 100)}%` }}
            />
          </div>
        </div>
      ) : (
        <p className="mt-1 text-3xl font-bold text-gray-900 dark:text-white">{display}</p>
      )}

      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  );
});
