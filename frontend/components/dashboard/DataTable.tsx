/** Generic typed data table: loading, error, empty, selection, row click. */
import type { ReactNode } from 'react';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  /** Hidden below the lg breakpoint to keep mobile tables readable. */
  hideOnMobile?: boolean;
  className?: string;
}

interface DataTableProps<T extends { id: string }> {
  columns: Column<T>[];
  rows: T[];
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  onRowClick?: (row: T) => void;
  /** Selection (bulk actions). Provide all three to enable. */
  selection?: {
    isSelected: (id: string) => boolean;
    toggle: (id: string) => void;
    toggleAll: (ids: string[]) => void;
    allSelected: boolean;
  };
}

export function DataTable<T extends { id: string }>({
  columns,
  rows,
  isLoading,
  error,
  onRetry,
  emptyTitle = 'Nothing here yet',
  emptyDescription,
  emptyAction,
  onRowClick,
  selection,
}: DataTableProps<T>) {
  if (isLoading) return <TableSkeleton rows={5} cols={columns.length} />;
  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (rows.length === 0)
    return <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500 dark:border-gray-700">
          <tr>
            {selection && (
              <th className="w-10 px-4 py-3">
                <input
                  type="checkbox"
                  aria-label="Select all rows"
                  checked={selection.allSelected}
                  onChange={() => selection.toggleAll(rows.map((r) => r.id))}
                  className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                />
              </th>
            )}
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-4 py-3 font-semibold ${col.hideOnMobile ? 'hidden lg:table-cell' : ''} ${col.className ?? ''}`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
          {rows.map((row) => (
            <tr
              key={row.id}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={onRowClick ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50' : ''}
            >
              {selection && (
                <td className="w-10 px-4 py-3" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label={`Select row ${row.id}`}
                    checked={selection.isSelected(row.id)}
                    onChange={() => selection.toggle(row.id)}
                    className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                  />
                </td>
              )}
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`px-4 py-3 ${col.hideOnMobile ? 'hidden lg:table-cell' : ''} ${col.className ?? ''}`}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
