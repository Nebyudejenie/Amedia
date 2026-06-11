'use client';

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import { resetPasswordSchema, type ResetPasswordInput } from '@/lib/validators';
import { authApi, ApiError } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { PasswordStrength } from '@/components/auth/PasswordStrength';

function ResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get('token') ?? '';
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordInput>({ resolver: zodResolver(resetPasswordSchema) });

  const password = watch('password', '');

  const onSubmit = async (data: ResetPasswordInput) => {
    setServerError(null);
    try {
      await authApi.resetPassword(token, data.password);
      router.push('/auth/login?reset=success');
    } catch (err) {
      setServerError(
        err instanceof ApiError && err.status === 401
          ? 'This reset link is invalid or has expired. Request a new one.'
          : 'Something went wrong. Try again.'
      );
    }
  };

  if (!token) {
    return (
      <div className="space-y-4 text-center">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Invalid link</h2>
        <p className="text-sm text-gray-500">This password reset link is missing its token.</p>
        <Link href="/auth/forgot-password" className="text-sm font-medium text-brand-600">
          Request a new link
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Choose a new password</h2>

      {serverError && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">
          {serverError}
        </div>
      )}

      <div className="space-y-2">
        <Input
          label="New password"
          showPasswordToggle
          autoComplete="new-password"
          error={errors.password?.message}
          {...register('password')}
        />
        <PasswordStrength password={password} />
      </div>

      <Input
        label="Confirm new password"
        showPasswordToggle
        autoComplete="new-password"
        error={errors.confirmPassword?.message}
        {...register('confirmPassword')}
      />

      <Button type="submit" isLoading={isSubmitting} className="w-full" size="lg">
        Reset password
      </Button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPasswordForm />
    </Suspense>
  );
}
