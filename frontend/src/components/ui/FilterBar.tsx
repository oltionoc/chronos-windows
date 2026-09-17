import type { ReactNode } from 'react';
import { useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from './Button';
import { Drawer } from './Drawer';

interface FilterBarProps {
  children: ReactNode;
  hasActiveFilters?: boolean;
  onClearFilters?: () => void;
}

// Filter Bar — DESIGN_SPEC §6.12. Desktop/tablet: inline row. Mobile (<640px):
// collapses into a "Filters" button opening a bottom Drawer (§4.1).
export function FilterBar({ children, hasActiveFilters, onClearFilters }: FilterBarProps) {
  const { t } = useTranslation();
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <>
      <div className="hidden rounded-lg border border-neutral-200 bg-white p-4 sm:flex sm:flex-wrap sm:items-end sm:gap-3">
        {children}
        {hasActiveFilters && onClearFilters && (
          <button
            type="button"
            onClick={onClearFilters}
            className="ml-auto self-center text-body text-primary-600 hover:underline"
          >
            {t('common.clearFilters')}
          </button>
        )}
      </div>

      <div className="sm:hidden">
        <Button variant="secondary" leftIcon={<SlidersHorizontal size={16} />} onClick={() => setDrawerOpen(true)} className="w-full justify-center">
          {t('common.search')}
        </Button>
      </div>

      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} side="bottom" title={t('common.search')}>
        <div className="flex flex-col gap-4 p-4">
          {children}
          <div className="flex gap-3">
            {hasActiveFilters && onClearFilters && (
              <Button variant="secondary" className="flex-1" onClick={onClearFilters}>
                {t('common.clearFilters')}
              </Button>
            )}
            <Button className="flex-1" onClick={() => setDrawerOpen(false)}>
              {t('common.confirm')}
            </Button>
          </div>
        </div>
      </Drawer>
    </>
  );
}

// Date Range picker (two native date inputs, en-dash separator) — DESIGN_SPEC §6.12
export function DateRangeInput({
  from,
  to,
  onFromChange,
  onToChange,
  fromLabel,
  toLabel,
}: {
  from: string;
  to: string;
  onFromChange: (v: string) => void;
  onToChange: (v: string) => void;
  fromLabel?: string;
  toLabel?: string;
}) {
  return (
    <div className="flex items-end gap-2">
      <div>
        {fromLabel && <label className="mb-1.5 block text-label text-neutral-700">{fromLabel}</label>}
        <input
          type="date"
          value={from}
          onChange={(e) => onFromChange(e.target.value)}
          className="h-9 rounded-md border border-neutral-300 bg-white px-3 text-body text-neutral-800 transition-[border-color] duration-100 ease-out hover:border-neutral-400 focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600 focus:ring-offset-0"
        />
      </div>
      <span className="mb-2 text-neutral-400">–</span>
      <div>
        {toLabel && <label className="mb-1.5 block text-label text-neutral-700">{toLabel}</label>}
        <input
          type="date"
          value={to}
          onChange={(e) => onToChange(e.target.value)}
          className="h-9 rounded-md border border-neutral-300 bg-white px-3 text-body text-neutral-800 transition-[border-color] duration-100 ease-out hover:border-neutral-400 focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600 focus:ring-offset-0"
        />
      </div>
    </div>
  );
}
