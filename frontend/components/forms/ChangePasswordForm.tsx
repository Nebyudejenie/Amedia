'use client';

import { useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { PasswordStrength } from '@/components/auth/PasswordStrength';
import { api, ApiError } from '@/lib/api';
import { useZodForm } from '@/lib/use-zod-form';
import { changePasswordSchema, type ChangePasswordInput } from '@/lib/validators';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';

export function ChangePasswordForm({ onDone }: { onDone?: () => void }) {
  const addToast = useUiStore((s) => s.addToast);
  const logout = useAuthStore((s) => s.logout);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useZodForm(changePasswordSchema);

  const newPassword = watch('new_password', '');

  const onSubmit = async (data: ChangePasswordInput) => {
    setServerError(null);
    try {
      await api.post('/auth/change-password', {
        current_password: data.current_password,
        new_password: data.new_password,
      });
      addToast('Password changed — please sign in again', 'success');
      onDone?.();
      // Backend invalidates every session; route the user back to login
      setTimeout(() => void logout(), 1200);
    } catch (err) {
      setServerError(
        err instanceof ApiError && err.status === 401
          ? 'Current password is incorrect'
          : err instanceof ApiError
            ? err.detail
            : 'Something went wrong. Try again.'
      );
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      {serverError && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">
          {serverError}
        </div>
      )}

      <Input
        label="Current password *"
        showPasswordToggle
        aria-required
        autoComplete="current-password"
        error={errors.current_password?.message}
        {...register('current_password')}
      />

      <div className="space-y-2">
        <Input
          label="New password *"
          showPasswordToggle
          aria-required
          autoComplete="new-password"
          placeholder="12+ chars, uppercase, number, symbol"
          error={errors.new_password?.message}
          {...register('new_password')}
        />
        <PasswordStrength password={newPassword} />
      </div>

      <Input
        label="Confirm new password *"
        showPasswordToggle
        aria-required
        autoComplete="new-password"
        error={errors.confirm_password?.message}
        {...register('confirm_password')}
      />

      <div className="flex justify-end gap-3">
        {onDone && (
          <Button type="button" variant="secondary" onClick={onDone}>
            Cancel
          </Button>
        )}
        <Button type="submit" isLoading={isSubmitting}>
          {isSubmitting ? 'Changing…' : 'Change password'}
        </Button>
      </div>
    </form>
  );
}
