import { Suspense } from 'react';
import type { Metadata } from 'next';
import { LoginForm } from '@/components/auth/LoginForm';

export const metadata: Metadata = { title: 'Sign in' };

export default function LoginPage() {
  return (
    <>
      <h2 className="mb-6 text-xl font-semibold text-gray-900 dark:text-white">Sign in</h2>
      <Suspense>
        <LoginForm />
      </Suspense>
    </>
  );
}
