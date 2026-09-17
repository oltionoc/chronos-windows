import { useState } from 'react';
import type { FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import { payrollApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { RadioGroup } from '../../components/ui/Controls';
import { CurrencyInput, Input } from '../../components/ui/Input';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { AdjustmentTypeBadge, PayrollStatusBadge } from '../../components/ui/Badge';
import { FileDownloadButton } from '../../components/ui/FileDownloadButton';
import { KeyValueGridSkeleton } from '../../components/ui/Skeleton';
import { formatCurrency, formatMinutes } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { AdjustmentType, PayrollAdjustment } from '../../api/types';

// /payroll/runs/:id/employees/:employeeId (T2, no tabs) — DESIGN_SPEC §5.20
export function PayrollLineDetailPage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const { id, employeeId } = useParams();
  const runId = Number(id);
  const empId = Number(employeeId);

  const { data: run } = useFetch(() => payrollApi.getRun(runId), [runId]);
  const { data: line, loading, reload } = useFetch(() => payrollApi.lineDetail(runId, empId), [runId, empId]);

  usePageTitle(
    line?.employee_name ?? '…',
    [
      { label: t('payroll.runsTitle'), to: '/payroll/runs' },
      { label: run ? `${t(`payroll.months.${run.period_month}`)} ${run.period_year}` : '', to: `/payroll/runs/${runId}` },
      { label: line?.employee_name ?? '' },
    ]
  );

  const [modalOpen, setModalOpen] = useState(false);
  const [type, setType] = useState<AdjustmentType>('bonus');
  const [amount, setAmount] = useState<number | null>(null);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const isDraft = run?.status === 'draft';

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (amount == null || !reason.trim()) return;
    setSubmitting(true);
    try {
      await payrollApi.addAdjustment(runId, empId, { type, amount_eur: amount, reason });
      showToast('success', t('toast.created'));
      setModalOpen(false);
      setType('bonus');
      setAmount(null);
      setReason('');
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  const adjustmentColumns: Column<PayrollAdjustment>[] = [
    { key: 'type', header: t('payroll.adjustmentType'), render: (a) => <AdjustmentTypeBadge type={a.type} /> },
    { key: 'amount', header: t('payroll.amount'), align: 'right', render: (a) => <span className="font-mono">{formatCurrency(a.amount_eur)}</span> },
    { key: 'reason', header: t('payroll.reason'), render: (a) => a.reason },
    { key: 'createdBy', header: t('payroll.createdBy'), render: (a) => a.created_by_name ?? '–' },
  ];

  if (loading || !line || !run) {
    return (
      <div>
        <PageHeader title="…" />
        <Card><KeyValueGridSkeleton rows={6} /></Card>
      </div>
    );
  }

  const breakdownRows: [string, string, boolean][] = [
    [t('payroll.baseSalary'), formatCurrency(line.base_salary_eur), false],
    [t('payroll.lateMin'), formatMinutes(line.total_late_minutes), false],
    [t('payroll.latenessPenalty'), formatCurrency(-Math.abs(line.total_lateness_penalty_eur)), true],
    [t('payroll.overtimeMin'), formatMinutes(line.total_overtime_minutes), false],
    [t('payroll.overtimeBonus'), formatCurrency(line.total_overtime_bonus_eur), false],
    [t('payroll.absenceDays'), String(line.total_absence_days), false],
    [t('payroll.absenceDeduction'), formatCurrency(-Math.abs(line.total_absence_deduction_eur)), true],
    [t('payroll.paidLeave'), String(line.paid_leave_days), false],
    [t('payroll.unpaidLeave'), String(line.unpaid_leave_days), false],
  ];

  return (
    <div>
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            {line.employee_name}
            <PayrollStatusBadge status={run.status} />
          </span>
        }
        subtitle={`${t(`payroll.months.${run.period_month}`)} ${run.period_year}`}
        actions={
          <FileDownloadButton
            label={t('payroll.downloadPayslip')}
            onDownload={() => payrollApi.payslip(runId, empId)}
            fallbackFilename={`payslip-${empId}.xlsx`}
            disabled={run.status !== 'finalized'}
            disabledHint={run.status !== 'finalized' ? t('payroll.availableOnceFinalized') : undefined}
          />
        }
      />

      <Card title={t('payroll.lineTitle')} className="mb-6">
        <dl className="flex flex-col divide-y divide-neutral-200">
          {breakdownRows.map(([label, value, danger]) => (
            <div key={label} className="flex items-center justify-between py-2.5 first:pt-0">
              <dt className="text-body text-neutral-600">{label}</dt>
              <dd className={`font-mono tabular-nums text-body ${danger ? 'text-danger-600' : 'text-neutral-800'}`}>{value}</dd>
            </div>
          ))}
          <div className="flex items-center justify-between border-t border-neutral-200 pt-3 mt-1">
            <dt className="text-lg font-semibold text-neutral-900">{t('payroll.netPay')}</dt>
            <dd className="font-mono text-lg font-semibold tabular-nums text-neutral-900">{formatCurrency(line.net_pay_eur)}</dd>
          </div>
        </dl>
      </Card>

      <Card
        title={t('payroll.adjustmentsTitle')}
        headerAction={isDraft ? <Button size="sm" leftIcon={<Plus size={16} />} onClick={() => setModalOpen(true)}>{t('payroll.addAdjustment')}</Button> : undefined}
      >
        <DataTable
          columns={adjustmentColumns}
          rows={line.adjustments ?? []}
          rowKey={(a) => a.id}
          emptyMessage={t('payroll.emptyAdjustments')}
          mobileCard={(a) => ({
            title: <AdjustmentTypeBadge type={a.type} />,
            subtitle: a.reason,
            badge: <span className="font-mono">{formatCurrency(a.amount_eur)}</span>,
            rows: [{ label: t('payroll.createdBy'), value: a.created_by_name ?? '–' }],
          })}
        />
      </Card>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={t('payroll.addAdjustment')}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <RadioGroup
            name="adjustment-type"
            value={type}
            onChange={(v) => setType(v as AdjustmentType)}
            options={[
              { value: 'bonus', label: t('status.adjustment.bonus') },
              { value: 'deduction', label: t('status.adjustment.deduction') },
            ]}
          />
          <CurrencyInput label={t('payroll.amount')} required value={amount} onChange={setAmount} />
          <Input label={t('payroll.reason')} required value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={submitting} disabled={amount == null || !reason.trim()}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
