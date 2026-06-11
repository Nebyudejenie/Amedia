import { Button } from '@/components/ui/Button';

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center" role="alert">
      <svg className="h-10 w-10 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
      </svg>
      <p className="text-sm text-gray-700 dark:text-gray-300">{message}</p>
      <div className="flex items-center gap-3">
        {onRetry && (
          <Button size="sm" variant="secondary" onClick={onRetry}>
            Retry
          </Button>
        )}
        <a href="mailto:support@arada.fun" className="text-sm text-brand-600 hover:underline">
          Contact support
        </a>
      </div>
    </div>
  );
}
