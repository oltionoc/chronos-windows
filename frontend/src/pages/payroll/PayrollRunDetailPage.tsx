import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Trans, useTranslation } from 'react-i18next';
import { Users, Wallet, TrendingDown, TrendingUp, Trash2 } from 'lucide-react';
import { payrollApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { FileDownloadButton } from '../../components/ui/FileDownloadButton';
import { ConfirmDialog } from '../../components/ui/Modal';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { PayrollStatusBadge } from '../../components/ui/Badge';
import { formatCurrency, formatDate, formatMinutes } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { PayrollRunLine } from '../../api/types';

function StatBlock({ icon: Icon, label, value }: { icon: typeof Users; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-neutral-100">
        <Icon size={18} className="text-neutral-600" />
      </div>
      <div>
        <div className="font-mono text-lg font-semibold tabular-nums text-neutral-900">{value}</div>
        <div className="text-caption text-neutral-500">{label}</div>
      </div>
    </div>
  );
}

// /payroll/runs/:id (T2, no tabs) — DESIGN_SPEC §5.19
export function PayrollRunDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { id } = useParams();
  const runId = Number(id);

  const { data: run, loading: runLoading, reload: reloadRun } = useFetch(() => payrollApi.getRun(runId), [runId]);
  const { data: lines, loading: linesLoading, reload: reloadLines } = useFetch(() => payrollApi.lines(runId), [runId]);

  usePageTitle(
    run ? t('payroll.runTitle', { period: `${t(`payroll.months.${run.period_month}`)} ${run.period_year}` }) : '…',
    [{ label: t('payroll.runsTitle'), to: '/payroll/runs' }, { label: run ? `${t(`payroll.months.${run.period_month}`)} ${run.period_year}` : '' }]
  );

  const [finalizeOpen, setFinalizeOpen] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleFinalize() {
    setFinalizing(true);
    try {
      await payrollApi.finalize(runId);
      showToast('success', t('toast.saved'));
      setFinalizeOpen(false);
      reloadRun();
      reloadLines();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setFinalizing(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await payrollApi.deleteRun(runId);
      showToast('success', t('toast.deleted'));
      navigate('/payroll/runs');
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
      setDeleting(false);
    }
  }

  const stats = useMemo(() => {
    const rows = lines ?? [];
    return {
      count: rows.length,
      totalNet: rows.reduce((sum, l) => sum + l.net_pay_eur, 0),
      totalPenalties: rows.reduce((sum, l) => sum + l.total_lateness_penalty_eur, 0),
      totalBonuses: rows.reduce((sum, l) => sum + l.total_overtime_bonus_eur, 0),
    };
  }, [lines]);

  const columns: Column<PayrollRunLine>[] = [
    { key: 'employee', header: t('payroll.employee'), render: (l) => <span className="font-medium">{l.employee_name}</span> },
    { key: 'base', header: t('payroll.baseSalary'), align: 'right', render: (l) => <span className="font-mono">{formatCurrency(l.base_salary_eur)}</span> },
    { key: 'lateMin', header: t('payroll.lateMin'), align: 'right', render: (l) => <span className="font-mono">{formatMinutes(l.total_late_minutes)}</span> },
    {
      key: 'latenessPenalty',
      header: t('payroll.latenessPenalty'),
      align: 'right',
      render: (l) => <span className="font-mono text-danger-600">{formatCurrency(-Math.abs(l.total_lateness_penalty_eur))}</span>,
    },
    { key: 'otMin', header: t('payroll.overtimeMin'), align: 'right', render: (l) => <span className="font-mono">{formatMinutes(l.total_overtime_minutes)}</span> },
    { key: 'otBonus', header: t('payroll.overtimeBonus'), align: 'right', render: (l) => <span className="font-mono">{formatCurrency(l.total_overtime_bonus_eur)}</span> },
    { key: 'absenceDays', header: t('payroll.absenceDays'), align: 'right', render: (l) => <span className="font-mono">{l.total_absence_days}</span> },
    {
      key: 'absenceDeduction',
      header: t('payroll.absenceDeduction'),
      align: 'right',
      render: (l) => <span className="font-mono text-danger-600">{formatCurrency(-Math.abs(l.total_absence_deduction_eur))}</span>,
    },
    { key: 'paidLeave', header: t('payroll.paidLeave'), align: 'right', render: (l) => <span className="font-mono">{l.paid_leave_days}</span> },
    { key: 'unpaidLeave', header: t('payroll.unpaidLeave'), align: 'right', render: (l) => <span className="font-mono">{l.unpaid_leave_days}</span> },
    {
      key: 'netPay',
      header: t('payroll.netPay'),
      align: 'right',
      render: (l) => <span className="font-mono font-semibold text-neutral-900">{formatCurrency(l.net_pay_eur)}</span>,
    },
  ];

  if (runLoading || !run) {
    return <PageHeader title="…" />;
  }

  return (
    <div>
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            {t('payroll.runTitle', { period: `${t(`payroll.months.${run.period_month}`)} ${run.period_year}` })}
            <PayrollStatusBadge status={run.status} />
          </span>
        }
        subtitle={
          run.status === 'finalized' && run.finalized_at ? (
            <Trans
              i18nKey="payroll.finalizedOn"
              values={{ date: formatDate(run.finalized_at), name: run.generated_by_name ?? '' }}
              components={{ date: <span className="font-mono" /> }}
            />
          ) : undefined
        }
        actions={
          <div className="flex flex-wrap items-start gap-2">
            <FileDownloadButton
              label={t('payroll.exportExcel')}
              onDownload={() => payrollApi.exportExcel(runId)}
              fallbackFilename={`payroll-${run.period_year}-${run.period_month}.xlsx`}
            />
            {run.status === 'draft' && (
              <>
                <Button variant="danger-outline" leftIcon={<Trash2 size={16} />} onClick={() => setDeleteOpen(true)}>
                  {t('common.delete')}
                </Button>
                <Button onClick={() => setFinalizeOpen(true)}>{t('payroll.finalizeRun')}</Button>
              </>
            )}
          </div>
        }
      />

      <Card className="mb-6">
        <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
          <StatBlock icon={Users} label={t('payroll.employeesCount')} value={String(stats.count)} />
          <StatBlock icon={Wallet} label={t('payroll.totalNetPay')} value={formatCurrency(stats.totalNet)} />
          <StatBlock icon={TrendingDown} label={t('payroll.totalPenalties')} value={formatCurrency(stats.totalPenalties)} />
          <StatBlock icon={TrendingUp} label={t('payroll.totalBonuses')} value={formatCurrency(stats.totalBonuses)} />
        </div>
      </Card>

      <DataTable
        columns={columns}
        rows={lines ?? []}
        rowKey={(l) => l.id}
        loading={linesLoading}
        onRowClick={(l) => navigate(`/payroll/runs/${runId}/employees/${l.employee_id}`)}
        emptyIcon={<Wallet size={24} />}
        emptyMessage={t('payroll.emptyMessage')}
        mobileCard={(l) => ({
          title: l.employee_name,
          subtitle: <span className="font-mono">{formatCurrency(l.net_pay_eur)}</span>,
          rows: [
            { label: t('payroll.baseSalary'), value: <span className="font-mono">{formatCurrency(l.base_salary_eur)}</span> },
            { label: t('payroll.lateMin'), value: <span className="font-mono">{formatMinutes(l.total_late_minutes)}</span> },
            { label: t('payroll.latenessPenalty'), value: <span className="font-mono text-danger-600">{formatCurrency(-Math.abs(l.total_lateness_penalty_eur))}</span> },
            { label: t('payroll.overtimeMin'), value: <span className="font-mono">{formatMinutes(l.total_overtime_minutes)}</span> },
            { label: t('payroll.overtimeBonus'), value: <span className="font-mono">{formatCurrency(l.total_overtime_bonus_eur)}</span> },
            { label: t('payroll.absenceDays'), value: <span className="font-mono">{l.total_absence_days}</span> },
            { label: t('payroll.absenceDeduction'), value: <span className="font-mono text-danger-600">{formatCurrency(-Math.abs(l.total_absence_deduction_eur))}</span> },
            { label: t('payroll.paidLeave'), value: <span className="font-mono">{l.paid_leave_days}</span> },
            { label: t('payroll.unpaidLeave'), value: <span className="font-mono">{l.unpaid_leave_days}</span> },
          ],
        })}
      />

      <ConfirmDialog
        open={finalizeOpen}
        onClose={() => setFinalizeOpen(false)}
        onConfirm={handleFinalize}
        title={t('payroll.finalizeConfirmTitle')}
        description={t('payroll.finalizeConfirmDesc')}
        destructive={false}
        confirmVariant="primary"
        loading={finalizing}
      />

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
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
