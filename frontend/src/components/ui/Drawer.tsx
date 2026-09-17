import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import clsx from 'clsx';

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  side: 'left' | 'bottom';
  title?: ReactNode;
}

// Drawer (mobile off-canvas: nav and filters) — DESIGN_SPEC §6.28
export function Drawer({ open, onClose, children, side, title }: DrawerProps) {
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-drawer">
      <div className="absolute inset-0 bg-[rgba(15,23,42,0.5)]" onClick={onClose} />
      <div
        className={clsx(
          'absolute bg-white shadow-lg',
          side === 'left' && 'left-0 top-0 h-full w-[280px]',
          side === 'bottom' && 'bottom-0 left-0 right-0 max-h-[80vh] overflow-y-auto rounded-t-lg'
        )}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-3">
            <h2 className="text-section-title text-neutral-900">{title}</h2>
            <button type="button" onClick={onClose} className="rounded-md p-1 text-neutral-500 hover:bg-neutral-100" aria-label="close">
              <X size={18} />
            </button>
          </div>
        )}
        {children}
      </div>
    </div>,
    document.body
  );
}
