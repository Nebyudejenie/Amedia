'use client';

import { forwardRef, useState, type TextareaHTMLAttributes } from 'react';

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  /** Show "123 / 5000" counter under the field. */
  maxChars?: number;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, maxChars, id, onChange, className = '', ...props }, ref) => {
    const inputId = id ?? props.name;
    const [count, setCount] = useState(
      typeof props.defaultValue === 'string' ? props.defaultValue.length : 0
    );

    return (
      <div className="space-y-1">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={inputId}
          rows={4}
          maxLength={maxChars}
          aria-invalid={!!error}
          aria-describedby={error ? `${inputId}-error` : undefined}
          onChange={(e) => {
            setCount(e.target.value.length);
            onChange?.(e);
          }}
          className={`w-full rounded-lg border px-3 py-2 text-sm shadow-sm transition-colors
            placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500
            dark:bg-gray-800 dark:text-white
            ${error ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'} ${className}`}
          {...props}
        />
        <div className="flex justify-between">
          {error ? (
            <p id={`${inputId}-error`} role="alert" className="text-sm text-red-600">
              {error}
            </p>
          ) : (
            <span />
          )}
          {maxChars && (
            <span className={`text-xs ${count > maxChars * 0.9 ? 'text-orange-500' : 'text-gray-400'}`}>
              {count} / {maxChars}
            </span>
          )}
        </div>
      </div>
    );
  }
);
Textarea.displayName = 'Textarea';
