import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Wallet, Plus, Trash2 } from 'lucide-react';
import { payrollApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { FilterBar } from '../../components/ui/FilterBar';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { ConfirmDialog } from '../../components/ui/Modal';
import { PayrollStatusBadge } from '../../components/ui/Badge';
import { formatCurrency } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { PayrollRun, PayrollRunStatus } from '../../api/types';

const STATUS_VALUES: PayrollRunStatus[] = ['draft', 'finalized'];

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 6 }, (_, i) => CURRENT_YEAR - i);

// /payroll/runs (T1) — DESIGN_SPEC §5.17
export function PayrollRunsListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  usePageTitle(t('payroll.runsTitle'));

  const [year, setYear] = useState(String(CURRENT_YEAR));
  const [locationId, setLocationId] = useState('');
  const [status, setStatus] = useState('');
  const { data: locations } = useFetch(() => locationsApi.list(), []);

  const params = useMemo(
    () => ({
      year: year ? Number(year) : undefined,
      location_id: locationId ? Number(locationId) : undefined,
      status: status || undefined,
    }),
    [year, locationId, status]
  );
  const { data, loading, reload } = useFetch(() => payrollApi.runs(params), [JSON.stringify(params)]);

  const hasActiveFilters = !!(locationId || status);
  function clearFilters() {
    setLocationId('');
    setStatus('');
  }

  const [deleteTarget, setDeleteTarget] = useState<PayrollRun | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await payrollApi.deleteRun(deleteTarget.id);
      showToast('success', t('toast.deleted'));
      setDeleteTarget(null);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setDeleting(false);
    }
  }

  const columns: Column<PayrollRun>[] = [
    {
      key: 'period',
      header: t('payroll.period'),
      render: (r) => <span className="font-medium">{t(`payroll.months.${r.period_month}`)} {r.period_year}</span>,
    },
    { key: 'location', header: t('payroll.location'), render: (r) => r.location_name ?? t('common.all') },
    { key: 'status', header: t('payroll.status'), render: (r) => <PayrollStatusBadge status={r.status} /> },
    { key: 'generatedBy', header: t('payroll.generatedBy'), render: (r) => r.generated_by_name ?? '–' },
    { key: 'lineCount', header: t('payroll.lineCount'), align: 'right', render: (r) => r.line_count != null ? <span className="font-mono">{r.line_count}</span> : '–' },
    {
      key: 'totalNet',
      header: t('payroll.totalNetPay'),
      align: 'right',
      render: (r) => (r.total_net_pay_eur != null ? <span className="font-mono">{formatCurrency(r.total_net_pay_eur)}</span> : '–'),
    },
    {
      key: 'actions',
      header: '',
      render: (r) =>
        r.status === 'draft' ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(r);
            }}
            className="rounded-md p-1.5 text-neutral-400 hover:bg-danger-50 hover:text-danger-600"
            aria-label={t('common.delete')}
          >
            <Trash2 size={16} />
          </button>
        ) : null,
    },
  ];

  return (
    <div>
      <PageHeader
        title={t('payroll.runsTitle')}
        actions={
          <Button leftIcon={<Plus size={16} />} onClick={() => navigate('/payroll/runs/new')}>
            {t('payroll.newRun')}
          </Button>
        }
      />

      <div className="mb-4">
        <FilterBar hasActiveFilters={hasActiveFilters} onClearFilters={clearFilters}>
          <Select label={t('payroll.periodYear')} value={year} onChange={(e) => setYear(e.target.value)} options={YEARS.map((y) => ({ value: y, label: String(y) }))} containerClassName="w-32" />
          <Select
            label={t('payroll.location')}
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            placeholder={t('common.all')}
            options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
            containerClassName="w-48"
          />
          <Select
            label={t('payroll.status')}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            placeholder={t('common.all')}
            options={STATUS_VALUES.map((s) => ({ value: s, label: t(`status.payrollRun.${s}`) }))}
            containerClassName="w-40"
          />
        </FilterBar>
      </div>

      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(r) => r.id}
        loading={loading}
        onRowClick={(r) => navigate(`/payroll/runs/${r.id}`)}
        emptyIcon={<Wallet size={24} />}
        emptyMessage={t('payroll.emptyMessage')}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
        mobileCard={(r) => ({
          title: `${t(`payroll.months.${r.period_month}`)} ${r.period_year}`,
          subtitle: r.location_name ?? t('common.all'),
          badge: <PayrollStatusBadge status={r.status} />,
          rows: [{ label: t('payroll.totalNetPay'), value: r.total_net_pay_eur != null ? <span className="font-mono">{formatCurrency(r.total_net_pay_eur)}</span> : '–' }],
        })}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title={t('payroll.deleteConfirmTitle')}
        description={t('payroll.deleteConfirmDesc')}
        destructive
        confirmVariant="danger"
        loading={deleting}
      />
    </div>
  );
}
