'use client';

import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  destructive = false,
  isLoading = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  destructive?: boolean;
  isLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal open={open} onClose={onCancel} title={title}>
      <p className="text-sm text-gray-600 dark:text-gray-300">{message}</p>
      <div className="mt-6 flex justify-end gap-3">
        <Button variant="secondary" onClick={onCancel} disabled={isLoading}>
          Cancel
        </Button>
        <Button variant={destructive ? 'danger' : 'primary'} onClick={onConfirm} isLoading={isLoading}>
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
