import { forwardRef, useState, type InputHTMLAttributes } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  showPasswordToggle?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, showPasswordToggle, type, id, className = '', ...props }, ref) => {
    const [visible, setVisible] = useState(false);
    const inputType = showPasswordToggle ? (visible ? 'text' : 'password') : type;
    const inputId = id ?? props.name;

    return (
      <div className="space-y-1">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            {label}
          </label>
        )}
        <div className="relative">
          <input
            ref={ref}
            id={inputId}
            type={inputType}
            aria-invalid={!!error}
            aria-describedby={error ? `${inputId}-error` : undefined}
            className={`w-full rounded-lg border px-3 py-2 text-sm shadow-sm transition-colors
              placeholder:text-gray-400
              focus:outline-none focus:ring-2 focus:ring-brand-500
              dark:bg-gray-800 dark:text-white
              ${error ? 'border-red-500' : 'border-gray-300 dark:border-gray-600'}
              ${showPasswordToggle ? 'pr-10' : ''} ${className}`}
            {...props}
          />
          {showPasswordToggle && (
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setVisible(!visible)}
              aria-label={visible ? 'Hide password' : 'Show password'}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              {visible ? (
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                </svg>
              ) : (
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          )}
        </div>
        {error && (
          <p id={`${inputId}-error`} role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
    );
  }
);
Input.displayName = 'Input';
