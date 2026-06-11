'use client';

/** Six single-digit inputs with auto-advance, backspace, and paste support. */
import { useRef } from 'react';

interface VerificationCodeInputProps {
  value: string;
  onChange: (code: string) => void;
  disabled?: boolean;
  error?: string;
}

const LENGTH = 6;

export function VerificationCodeInput({
  value,
  onChange,
  disabled,
  error,
}: VerificationCodeInputProps) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length: LENGTH }, (_, i) => value[i] ?? '');

  const setDigit = (index: number, digit: string) => {
    const next = digits.slice();
    next[index] = digit;
    onChange(next.join(''));
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-center gap-2" role="group" aria-label="Verification code">
        {digits.map((digit, i) => (
          <input
            key={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            inputMode="numeric"
            maxLength={1}
            value={digit}
            disabled={disabled}
            aria-label={`Digit ${i + 1} of ${LENGTH}`}
            aria-invalid={!!error}
            onChange={(e) => {
              const char = e.target.value.replace(/\D/g, '').slice(-1);
              setDigit(i, char);
              if (char && i < LENGTH - 1) refs.current[i + 1]?.focus();
            }}
            onKeyDown={(e) => {
              if (e.key === 'Backspace' && !digit && i > 0) {
                refs.current[i - 1]?.focus();
                setDigit(i - 1, '');
              }
              if (e.key === 'ArrowLeft' && i > 0) refs.current[i - 1]?.focus();
              if (e.key === 'ArrowRight' && i < LENGTH - 1) refs.current[i + 1]?.focus();
            }}
            onPaste={(e) => {
              e.preventDefault();
              const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, LENGTH);
              if (pasted) {
                onChange(pasted.padEnd(value.length > pasted.length ? value.length : 0, ''));
                refs.current[Math.min(pasted.length, LENGTH - 1)]?.focus();
              }
            }}
            className={`h-12 w-10 rounded-lg border text-center text-lg font-semibold shadow-sm
              focus:outline-none focus:ring-2 focus:ring-brand-500
              disabled:opacity-50 dark:bg-gray-800 dark:text-white
              ${error ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'}`}
          />
        ))}
      </div>
      {error && (
        <p role="alert" className="text-center text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
