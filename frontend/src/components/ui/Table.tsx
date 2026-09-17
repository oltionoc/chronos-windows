import type { ReactNode } from 'react';
import { ChevronLeft, ChevronRight, Inbox } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { Button } from './Button';
import { Select } from './Select';

export interface Column<T> {
  key: string;
  header: string;
  align?: 'left' | 'right';
  render: (row: T) => ReactNode;
  headerClassName?: string;
  cellClassName?: string;
}

export interface MobileCard {
  title: ReactNode;
  subtitle?: ReactNode;
  badge?: ReactNode;
  rows: { label: string; value: ReactNode }[];
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  loading?: boolean;
  onRowClick?: (row: T) => void;
  emptyIcon?: ReactNode;
  emptyMessage: string;
  hasActiveFilters?: boolean;
  onClearFilters?: () => void;
  mobileCard: (row: T) => MobileCard;
  footer?: ReactNode;
  rowClassName?: (row: T) => string;
}

// Table / Data Grid — DESIGN_SPEC §6.10
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  onRowClick,
  emptyIcon,
  emptyMessage,
  hasActiveFilters,
  onClearFilters,
  mobileCard,
  footer,
  rowClassName,
}: DataTableProps<T>) {
  const { t } = useTranslation();
  const isEmpty = !loading && rows.length === 0;

  const emptyBlock = (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
      <div className="text-neutral-400">{emptyIcon ?? <Inbox size={24} />}</div>
      <p className="text-body-muted text-neutral-500">{emptyMessage}</p>
      {hasActiveFilters && onClearFilters && (
        <button type="button" onClick={onClearFilters} className="text-body text-primary-600 hover:underline">
          {t('common.clearFilters')}
        </button>
      )}
    </div>
  );

  return (
    <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-sm">
      {/* Desktop / tablet table (>=640px) */}
      <div className="hidden sm:block sm:overflow-x-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10 bg-neutral-50">
            <tr className="border-b border-neutral-200">
              {columns.map((col, i) => (
                <th
                  key={col.key}
                  className={clsx(
                    'whitespace-nowrap px-4 py-2.5 text-left text-group-label text-neutral-500',
                    col.align === 'right' && 'text-right',
                    i === 0 && columns.length > 3 && 'sticky left-0 z-10 border-r border-neutral-200 bg-neutral-50',
                    col.headerClassName
                  )}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-neutral-200">
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-2.5">
                      <div className="h-4 w-3/4 animate-pulse rounded-sm bg-neutral-100" />
                    </td>
                  ))}
                </tr>
              ))}
            {!loading &&
              rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={clsx(
                    'group border-b border-neutral-200 last:border-b-0 hover:bg-neutral-50',
                    onRowClick && 'cursor-pointer',
                    rowClassName?.(row)
                  )}
                >
                  {columns.map((col, i) => (
                    <td
                      key={col.key}
                      className={clsx(
                        'px-4 py-2.5 text-body text-neutral-800',
                        col.align === 'right' && 'text-right tabular-nums',
                        i === 0 && columns.length > 3 && 'sticky left-0 z-[1] border-r border-neutral-200 bg-white group-hover:bg-neutral-50',
                        col.cellClassName
                      )}
                    >
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
        {isEmpty && emptyBlock}
      </div>

      {/* Mobile card list (<640px) */}
      <div className="divide-y divide-neutral-200 sm:hidden">
        {loading &&
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="p-3">
              <div className="mb-2 h-4 w-1/2 animate-pulse rounded-sm bg-neutral-100" />
              <div className="h-3 w-1/3 animate-pulse rounded-sm bg-neutral-100" />
            </div>
          ))}
        {!loading &&
          rows.map((row) => {
            const card = mobileCard(row);
            return (
              <div
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={clsx('rounded-md p-3', onRowClick && 'cursor-pointer active:bg-neutral-50', rowClassName?.(row))}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-body font-medium text-neutral-800">{card.title}</div>
                    {card.subtitle && <div className="truncate text-caption text-neutral-500">{card.subtitle}</div>}
                  </div>
                  {card.badge && <div className="shrink-0">{card.badge}</div>}
                </div>
                {card.rows.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {card.rows.map((r, i) => (
                      <div key={i} className="flex justify-between gap-4 text-caption">
                        <span className="text-neutral-500">{r.label}</span>
                        <span className="text-right text-neutral-800">{r.value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        {isEmpty && emptyBlock}
      </div>
      {footer}
    </div>
  );
}

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

// Pagination Footer — DESIGN_SPEC §6.11
export function Pagination({ page, pageSize, total, onPageChange, onPageSizeChange }: PaginationProps) {
  const { t } = useTranslation();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex flex-col gap-3 border-t border-neutral-200 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <Select
        value={pageSize}
        onChange={(e) => onPageSizeChange(Number(e.target.value))}
        options={[10, 25, 50, 100].map((n) => ({ value: n, label: String(n) }))}
        containerClassName="w-24"
      />
      <div className="flex items-center gap-3">
        <span className="text-caption text-neutral-500">{t('table.showing', { from, to, total })}</span>
        <Button
          variant="ghost"
          size="sm"
          iconOnly
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          iconOnly
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
