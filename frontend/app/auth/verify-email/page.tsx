'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/ui/Button';
import { VerificationCodeInput } from '@/components/forms/VerificationCodeInput';
import { api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';

const RESEND_COOLDOWN_SECONDS = 60;

export default function VerifyEmailPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [resendMessage, setResendMessage] = useState<string | null>(null);

  // Tick the resend cooldown
  useEffect(() => {
    if (cooldown <= 0) return;
    const id = setInterval(() => setCooldown((c) => c - 1), 1000);
    return () => clearInterval(id);
  }, [cooldown]);

  const submit = async (fullCode: string) => {
    setError(null);
    setSubmitting(true);
    try {
      await api.post('/auth/verify-email', { verification_token: fullCode });
      router.push('/dashboard?verified=1');
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? 'Invalid or expired code. Request a new one.'
          : 'Verification failed. Try again.'
      );
      setCode('');
    } finally {
      setSubmitting(false);
    }
  };

  // Auto-submit when all 6 digits are entered
  useEffect(() => {
    if (code.length === 6 && !submitting) void submit(code);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const resend = async () => {
    if (cooldown > 0 || !user?.email) return;
    setResendMessage(null);
    try {
      await api.post('/auth/resend-verification', { email: user.email });
    } finally {
      // Cooldown applies regardless — server also rate-limits (5/min/IP)
      setCooldown(RESEND_COOLDOWN_SECONDS);
      setResendMessage('A new code has been sent if your email is unverified.');
    }
  };

  return (
    <div className="space-y-6 text-center">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Verify your email</h2>
        <p className="mt-2 text-sm text-gray-500">
          We sent a 6-digit code to <b>{user?.email ?? 'your email'}</b>. Enter it below.
        </p>
      </div>

      <VerificationCodeInput value={code} onChange={setCode} disabled={submitting} error={error ?? undefined} />

      <Button
        className="w-full"
        size="lg"
        isLoading={submitting}
        disabled={code.length !== 6}
        onClick={() => submit(code)}
      >
        {submitting ? 'Verifying…' : 'Verify email'}
      </Button>

      <div className="space-y-1 text-sm">
        {resendMessage && <p className="text-green-600">{resendMessage}</p>}
        <button
          onClick={resend}
          disabled={cooldown > 0}
          className="font-medium text-brand-600 hover:text-brand-700 disabled:cursor-not-allowed disabled:text-gray-400"
        >
          {cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
        </button>
      </div>
    </div>
  );
}
