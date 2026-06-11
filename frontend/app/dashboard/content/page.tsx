'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { DataTable, type Column } from '@/components/dashboard/DataTable';
import { StatusBadge } from '@/components/dashboard/StatusBadge';
import { Pagination } from '@/components/dashboard/Pagination';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Modal } from '@/components/ui/Modal';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { api, ApiError } from '@/lib/api';
import { useApi, useDebounce, usePagination, useSelection } from '@/lib/hooks';
import { relativeTime, truncate } from '@/lib/format';
import { useUiStore } from '@/stores/ui';
import type { ContentItem } from '@/lib/types';

const PAGE_SIZE = 20;

const SOURCE_OPTIONS = [
  { value: '', label: 'All sources' },
  { value: 'rss', label: 'RSS' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'news', label: 'News' },
  { value: 'custom', label: 'Custom' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'analyzing', label: 'Analyzing' },
  { value: 'complete', label: 'Complete' },
  { value: 'error', label: 'Error' },
];

const SORT_OPTIONS = [
  { value: 'created_at', label: 'Sort: Date' },
  { value: 'title', label: 'Sort: Title' },
  { value: 'status', label: 'Sort: Status' },
];

// ---------------------------------------------------------------------------
// Add Content modal
// ---------------------------------------------------------------------------

const addContentSchema = z.object({
  title: z.string().min(2, 'Title is required').max(200),
  url: z.string().url('Enter a valid URL'),
  source_type: z.enum(['rss', 'telegram', 'youtube', 'news', 'custom']),
  tags: z.string().optional(),
});

type AddContentInput = z.infer<typeof addContentSchema>;

function AddContentModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const addToast = useUiStore((s) => s.addToast);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<AddContentInput>({
    resolver: zodResolver(addContentSchema),
    defaultValues: { source_type: 'rss' },
  });

  const onSubmit = async (data: AddContentInput) => {
    try {
      await api.post('/content/sources', {
        ...data,
        tags: data.tags
          ?.split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      });
      addToast('Content source added', 'success');
      reset();
      onClose();
      onCreated();
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Failed to add content', 'error');
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Add content">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <Input label="Title" placeholder="My news feed" error={errors.title?.message} {...register('title')} />
        <Input label="URL" placeholder="https://example.com/feed.xml" error={errors.url?.message} {...register('url')} />
        <Select
          label="Source type"
          options={SOURCE_OPTIONS.filter((o) => o.value)}
          {...register('source_type')}
        />
        <Input
          label="Tags (comma separated)"
          placeholder="tech, ai, news"
          error={errors.tags?.message}
          {...register('tags')}
        />
        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" isLoading={isSubmitting}>
            Add content
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Row actions dropdown
// ---------------------------------------------------------------------------

function RowActions({
  item,
  onAnalyze,
  onDelete,
}: {
  item: ContentItem;
  onAnalyze: (item: ContentItem) => void;
  onDelete: (item: ContentItem) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={() => setOpen(!open)}
        aria-label={`Actions for ${item.title}`}
        aria-haspopup="menu"
        aria-expanded={open}
        className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700"
      >
        <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 8a2 2 0 100-4 2 2 0 000 4zm0 6a2 2 0 100-4 2 2 0 000 4zm0 6a2 2 0 100-4 2 2 0 000 4z" />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-10 mt-1 w-36 rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-800"
          onMouseLeave={() => setOpen(false)}
        >
          <button
            role="menuitem"
            onClick={() => { setOpen(false); onAnalyze(item); }}
            className="block w-full px-3 py-1.5 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Analyze
          </button>
          <button
            role="menuitem"
            onClick={() => { setOpen(false); onDelete(item); }}
            className="block w-full px-3 py-1.5 text-left text-sm text-red-600 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function ContentPageInner() {
  const searchParams = useSearchParams();
  const addToast = useUiStore((s) => s.addToast);

  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [addOpen, setAddOpen] = useState(searchParams.get('add') === '1');
  const [deleteTarget, setDeleteTarget] = useState<ContentItem | null>(null);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const debouncedSearch = useDebounce(search);
  const pagination = usePagination(PAGE_SIZE);
  const selection = useSelection();

  // Reset to first page whenever a filter changes
  useEffect(() => {
    pagination.reset();
    selection.clear();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, sourceFilter, statusFilter, sortBy]);

  const query = useMemo(() => {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(pagination.offset),
      sort: sortBy,
    });
    if (debouncedSearch) params.set('q', debouncedSearch);
    if (sourceFilter) params.set('source_type', sourceFilter);
    if (statusFilter) params.set('status', statusFilter);
    return `/content/items?${params}`;
  }, [debouncedSearch, sourceFilter, statusFilter, sortBy, pagination.offset]);

  const { data, isLoading, error, refetch } = useApi<{ items?: ContentItem[]; total?: number }>(query);
  const items = data?.items ?? [];
  const total = data?.total ?? null;

  const analyze = async (item: ContentItem) => {
    try {
      await api.post(`/content/sources/${item.id}/fetch`);
      addToast('Analysis queued', 'success');
      void refetch();
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Failed to queue analysis', 'error');
    }
  };

  const deleteOne = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/content/items/${deleteTarget.id}`);
      addToast('Item deleted', 'success');
      setDeleteTarget(null);
      void refetch();
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Delete failed', 'error');
    } finally {
      setDeleting(false);
    }
  };

  const deleteBulk = async () => {
    setDeleting(true);
    const ids = Array.from(selection.selected);
    try {
      await Promise.all(ids.map((id) => api.delete(`/content/items/${id}`)));
      addToast(`${ids.length} items deleted`, 'success');
      selection.clear();
      setBulkDeleteOpen(false);
      void refetch();
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Bulk delete failed', 'error');
    } finally {
      setDeleting(false);
    }
  };

  const columns: Column<ContentItem>[] = [
    {
      key: 'title',
      header: 'Title',
      render: (row) => (
        <span className="font-medium text-gray-900 dark:text-white">{truncate(row.title, 50)}</span>
      ),
    },
    {
      key: 'source',
      header: 'Source',
      hideOnMobile: true,
      render: (row) => <span className="uppercase text-gray-500">{row.source_type}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'created',
      header: 'Created',
      hideOnMobile: true,
      render: (row) => <span className="text-gray-500">{relativeTime(row.created_at)}</span>,
    },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (row) => <RowActions item={row} onAnalyze={analyze} onDelete={setDeleteTarget} />,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Content</h1>
        <Button onClick={() => setAddOpen(true)}>+ Add Content</Button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <input
          type="search"
          aria-label="Search by title"
          placeholder="Search by title…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-800"
        />
        <div className="flex flex-wrap gap-3">
          <Select aria-label="Filter by source" options={SOURCE_OPTIONS} value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} />
          <Select aria-label="Filter by status" options={STATUS_OPTIONS} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} />
          <Select aria-label="Sort by" options={SORT_OPTIONS} value={sortBy} onChange={(e) => setSortBy(e.target.value)} />
        </div>
      </div>

      {/* Bulk action bar — appears when rows are selected */}
      {selection.selected.size > 0 && (
        <div className="flex items-center justify-between rounded-lg bg-brand-50 px-4 py-2 dark:bg-brand-900/30" role="status">
          <p className="text-sm font-medium text-brand-700 dark:text-brand-100">
            {selection.selected.size} selected
          </p>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={selection.clear}>
              Clear
            </Button>
            <Button size="sm" variant="danger" onClick={() => setBulkDeleteOpen(true)}>
              Delete selected
            </Button>
          </div>
        </div>
      )}

      <Card className="p-0">
        <DataTable
          columns={columns}
          rows={items}
          isLoading={isLoading}
          error={error}
          onRetry={refetch}
          emptyTitle="No content found"
          emptyDescription={
            debouncedSearch || sourceFilter || statusFilter
              ? 'Try adjusting your search or filters.'
              : 'Add your first content source to get started.'
          }
          emptyAction={<Button size="sm" onClick={() => setAddOpen(true)}>+ Add Content</Button>}
          selection={{
            isSelected: selection.isSelected,
            toggle: selection.toggle,
            toggleAll: selection.toggleAll,
            allSelected: items.length > 0 && selection.selected.size === items.length,
          }}
        />
        {items.length > 0 && (
          <Pagination
            page={pagination.page}
            pageSize={PAGE_SIZE}
            itemCount={items.length}
            total={total}
            onPrev={pagination.prev}
            onNext={pagination.next}
          />
        )}
      </Card>

      <AddContentModal open={addOpen} onClose={() => setAddOpen(false)} onCreated={refetch} />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete item?"
        message={`"${deleteTarget ? truncate(deleteTarget.title, 60) : ''}" will be permanently removed.`}
        confirmLabel="Delete"
        destructive
        isLoading={deleting}
        onConfirm={deleteOne}
        onCancel={() => setDeleteTarget(null)}
      />

      <ConfirmDialog
        open={bulkDeleteOpen}
        title={`Delete ${selection.selected.size} items?`}
        message="The selected items will be permanently removed. This cannot be undone."
        confirmLabel="Delete all"
        destructive
        isLoading={deleting}
        onConfirm={deleteBulk}
        onCancel={() => setBulkDeleteOpen(false)}
      />
    </div>
  );
}

export default function ContentPage() {
  return (
    <Suspense>
      <ContentPageInner />
    </Suspense>
  );
}
