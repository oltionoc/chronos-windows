import { useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { leaveApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { useAuth } from '../../auth/AuthContext';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { ConfirmDialog } from '../../components/ui/Modal';
import { LeaveStatusBadge, LeaveTypeBadge } from '../../components/ui/Badge';
import { KeyValueGridSkeleton } from '../../components/ui/Skeleton';
import { formatDate, formatDateTime } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import { localizedLeaveTypeName } from '../../lib/leaveTypes';

function daysBetween(start: string, end: string): number {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return Math.round(ms / 86400000) + 1;
}

// /leave/:id (T2, no tabs) — DESIGN_SPEC §5.16. No approval workflow
// (client direction 2026-08-27) — every request auto-approves on creation,
// so this page is a record view with a delete option, not a review action.
export function LeaveDetailPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { user } = useAuth();
  const { id } = useParams();
  const leaveId = Number(id);
  const isAdmin = user?.role === 'admin';

  const { data: leave, loading } = useFetch(() => leaveApi.get(leaveId), [leaveId]);
  usePageTitle(t('leave.detailTitle'), [{ label: t('leave.title'), to: '/leave' }, { label: t('leave.detailTitle') }]);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      await leaveApi.remove(leaveId);
      showToast('success', t('toast.saved'));
      navigate('/leave');
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setDeleting(false);
    }
  }

  if (loading || !leave) {
    return (
      <div>
        <PageHeader title="…" />
        <Card><KeyValueGridSkeleton rows={6} /></Card>
      </div>
    );
  }

  // Backend still allows a pending record (legacy/historical) or an
  // auto-approved one to be deleted, but blocks a manually-approved
  // required-approval record — the exact rule lives server-side
  // (routers/leave.py delete_leave_record); this just avoids offering a
  // delete that would obviously 400 for a rejected/cancelled record.
  const canDelete = leave.status === 'pending' || leave.status === 'approved';

  const rows: [string, ReactNode][] = [
    [t('leave.employee'), leave.employee_name ?? '–'],
    [t('leave.leaveType'), <LeaveTypeBadge key="lt" name={localizedLeaveTypeName({ name_en: leave.leave_type_name_en, name_sq: leave.leave_type_name_sq }, i18n.language)} />],
    [t('leave.startDate'), <span key="start" className="font-mono">{formatDate(leave.start_date)}</span>],
    [t('leave.endDate'), <span key="end" className="font-mono">{formatDate(leave.end_date)}</span>],
    [t('leave.days'), <span key="days" className="font-mono">{daysBetween(leave.start_date, leave.end_date)}</span>],
    [t('leave.requestedBy'), leave.requested_by_name ?? '–'],
    [t('leave.notes'), leave.notes || '–'],
  ];
  if (leave.approved_by_name) {
    rows.push([t('leave.approvedBy'), leave.approved_by_name]);
    rows.push([t('leave.approvedAt'), leave.approved_at ? <span key="approvedAt" className="font-mono">{formatDateTime(leave.approved_at)}</span> : '–']);
  }

  return (
    <div>
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            {t('leave.detailTitle')}
            <LeaveStatusBadge status={leave.status} />
          </span>
        }
        subtitle={leave.employee_name}
        actions={
          isAdmin && (
            <Button variant="danger" disabled={!canDelete} onClick={() => setDeleteOpen(true)}>
              {t('common.delete')}
            </Button>
          )
        }
      />

      <Card>
        <dl className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt className="text-caption text-neutral-500">{label}</dt>
              <dd className="mt-0.5 text-body text-neutral-800">{value}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={handleDelete}
        title={t('leave.deleteConfirmTitle')}
        description={t('leave.deleteConfirmDesc')}
        destructive
        loading={deleting}
      />
    </div>
  );
}
