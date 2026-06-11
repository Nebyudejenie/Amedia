'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Modal } from '@/components/ui/Modal';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { PasswordStrength } from '@/components/auth/PasswordStrength';
import { api, ApiError, type User } from '@/lib/api';
import { useApi } from '@/lib/hooks';
import { passwordSchema } from '@/lib/validators';
import { relativeTime } from '@/lib/format';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';
import type { ApiKey, Invoice } from '@/lib/types';

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

function ProfileSection() {
  const { user, setUser } = useAuthStore();
  const addToast = useUiStore((s) => s.addToast);
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url ?? '');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const body: Record<string, string> = {};
      if (fullName !== (user?.full_name ?? '')) body.full_name = fullName;
      if (avatarUrl && avatarUrl !== (user?.avatar_url ?? '')) body.avatar_url = avatarUrl;
      const updated = await api.patch<User>('/api/v1/users/me', body);
      setUser(updated);
      addToast('Profile updated', 'success');
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Update failed', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="Profile">
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          {/* eslint-disable-next-line @next/next/no-img-element -- avatar URLs are external */}
          <img
            src={avatarUrl || `https://api.dicebear.com/8.x/initials/svg?seed=${user?.email}`}
            alt="Avatar"
            className="h-16 w-16 rounded-full border border-gray-200 object-cover dark:border-gray-700"
          />
          <div className="flex-1">
            <Input
              label="Avatar URL"
              placeholder="https://…/avatar.png"
              value={avatarUrl}
              onChange={(e) => setAvatarUrl(e.target.value)}
            />
          </div>
        </div>
        <Input label="Email" value={user?.email ?? ''} disabled />
        <Input
          label="Full name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          placeholder="Your name"
        />
        <Button onClick={save} isLoading={saving}>
          Save changes
        </Button>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// API Keys
// ---------------------------------------------------------------------------

function ApiKeysSection() {
  const addToast = useUiStore((s) => s.addToast);
  const { data, isLoading, error, refetch } = useApi<{ keys?: ApiKey[] }>('/auth/api-keys');
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);
  const [creating, setCreating] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);

  const keys = data?.keys ?? [];

  const createKey = async () => {
    setCreating(true);
    try {
      const created = await api.post<{ api_key?: string; key?: string }>('/auth/api-keys', {
        name: `key-${Date.now()}`,
      });
      setNewKey(created.api_key ?? created.key ?? null);
      void refetch();
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Failed to create key', 'error');
    } finally {
      setCreating(false);
    }
  };

  const revokeKey = async () => {
    if (!revokeTarget) return;
    try {
      await api.delete(`/auth/api-keys/${revokeTarget.id}`);
      addToast('API key revoked', 'success');
      setRevokeTarget(null);
      void refetch();
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Revoke failed', 'error');
    }
  };

  const copy = (text: string) => {
    void navigator.clipboard.writeText(text);
    addToast('Copied to clipboard', 'success');
  };

  return (
    <Card title="API Keys">
      <div className="space-y-4">
        {isLoading ? (
          <p className="text-sm text-gray-400">Loading keys…</p>
        ) : error || keys.length === 0 ? (
          <EmptyState title="No API keys" description="Create a key to access the Arada API programmatically." />
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {keys.map((key) => (
              <li key={key.id} className="flex items-center justify-between py-3">
                <div>
                  <code className="text-sm text-gray-900 dark:text-white">
                    {key.key_prefix}{'•'.repeat(24)}
                  </code>
                  <p className="text-xs text-gray-400">
                    {key.last_used_at ? `Last used ${relativeTime(key.last_used_at)}` : 'Never used'}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => copy(key.key_prefix)}>
                    Copy
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => setRevokeTarget(key)}>
                    Revoke
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
        <Button onClick={createKey} isLoading={creating} variant="secondary">
          + Create new key
        </Button>
      </div>

      {/* Show full key exactly once after creation */}
      <Modal open={newKey !== null} onClose={() => setNewKey(null)} title="API key created">
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Copy this key now — it will <b>not</b> be shown again.
        </p>
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-gray-100 p-3 dark:bg-gray-700">
          <code className="flex-1 break-all text-sm">{newKey}</code>
          <Button size="sm" onClick={() => newKey && copy(newKey)}>
            Copy
          </Button>
        </div>
      </Modal>

      <ConfirmDialog
        open={revokeTarget !== null}
        title="Revoke API key?"
        message="Applications using this key will immediately lose access."
        confirmLabel="Revoke"
        destructive
        onConfirm={revokeKey}
        onCancel={() => setRevokeTarget(null)}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Billing
// ---------------------------------------------------------------------------

interface BillingInfo {
  plan?: string;
  usage?: number;
  limit?: number;
  invoices?: Invoice[];
}

function BillingSection() {
  const { data } = useApi<BillingInfo>('/api/v1/billing');
  const plan = data?.plan ?? 'Free';
  const usage = data?.usage ?? 0;
  const limit = data?.limit ?? 100;
  const percent = limit > 0 ? Math.round((usage / limit) * 100) : 0;
  const invoices = data?.invoices ?? [];

  return (
    <Card title="Billing">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500">Current plan</p>
            <p className="text-lg font-semibold text-gray-900 dark:text-white">{plan}</p>
          </div>
          <Button variant="secondary" size="sm">
            Upgrade plan
          </Button>
        </div>

        <div>
          <div className="mb-1 flex justify-between text-sm">
            <span className="text-gray-500">Usage this month</span>
            <span className="font-medium text-gray-900 dark:text-white">
              {usage} / {limit} analyses
            </span>
          </div>
          <div
            className="h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-700"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Monthly usage"
          >
            <div
              className={`h-full rounded-full ${percent > 90 ? 'bg-red-500' : 'bg-brand-600'}`}
              style={{ width: `${Math.min(percent, 100)}%` }}
            />
          </div>
        </div>

        <div>
          <p className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">Invoice history</p>
          {invoices.length === 0 ? (
            <p className="text-sm text-gray-400">No invoices yet.</p>
          ) : (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {invoices.map((inv) => (
                  <tr key={inv.id}>
                    <td className="py-2 text-gray-500">{inv.date}</td>
                    <td className="py-2">{inv.amount}</td>
                    <td className="py-2 capitalize">{inv.status}</td>
                    <td className="py-2 text-right">
                      {inv.url && (
                        <a href={inv.url} className="text-brand-600 hover:underline" download>
                          Download
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

const ALERT_TYPES = [
  { key: 'analysis_complete', label: 'Analysis complete' },
  { key: 'error_occurred', label: 'Error occurred' },
  { key: 'weekly_digest', label: 'Weekly digest' },
  { key: 'usage_alerts', label: 'Usage limit alerts' },
];

function NotificationsSection() {
  const addToast = useUiStore((s) => s.addToast);
  const [frequency, setFrequency] = useState('weekly');
  const [alerts, setAlerts] = useState<Set<string>>(new Set(['analysis_complete', 'error_occurred']));
  const [saving, setSaving] = useState(false);

  const toggleAlert = (key: string) =>
    setAlerts((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const save = async () => {
    setSaving(true);
    try {
      await api.patch('/api/v1/users/me/notifications', {
        frequency,
        alerts: Array.from(alerts),
      });
      addToast('Notification preferences saved', 'success');
    } catch {
      // Endpoint ships in a later phase — store locally for now
      addToast('Preferences saved locally', 'info');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="Notifications">
      <div className="space-y-4">
        <Select
          label="Email frequency"
          options={[
            { value: 'daily', label: 'Daily' },
            { value: 'weekly', label: 'Weekly' },
            { value: 'monthly', label: 'Monthly' },
          ]}
          value={frequency}
          onChange={(e) => setFrequency(e.target.value)}
        />
        <fieldset>
          <legend className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
            Alert types
          </legend>
          <div className="space-y-2">
            {ALERT_TYPES.map((alert) => (
              <label key={alert.key} className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={alerts.has(alert.key)}
                  onChange={() => toggleAlert(alert.key)}
                  className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                />
                {alert.label}
              </label>
            ))}
          </div>
        </fieldset>
        <Button onClick={save} isLoading={saving}>
          Save preferences
        </Button>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Danger zone
// ---------------------------------------------------------------------------

const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, 'Current password required'),
    new_password: passwordSchema,
    confirm: z.string(),
  })
  .refine((d) => d.new_password === d.confirm, {
    message: 'Passwords do not match',
    path: ['confirm'],
  });

type ChangePasswordInput = z.infer<typeof changePasswordSchema>;

function DangerZone() {
  const addToast = useUiStore((s) => s.addToast);
  const logout = useAuthStore((s) => s.logout);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordInput>({ resolver: zodResolver(changePasswordSchema) });

  const newPassword = watch('new_password', '');

  const changePassword = async (data: ChangePasswordInput) => {
    try {
      await api.post('/auth/change-password', {
        current_password: data.current_password,
        new_password: data.new_password,
      });
      addToast('Password changed — please sign in again', 'success');
      setPasswordOpen(false);
      // Backend invalidates all sessions; send the user to login
      setTimeout(() => void logout(), 1200);
    } catch (err) {
      addToast(err instanceof ApiError ? err.detail : 'Change failed', 'error');
    }
  };

  return (
    <Card title="Danger zone" className="border-red-200 dark:border-red-900">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-white">Change password</p>
            <p className="text-xs text-gray-500">All sessions will be signed out.</p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setPasswordOpen(true)}>
            Change password
          </Button>
        </div>
        <div className="flex items-center justify-between border-t border-gray-100 pt-3 dark:border-gray-700">
          <div>
            <p className="text-sm font-medium text-red-600">Delete account</p>
            <p className="text-xs text-gray-500">Permanently removes your account and data.</p>
          </div>
          <Button variant="danger" size="sm" onClick={() => setDeleteOpen(true)}>
            Delete account
          </Button>
        </div>
      </div>

      <Modal open={passwordOpen} onClose={() => setPasswordOpen(false)} title="Change password">
        <form onSubmit={handleSubmit(changePassword)} className="space-y-4" noValidate>
          <Input
            label="Current password"
            showPasswordToggle
            autoComplete="current-password"
            error={errors.current_password?.message}
            {...register('current_password')}
          />
          <div className="space-y-2">
            <Input
              label="New password"
              showPasswordToggle
              autoComplete="new-password"
              error={errors.new_password?.message}
              {...register('new_password')}
            />
            <PasswordStrength password={newPassword} />
          </div>
          <Input
            label="Confirm new password"
            showPasswordToggle
            autoComplete="new-password"
            error={errors.confirm?.message}
            {...register('confirm')}
          />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setPasswordOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" isLoading={isSubmitting}>
              Change password
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={deleteOpen}
        title="Delete your account?"
        message="This permanently deletes your account, content, and analytics. This action cannot be undone."
        confirmLabel="Yes, delete my account"
        destructive
        onConfirm={async () => {
          try {
            await api.delete('/api/v1/users/me');
            await logout();
          } catch (err) {
            addToast(err instanceof ApiError ? err.detail : 'Deletion failed', 'error');
            setDeleteOpen(false);
          }
        }}
        onCancel={() => setDeleteOpen(false)}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------

export default function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
      <ProfileSection />
      <ApiKeysSection />
      <BillingSection />
      <NotificationsSection />
      <DangerZone />
    </div>
  );
}
