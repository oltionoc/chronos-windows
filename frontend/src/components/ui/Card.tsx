import type { ReactNode } from 'react';
import clsx from 'clsx';
import type { LucideIcon } from 'lucide-react';

interface CardProps {
  title?: ReactNode;
  headerAction?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  bodyClassName?: string;
}

// Card / Panel — DESIGN_SPEC §6.13
export function Card({ title, headerAction, children, footer, className, bodyClassName }: CardProps) {
  return (
    <div className={clsx('rounded-lg border border-neutral-200 bg-white shadow-sm', className)}>
      {(title || headerAction) && (
        <div className="flex items-center justify-between border-b border-neutral-200 px-6 py-4">
          <h2 className="text-section-title text-neutral-900">{title}</h2>
          {headerAction}
        </div>
      )}
      <div className={clsx('p-6', bodyClassName)}>{children}</div>
      {footer && <div className="border-t border-neutral-200 px-6 py-3">{footer}</div>}
    </div>
  );
}

type KpiColor = 'success' | 'warning' | 'danger' | 'violet';

const kpiColorMap: Record<KpiColor, { cardBg: string; border: string; text: string; dot: string }> = {
  success: { cardBg: 'bg-success-50', border: 'border-success-100', text: 'text-success-600', dot: 'bg-success-500' },
  warning: { cardBg: 'bg-warning-50', border: 'border-warning-100', text: 'text-warning-600', dot: 'bg-warning-500' },
  danger: { cardBg: 'bg-danger-50', border: 'border-danger-100', text: 'text-danger-600', dot: 'bg-danger-500' },
  violet: { cardBg: 'bg-violet-50', border: 'border-violet-100', text: 'text-violet-600', dot: 'bg-violet-500' },
};

interface KpiCardProps {
  icon: LucideIcon;
  value: ReactNode;
  label: string;
  color: KpiColor;
  onClick?: () => void;
  loading?: boolean;
  subValue?: ReactNode;
  subLabel?: string;
}

// KPI Card — DESIGN_SPEC §6.14 Revision 5: tinted-background style. Every
// card renders the same slots (icon+value row, label, divider, sub-line) so
// they stay structurally uniform whether or not a given card has real
// secondary data — a card with nothing to add shows an em-dash rather than
// omitting the row, so the KPI strip never has one visually taller/shorter
// card among the rest.
export function KpiCard({ icon: Icon, value, label, color, onClick, loading, subValue, subLabel }: KpiCardProps) {
  const c = kpiColorMap[color];
  const content = (
    <div className={clsx('rounded-lg border p-5 shadow-sm', c.cardBg, c.border)}>
      <div className="flex items-start justify-between gap-2">
        <Icon size={20} className={clsx('shrink-0', c.text)} />
        {loading ? (
          <div className="h-9 w-14 animate-pulse rounded-sm bg-white/60" />
        ) : (
          <div className="font-mono text-kpi tabular-nums text-neutral-900">{value}</div>
        )}
      </div>
      <div className="mt-2 text-caption text-neutral-600">{label}</div>
      <div className={clsx('mt-2 flex items-center gap-1.5 border-t pt-2 text-caption text-neutral-500', c.border)}>
        {loading ? (
          <div className="h-3 w-20 animate-pulse rounded-sm bg-white/60" />
        ) : subValue !== undefined ? (
          <>
            <span className={clsx('h-1.5 w-1.5 shrink-0 rounded-full', c.dot)} />
            <span className="font-mono tabular-nums text-neutral-700">{subValue}</span>
            <span>{subLabel}</span>
          </>
        ) : (
          <span className="text-neutral-400">–</span>
        )}
      </div>
    </div>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="w-full rounded-lg text-left transition-shadow hover:shadow-md"
      >
        {content}
      </button>
    );
  }
  return content;
}
