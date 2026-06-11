import type { ContentStatus } from '@/lib/types';

const STYLES: Record<ContentStatus, string> = {
  pending: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  analyzing: 'bg-blue-100 text-blue-700',
  complete: 'bg-green-100 text-green-700',
  error: 'bg-red-100 text-red-700',
};

export function StatusBadge({ status }: { status: ContentStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STYLES[status] ?? STYLES.pending}`}>
      {status}
    </span>
  );
}
