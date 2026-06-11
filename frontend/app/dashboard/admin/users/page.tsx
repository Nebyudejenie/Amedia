'use client';

import { useEffect, useMemo, useState } from 'react';

import { DataTable, type Column } from '@/components/dashboard/DataTable';
import { Pagination } from '@/components/dashboard/Pagination';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Modal } from '@/components/ui/Modal';
import { api, ApiError, type User } from '@/lib/api';
import { useApi, useDebounce, usePagination } from '@/lib/hooks';
import { relativeTime } from '@/lib/format';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';

const PAGE_SIZE = 20;

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'true', label: 'Active' },
  { value: 'false', label: 'Disabled' },
];

const ROLE_OPTIONS = [
  { value: '', label: 'All roles' },
  { value: 'true', label: 'Admins' },
  { value: 'false', label: 'Members' },
];

// ---------------------------------------------------------------------------
// User detail modal: view info, edit status/role, contact
// ---------------------------------------------------------------------------

function UserDetailModal({
  user,
  currentUserId,
  onClose,
  onSaved,
}: {
  user: User | null;
  currentUserId?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const addToast = useUiStore((s) => s.addToast);
  const [isActive, setIsActive] = useState(user?.is_active ?? true);
  const [isAdmin, setIsAdmin] = useState(user?.is_admin ?? false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setIsActive(user?.is_active ?? true);
    setIsAdmin(user?.is_admin ?? false);
  }, [user]);

  if (!user) return null;

  const isSelf = user.id === currentUserId;

  const save = async () => {
    setSaving(true);
    try {
      const body: Record<string, boolean> = {};
      if (isActive !== user.is_active) body.is_active = isActive;
      if (isAdmin !== user.is_admin) body.is_admin = isAdmin;
      if (Object.keys(body).length > 0) {
        await api.patch(`/api/v1/admin/users/${user.id}`, body);
        addToast('User updated', 'success');
        onSaved();
      }
      onClose();
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Update failed', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="User details">
      <div className="space-y-4">
        <div className="space-y-1 rounded-lg bg-gray-50 p-4 text-sm dark:bg-gray-700/50">
          <p><span className="text-gray-500">Name:</span> <b>{user.full_name ?? '—'}</b></p>
          <p><span className="text-gray-500">Email:</span> {user.email}</p>
          <p><span className="text-gray-500">Verified:</span> {user.email_verified ? 'Yes' : 'No'}</p>
          <p>
            <span className="text-gray-500">Joined:</span>{' '}
            {user.created_at ? relativeTime(user.created_at) : '—'}
          </p>
        </div>

        {isSelf ? (
          <p className="text-sm text-gray-500">You cannot edit your own account here.</p>
        ) : (
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
              />
              Account active
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isAdmin}
                onChange={(e) => setIsAdmin(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
              />
              Administrator role
            </label>
          </div>
        )}

        <div className="flex justify-between pt-2">
          <a
            href={`mailto:${user.email}`}
            className="text-sm font-medium text-brand-600 hover:underline"
          >
            Send email →
          </a>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={onClose}>
              Close
            </Button>
            {!isSelf && (
              <Button onClick={save} isLoading={saving}>
                Save changes
              </Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminUsersPage() {
  const currentUser = useAuthStore((s) => s.user);
  const addToast = useUiStore((s) => s.addToast);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [detailUser, setDetailUser] = useState<User | null>(null);

  const debouncedSearch = useDebounce(search);
  const pagination = usePagination(PAGE_SIZE);

  useEffect(() => {
    pagination.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, statusFilter, roleFilter]);

  const query = useMemo(() => {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(pagination.offset),
    });
    if (debouncedSearch) params.set('email', debouncedSearch);
    if (statusFilter) params.set('is_active', statusFilter);
    if (roleFilter) params.set('is_admin', roleFilter);
    return `/api/v1/admin/users?${params}`;
  }, [debouncedSearch, statusFilter, roleFilter, pagination.offset]);

  const { data, isLoading, error, refetch } = useApi<User[]>(query);
  const users = data ?? [];

  const toggleActive = async (user: User) => {
    try {
      await api.patch(`/api/v1/admin/users/${user.id}`, { is_active: !user.is_active });
      addToast(`User ${user.is_active ? 'disabled' : 'enabled'}`, 'success');
      void refetch();
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Update failed', 'error');
    }
  };

  const columns: Column<User>[] = [
    {
      key: 'user',
      header: 'User',
      render: (row) => (
        <div>
          <p className="font-medium text-gray-900 dark:text-white">{row.full_name ?? '—'}</p>
          <p className="text-xs text-gray-500">{row.email}</p>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Role',
      hideOnMobile: true,
      render: (row) =>
        row.is_admin ? (
          <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700">
            Admin
          </span>
        ) : (
          <span className="text-gray-500">Member</span>
        ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            row.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          }`}
        >
          {row.is_active ? 'Active' : 'Disabled'}
        </span>
      ),
    },
    {
      key: 'created',
      header: 'Created',
      hideOnMobile: true,
      render: (row) => (
        <span className="text-gray-500">{row.created_at ? relativeTime(row.created_at) : '—'}</span>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (row) =>
        row.id !== currentUser?.id ? (
          <div className="flex justify-end gap-2" onClick={(e) => e.stopPropagation()}>
            <Button size="sm" variant="secondary" onClick={() => setDetailUser(row)}>
              Edit
            </Button>
            <Button
              size="sm"
              variant={row.is_active ? 'danger' : 'secondary'}
              onClick={() => toggleActive(row)}
            >
              {row.is_active ? 'Disable' : 'Enable'}
            </Button>
          </div>
        ) : (
          <span className="text-xs text-gray-400">You</span>
        ),
    },
  ];

  if (currentUser && !currentUser.is_admin) {
    return <p className="text-sm text-gray-500">Admin access required.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Users</h1>
        <div className="flex flex-wrap gap-3">
          <input
            type="search"
            aria-label="Search by email or name"
            placeholder="Search by email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-gray-600 dark:bg-gray-800"
          />
          <Select aria-label="Filter by status" options={STATUS_OPTIONS} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} />
          <Select aria-label="Filter by role" options={ROLE_OPTIONS} value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} />
        </div>
      </div>

      <Card className="p-0">
        <DataTable
          columns={columns}
          rows={users}
          isLoading={isLoading}
          error={error}
          onRetry={refetch}
          emptyTitle="No users found"
          emptyDescription="Try adjusting your search or filters."
          onRowClick={setDetailUser}
        />
        {users.length > 0 && (
          <Pagination
            page={pagination.page}
            pageSize={PAGE_SIZE}
            itemCount={users.length}
            onPrev={pagination.prev}
            onNext={pagination.next}
          />
        )}
      </Card>

      <UserDetailModal
        user={detailUser}
        currentUserId={currentUser?.id}
        onClose={() => setDetailUser(null)}
        onSaved={refetch}
      />
    </div>
  );
}
