'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import { loginSchema, type LoginInput } from '@/lib/validators';
import { authApi, ApiError } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setUser = useAuthStore((s) => s.setUser);
  const [serverError, setServerError] = useState<string | null>(null);

  const sessionExpired = searchParams.get('expired') === '1';
  const nextPath = searchParams.get('next') ?? '/dashboard';

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { rememberMe: false },
  });

  const onSubmit = async (data: LoginInput) => {
    setServerError(null);
    try {
      const { user } = await authApi.login(data);
      setUser(user);
      router.push(nextPath);
      router.refresh();
    } catch (err) {
      setServerError(err instanceof ApiError ? err.detail : 'Something went wrong. Try again.');
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      {sessionExpired && !serverError && (
        <div className="rounded-lg bg-yellow-50 p-3 text-sm text-yellow-800" role="alert">
          Your session expired. Please sign in again.
        </div>
      )}

      {serverError && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">
          {serverError}
        </div>
      )}

      <Input
        label="Email"
        type="email"
        autoComplete="email"
        placeholder="you@example.com"
        error={errors.email?.message}
        {...register('email')}
      />

      <Input
        label="Password"
        showPasswordToggle
        autoComplete="current-password"
        placeholder="••••••••••••"
        error={errors.password?.message}
        {...register('password')}
      />

      <div className="flex items-center justify-between text-sm">
        <label className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
            {...register('rememberMe')}
          />
          Remember me
        </label>
        <Link href="/auth/forgot-password" className="font-medium text-brand-600 hover:text-brand-700">
          Forgot password?
        </Link>
      </div>

      <Button type="submit" isLoading={isSubmitting} className="w-full" size="lg">
        Sign in
      </Button>

      <p className="text-center text-sm text-gray-500">
        No account?{' '}
        <Link href="/auth/register" className="font-medium text-brand-600 hover:text-brand-700">
          Create one
        </Link>
      </p>
    </form>
  );
}
