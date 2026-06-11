'use client';

import { passwordStrength } from '@/lib/validators';

export function PasswordStrength({ password }: { password: string }) {
  const { score, label, color } = passwordStrength(password);

  if (!password) return null;

  return (
    <div className="space-y-1" aria-live="polite">
      <div className="flex gap-1">
        {[1, 2, 3, 4].map((step) => (
          <div
            key={step}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              score >= step ? color : 'bg-gray-200 dark:bg-gray-700'
            }`}
          />
        ))}
      </div>
      <p className="text-xs text-gray-500">{label}</p>
    </div>
  );
}
