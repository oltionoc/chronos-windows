import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, X } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { Button } from './Button';
import type { ButtonVariant } from './Button';

type ModalSize = 'sm' | 'md' | 'lg';

const sizeClasses: Record<ModalSize, string> = {
  sm: 'max-w-[400px]',
  md: 'max-w-[560px]',
  lg: 'max-w-[720px]',
};

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: ModalSize;
  dismissible?: boolean;
}

// Modal / Dialog — DESIGN_SPEC §6.17
export function Modal({ open, onClose, title, children, footer, size = 'md', dismissible = true }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-modal-backdrop flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-[rgba(15,23,42,0.5)]"
        onClick={dismissible ? onClose : onClose}
      />
      <div
        className={clsx(
          'relative z-modal w-full rounded-lg bg-white shadow-lg',
          sizeClasses[size]
        )}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between border-b border-neutral-200 px-6 py-4">
          <h2 className="text-section-title text-neutral-900">{title}</h2>
          <div className="flex items-center gap-1">
            <span className="rounded-sm border border-neutral-200 bg-neutral-100 px-1.5 py-0.5 font-mono text-xs text-neutral-400">
              Esc
            </span>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
              aria-label="close"
            >
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-6 py-6">{children}</div>
        {footer && <div className="border-t border-neutral-200 px-6 py-3">{footer}</div>}
      </div>
    </div>,
    document.body
  );
}

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: ReactNode;
  description: ReactNode;
  confirmVariant?: ButtonVariant;
  destructive?: boolean;
  loading?: boolean;
  extraContent?: ReactNode;
}

// Confirmation Dialog — DESIGN_SPEC §6.18
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmVariant,
  destructive = true,
  loading = false,
  extraContent,
}: ConfirmDialogProps) {
  const { t } = useTranslation();
  const resolvedVariant: ButtonVariant = confirmVariant ?? (destructive ? 'danger' : 'primary');

  return (
    <Modal open={open} onClose={onClose} title={title} size="sm" dismissible={false}>
      <div className="flex flex-col items-center text-center">
        <div
          className={clsx(
            'mb-4 flex h-12 w-12 items-center justify-center rounded-full',
            destructive ? 'bg-danger-100' : 'bg-warning-100'
          )}
        >
          <AlertTriangle size={24} className={destructive ? 'text-danger-600' : 'text-warning-600'} />
        </div>
        <p className="text-body-muted text-neutral-500">{description}</p>
        {extraContent && <div className="mt-4 w-full text-left">{extraContent}</div>}
      </div>
      <div className="mt-6 flex justify-end gap-3">
        <Button variant="secondary" onClick={onClose}>
          {t('common.cancel')}
        </Button>
        <Button variant={resolvedVariant} onClick={onConfirm} loading={loading}>
          {t('common.confirm')}
        </Button>
      </div>
    </Modal>
  );
}
