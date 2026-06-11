import { Button } from '@/components/ui/Button';

export function Pagination({
  page,
  pageSize,
  itemCount,
  total,
  onPrev,
  onNext,
}: {
  page: number;
  pageSize: number;
  itemCount: number;
  total?: number | null;
  onPrev: () => void;
  onNext: () => void;
}) {
  const from = page * pageSize + (itemCount > 0 ? 1 : 0);
  const to = page * pageSize + itemCount;

  return (
    <div className="flex items-center justify-between border-t border-gray-100 px-4 py-3 dark:border-gray-700">
      <p className="text-sm text-gray-500">
        {total != null ? `Showing ${from}–${to} of ${total} items` : `Showing ${from}–${to}`}
      </p>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" disabled={page === 0} onClick={onPrev}>
          ← Previous
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={total != null ? to >= total : itemCount < pageSize}
          onClick={onNext}
        >
          Next →
        </Button>
      </div>
    </div>
  );
}
