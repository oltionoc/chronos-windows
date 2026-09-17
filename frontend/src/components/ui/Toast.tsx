import { createContext, useCallback, useContext, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import clsx from 'clsx';

type ToastVariant = 'success' | 'error' | 'warning' | 'info';

interface ToastItem {
  id: number;
  variant: ToastVariant;
  message: string;
}

interface ToastContextValue {
  showToast: (variant: ToastVariant, message: string) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

// `border` is a literal Tailwind class (not derived from another class via
// string replacement) so the JIT compiler's static scan can find it — a
// computed class name like `'bg-success-600'.replace('bg-', 'border-')` is
// invisible to Tailwind's scanner and gets purged from the production build,
// leaving the toast's left accent bar colorless.
const variantConfig: Record<
  ToastVariant,
  { border: string; icon: typeof CheckCircle2; iconColor: string; autoDismiss: boolean }
> = {
  success: { border: 'border-success-600', icon: CheckCircle2, iconColor: 'text-success-600', autoDismiss: true },
  info: { border: 'border-primary-600', icon: Info, iconColor: 'text-primary-600', autoDismiss: true },
  warning: { border: 'border-warning-600', icon: AlertTriangle, iconColor: 'text-warning-600', autoDismiss: false },
  error: { border: 'border-danger-600', icon: AlertCircle, iconColor: 'text-danger-600', autoDismiss: false },
};

// Toast / Notification — DESIGN_SPEC §6.19
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const showToast = useCallback(
    (variant: ToastVariant, message: string) => {
      const id = ++idRef.current;
      setToasts((t) => [...t, { id, variant, message }]);
      if (variantConfig[variant].autoDismiss) {
        setTimeout(() => dismiss(id), 4000);
      }
    },
    [dismiss]
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {createPortal(
        // `left-4` below `sm` keeps the stack bounded by the viewport on a
        // narrow phone: with `right-4` alone the shrink-to-fit container only
        // has (100vw - 16px) to work with, and the toast's 320px minimum then
        // hung 16px off the left edge of a 320px screen, clipping the variant
        // accent bar and half the icon. From `sm` up, the original
        // shrink-to-fit-from-the-right behaviour is restored unchanged.
        <div className="fixed left-4 right-4 top-4 z-toast flex flex-col items-end gap-3 sm:left-auto">
          {toasts.map((toast) => {
            const cfg = variantConfig[toast.variant];
            const Icon = cfg.icon;
            return (
              <div
                key={toast.id}
                className={clsx(
                  'flex w-full max-w-[420px] items-start gap-3 rounded-md border-l-4 bg-white px-4 py-3 shadow-md sm:w-auto sm:min-w-[320px]',
                  cfg.border
                )}
              >
                <Icon size={18} className={clsx('mt-0.5 shrink-0', cfg.iconColor)} />
                <p className="flex-1 text-body text-neutral-800">{toast.message}</p>
                <button
                  type="button"
                  onClick={() => dismiss(toast.id)}
                  className="shrink-0 text-neutral-400 hover:text-neutral-600"
                  aria-label="dismiss"
                >
                  <X size={16} />
                </button>
              </div>
            );
          })}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}
