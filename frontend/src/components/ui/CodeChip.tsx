import type { ReactNode } from 'react';
import clsx from 'clsx';

// Inline "code chip" treatment — DESIGN_SPEC §1.2 Monospace Usage. Reserved
// for the four identifier-style mono fields (Employee Code, Device IP:Port,
// Device Serial Number, Raw Status Code) wherever they render as a
// standalone cell/value. Timestamps/currency/minute-day counters use
// `font-mono` only (no chip) — apply that directly at the call site.
export function CodeChip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={clsx(
        'inline-block rounded-sm bg-neutral-100 px-1.5 py-0.5 font-mono text-xs text-neutral-700',
        className
      )}
    >
      {children}
    </span>
  );
}
