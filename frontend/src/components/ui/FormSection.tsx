import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import clsx from 'clsx';

interface FormSectionProps {
  title: string;
  children: ReactNode;
  first?: boolean;
}

// Form Section — DESIGN_SPEC §6.25
export function FormSection({ title, children, first }: FormSectionProps) {
  return (
    <div className={clsx('mb-8 last:mb-0', !first && 'border-t border-neutral-200 pt-6')}>
      <h3 className="mb-2 text-group-label text-neutral-500">{title}</h3>
      <div className="flex flex-col gap-5">{children}</div>
    </div>
  );
}

// Form-level error banner — DESIGN_SPEC §6.26
export function FormErrorBanner({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-3 rounded-md border border-danger-200 bg-danger-50 px-4 py-3">
      <p className="text-sm text-danger-700">{message}</p>
      {onDismiss && (
        <button type="button" onClick={onDismiss} className="shrink-0 text-danger-600 hover:text-danger-800" aria-label="dismiss">
          <X size={16} />
        </button>
      )}
    </div>
  );
}

// Sticky footer bar for T3 form pages — DESIGN_SPEC §3 (Page Templates, T3)
export function FormFooterBar({ children }: { children: ReactNode }) {
  return (
    <div className="sticky bottom-0 left-0 right-0 mt-8 flex justify-end gap-3 border-t border-neutral-200 bg-white px-6 py-3">
      {children}
    </div>
  );
}
