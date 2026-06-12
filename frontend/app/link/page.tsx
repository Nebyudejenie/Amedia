'use client';

/** Telegram account linking: /link?token=XXXXXX (from the bot's /start). */
import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';

import { api, ApiError } from '@/lib/api';
import { Spinner } from '@/components/ui/Spinner';

function LinkInner() {
  const token = useSearchParams().get('token') ?? '';
  const [state, setState] = useState<'working' | 'done' | 'error'>('working');
  const [message, setMessage] = useState('Linking your Telegram account…');

  useEffect(() => {
    if (!token) {
      setState('error');
      setMessage('Missing link token. Send /start to the bot for a fresh link.');
      return;
    }
    api
      .post('/api/v1/telegram/link', { token })
      .then(() => {
        setState('done');
        setMessage('Telegram account linked! You can now /submit articles from the bot.');
      })
      .catch((err) => {
        setState('error');
        setMessage(
          err instanceof ApiError && err.status === 401
            ? 'This link is invalid or expired. Send /start to the bot for a new one.'
            : err instanceof ApiError && err.status === 409
              ? 'That Telegram account is already linked to a different Arada account.'
              : 'Something went wrong. Try again.'
        );
      });
  }, [token]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 p-4 dark:bg-gray-900">
      <div className="w-full max-w-md space-y-4 rounded-2xl bg-white p-8 text-center shadow-xl dark:bg-gray-800">
        <div className="text-4xl">{state === 'working' ? <Spinner className="mx-auto h-8 w-8" /> : state === 'done' ? '🎉' : '⚠️'}</div>
        <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
          {state === 'done' ? 'Linked!' : state === 'error' ? 'Linking failed' : 'One moment…'}
        </h1>
        <p className="text-sm text-gray-500">{message}</p>
        {state !== 'working' && (
          <Link
            href="/dashboard"
            className="inline-block rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Go to dashboard
          </Link>
        )}
      </div>
    </main>
  );
}

export default function LinkPage() {
  return (
    <Suspense>
      <LinkInner />
    </Suspense>
  );
}
