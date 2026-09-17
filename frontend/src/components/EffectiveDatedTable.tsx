import { useTranslation } from 'react-i18next';
import { SlidersHorizontal } from 'lucide-react';
import clsx from 'clsx';
import { DataTable } from './ui/Table';
import type { Column, MobileCard } from './ui/Table';
import { CurrentBadge } from './ui/Badge';
import { formatDate } from '../lib/format';

interface EffectiveDatedRow {
  id: number;
  location_name?: string;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
}

function isCurrent(row: EffectiveDatedRow): boolean {
  const todayStr = new Date().toISOString().slice(0, 10);
  return row.is_active && row.effective_from <= todayStr && (!row.effective_to || row.effective_to >= todayStr);
}

// Shared "Effective-Dated Config List" table pattern — DESIGN_SPEC §5.21,
// used by /config/penalties, /config/overtime, /config/absence-rule.
export function EffectiveDatedTable<T extends EffectiveDatedRow>({
  rows,
  loading,
  extraColumns,
  onRowClick,
  mobileExtraRows,
  emptyMessage,
}: {
  rows: T[];
  loading?: boolean;
  extraColumns: Column<T>[];
  onRowClick?: (row: T) => void;
  mobileExtraRows: (row: T) => MobileCard['rows'];
  emptyMessage: string;
}) {
  const { t } = useTranslation();
  const sorted = [...rows].sort((a, b) => b.effective_from.localeCompare(a.effective_from));

  const columns: Column<T>[] = [
    {
      key: 'current',
      header: '',
      render: (r) => (isCurrent(r) ? <CurrentBadge /> : null),
    },
    { key: 'effectiveFrom', header: t('config.effectiveFrom'), render: (r) => <span className="font-mono">{formatDate(r.effective_from)}</span> },
    { key: 'effectiveTo', header: t('config.effectiveTo'), render: (r) => (r.effective_to ? <span className="font-mono">{formatDate(r.effective_to)}</span> : '–') },
    { key: 'location', header: t('config.location'), render: (r) => r.location_name ?? t('common.all') },
    ...extraColumns,
  ];

  return (
    <DataTable
      columns={columns}
      rows={sorted}
      rowKey={(r) => r.id}
      loading={loading}
      onRowClick={onRowClick}
      emptyIcon={<SlidersHorizontal size={24} />}
      emptyMessage={emptyMessage}
      rowClassName={(r) => clsx(isCurrent(r) ? 'bg-success-50' : 'text-neutral-500')}
      mobileCard={(r) => ({
        title: <span className="font-mono">{formatDate(r.effective_from)}</span>,
        subtitle: r.location_name ?? t('common.all'),
        badge: isCurrent(r) ? <CurrentBadge /> : undefined,
        rows: mobileExtraRows(r),
      })}
    />
  );
}
