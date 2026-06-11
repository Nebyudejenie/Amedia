'use client';

import { useUiStore } from '@/stores/ui';

const styles = {
  success: 'bg-green-600',
  error: 'bg-red-600',
  info: 'bg-gray-800',
};

export function ToastContainer() {
  const { toasts, removeToast } = useUiStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm text-white shadow-lg ${styles[toast.type]}`}
        >
          <span>{toast.message}</span>
          <button onClick={() => removeToast(toast.id)} aria-label="Dismiss" className="opacity-70 hover:opacity-100">
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
