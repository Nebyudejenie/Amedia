import type { Metadata } from 'next';
import { RegisterForm } from '@/components/auth/RegisterForm';

export const metadata: Metadata = { title: 'Create account' };

export default function RegisterPage() {
  return (
    <>
      <h2 className="mb-6 text-xl font-semibold text-gray-900 dark:text-white">Create your account</h2>
      <RegisterForm />
    </>
  );
}
