'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import { forgotPasswordSchema, type ForgotPasswordInput } from '@/lib/validators';
import { authApi } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';

export default function ForgotPasswordPage() {
  const [submitted, setSubmitted] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordInput>({ resolver: zodResolver(forgotPasswordSchema) });

  const onSubmit = async (data: ForgotPasswordInput) => {
    // Always show success — never reveal whether the email exists
    await authApi.forgotPassword(data.email).catch(() => {});
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div className="space-y-4 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
          <svg className="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Check your email</h2>
        <p className="text-sm text-gray-500">
          If an account exists for that address, we sent a password reset link. It expires in 24 hours.
        </p>
        <Link href="/auth/login" className="inline-block text-sm font-medium text-brand-600 hover:text-brand-700">
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Reset your password</h2>
      <p className="text-sm text-gray-500">
        Enter your email and we&apos;ll send you a reset link.
      </p>
      <Input
        label="Email"
        type="email"
        autoComplete="email"
        placeholder="you@example.com"
        error={errors.email?.message}
        {...register('email')}
      />
      <Button type="submit" isLoading={isSubmitting} className="w-full" size="lg">
        Send reset link
      </Button>
      <p className="text-center text-sm">
        <Link href="/auth/login" className="font-medium text-brand-600 hover:text-brand-700">
          Back to sign in
        </Link>
      </p>
    </form>
  );
}
