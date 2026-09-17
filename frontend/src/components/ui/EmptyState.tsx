import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}

// Empty State (standalone, whole-page) — DESIGN_SPEC §6.23
export function EmptyState({ icon: Icon, title, subtitle, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <Icon size={48} className="mb-4 text-neutral-300" />
      <p className="text-section-title text-neutral-900">{title}</p>
      {subtitle && <p className="mt-1 text-body-muted text-neutral-500">{subtitle}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
