'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import { registerSchema, type RegisterInput } from '@/lib/validators';
import { authApi, ApiError } from '@/lib/api';
import { useEmailAvailability } from '@/lib/hooks';
import { useAuthStore } from '@/stores/auth';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { PasswordStrength } from '@/components/auth/PasswordStrength';

export function RegisterForm() {
  const router = useRouter();
  const setUser = useAuthStore((s) => s.setUser);
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting, isValid },
  } = useForm<RegisterInput>({
    resolver: zodResolver(registerSchema),
    mode: 'onChange',
  });

  const password = watch('password', '');
  const email = watch('email', '');
  const emailStatus = useEmailAvailability(email);

  const onSubmit = async (data: RegisterInput) => {
    setServerError(null);
    try {
      const { user } = await authApi.register({
        email: data.email,
        password: data.password,
        full_name: data.full_name,
      });
      setUser(user);
      router.push('/dashboard');
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(
          err.status === 409 ? 'An account with this email already exists.' : err.detail
        );
      } else {
        setServerError('Something went wrong. Try again.');
      }
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
        label="Full name"
        autoComplete="name"
        placeholder="Ada Lovelace"
        error={errors.full_name?.message}
        {...register('full_name')}
      />

      <div className="space-y-1">
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          error={errors.email?.message ?? (emailStatus === 'taken' ? 'Email already in use' : undefined)}
          {...register('email')}
        />
        {!errors.email && emailStatus === 'checking' && (
          <p className="text-sm text-gray-400">Checking availability…</p>
        )}
        {!errors.email && emailStatus === 'available' && (
          <p className="flex items-center gap-1 text-sm text-green-600" role="status">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            Email available
          </p>
        )}
      </div>

      <div className="space-y-2">
        <Input
          label="Password"
          showPasswordToggle
          autoComplete="new-password"
          placeholder="12+ chars, uppercase, number, symbol"
          error={errors.password?.message}
          {...register('password')}
        />
        <PasswordStrength password={password} />
      </div>

      <Input
        label="Confirm password"
        showPasswordToggle
        autoComplete="new-password"
        error={errors.confirmPassword?.message}
        {...register('confirmPassword')}
      />

      <label className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-300">
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
          {...register('acceptTerms')}
        />
        <span>
          I agree to the{' '}
          <a href="/terms" target="_blank" className="font-medium text-brand-600 hover:underline">
            Terms of Service
          </a>{' '}
          and{' '}
          <a href="/privacy" target="_blank" className="font-medium text-brand-600 hover:underline">
            Privacy Policy
          </a>
        </span>
      </label>
      {errors.acceptTerms && (
        <p role="alert" className="text-sm text-red-600">
          {errors.acceptTerms.message}
        </p>
      )}

      <Button
        type="submit"
        isLoading={isSubmitting}
        disabled={!isValid || emailStatus === 'taken'}
        className="w-full"
        size="lg"
      >
        {isSubmitting ? 'Creating account…' : 'Create account'}
      </Button>

      <p className="text-center text-sm text-gray-500">
        Already have an account?{' '}
        <Link href="/auth/login" className="font-medium text-brand-600 hover:text-brand-700">
          Sign in
        </Link>
      </p>
    </form>
  );
}
