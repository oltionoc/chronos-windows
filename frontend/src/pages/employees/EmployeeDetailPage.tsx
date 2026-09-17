import { useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import { employeesApi, devicesApi, shiftSchedulesApi, attendanceApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { useAuth } from '../../auth/AuthContext';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { Tabs } from '../../components/ui/Tabs';
import { Button } from '../../components/ui/Button';
import { Modal, ConfirmDialog } from '../../components/ui/Modal';
import { Select, SearchableSelect } from '../../components/ui/Select';
import { Input } from '../../components/ui/Input';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { EmploymentStatusBadge, CurrentBadge } from '../../components/ui/Badge';
import { CodeChip } from '../../components/ui/CodeChip';
import { KeyValueGridSkeleton } from '../../components/ui/Skeleton';
import { AttendanceStatusTable } from '../../components/AttendanceStatusTable';
import { DateRangeInput } from '../../components/ui/FilterBar';
import { formatCurrency, formatDate, formatDateTime } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { Employee, EmployeeDeviceEnrollment, EmployeeShiftAssignment } from '../../api/types';
import { CalendarClock, HardDrive } from 'lucide-react';

function firstOfMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
}
function today(): string {
  return new Date().toISOString().slice(0, 10);
}

type TabKey = 'profile' | 'enrollments' | 'assignments' | 'attendance';

// /employees/:id (T2) — DESIGN_SPEC §5.4
export function EmployeeDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { user } = useAuth();
  const { id } = useParams();
  const employeeId = Number(id);
  // Operational access: admin or manager (server-side scoped to the
  // manager's own location) — see BLUEPRINT.md's 2026-08-24 access-control
  // note. Kept as `isAdmin` name since it still gates the same UI elements.
  const isAdmin = user?.role === 'admin' || user?.role === 'manager';

  const [tab, setTab] = useState<TabKey>('profile');
  const [forbidden, setForbidden] = useState(false);
  const { data: employee, loading } = useFetch(async () => {
    try {
      return await employeesApi.get(employeeId);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
        return null;
      }
      throw err;
    }
  }, [employeeId]);

  usePageTitle(
    employee ? `${employee.first_name} ${employee.last_name}` : '…',
    [{ label: t('employees.title'), to: '/employees' }, { label: employee ? `${employee.first_name} ${employee.last_name}` : '' }]
  );

  if (forbidden) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
        <p className="text-section-title text-neutral-900">{t('employees.noAccess')}</p>
        <Button onClick={() => navigate('/')}>{t('employees.backToDashboard')}</Button>
      </div>
    );
  }

  const tabs = [
    { key: 'profile', label: t('employees.tabProfile') },
    { key: 'enrollments', label: t('employees.tabEnrollments') },
    { key: 'assignments', label: t('employees.tabShiftAssignments') },
    { key: 'attendance', label: t('employees.tabAttendanceHistory') },
  ];

  return (
    <div>
      <PageHeader
        title={
          loading || !employee ? '…' : (
            <span className="flex items-center gap-3">
              {employee.first_name} {employee.last_name}
              <EmploymentStatusBadge status={employee.employment_status} />
            </span>
          )
        }
        subtitle={employee?.employee_code && <CodeChip>{employee.employee_code}</CodeChip>}
        actions={isAdmin && employee ? <Button onClick={() => navigate(`/employees/${employeeId}/edit`)}>{t('common.edit')}</Button> : undefined}
      />

      <Tabs tabs={tabs} active={tab} onChange={(k) => setTab(k as TabKey)} />

      <div className="mt-6">
        {tab === 'profile' && (
          <ProfileTab employee={employee} loading={loading} />
        )}
        {tab === 'enrollments' && (
          <EnrollmentsTab employeeId={employeeId} isAdmin={isAdmin} showToast={showToast} t={t} />
        )}
        {tab === 'assignments' && (
          <AssignmentsTab employeeId={employeeId} isAdmin={isAdmin} showToast={showToast} t={t} />
        )}
        {tab === 'attendance' && <AttendanceTab employeeId={employeeId} />}
      </div>
    </div>
  );
}

function ProfileTab({ employee, loading }: { employee: Employee | null; loading: boolean }) {
  const { t } = useTranslation();
  if (loading || !employee) {
    return (
      <Card>
        <KeyValueGridSkeleton rows={6} />
      </Card>
    );
  }
  const rows: [string, ReactNode][] = [
    [t('employees.jobTitle'), employee.job_title || '–'],
    [t('employees.nationalId'), employee.national_id || '–'],
    [t('employees.hireDate'), <span key="hireDate" className="font-mono">{formatDate(employee.hire_date)}</span>],
    [t('employees.baseSalary'), <span key="baseSalary" className="font-mono">{formatCurrency(employee.base_salary_eur)}</span>],
    [t('employees.location'), employee.location_name ?? '–'],
    [t('employees.manager'), employee.manager_name || t('employees.noManager')],
  ];
  return (
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
  );
}

function EnrollmentsTab({
  employeeId,
  isAdmin,
  showToast,
  t,
}: {
  employeeId: number;
  isAdmin: boolean;
  showToast: ReturnType<typeof useToast>['showToast'];
  t: (key: string) => string;
}) {
  const { data: enrollments, loading, reload } = useFetch(() => employeesApi.deviceEnrollments(employeeId), [employeeId]);
  const { data: devices } = useFetch(() => devicesApi.list(), []);
  const [modalOpen, setModalOpen] = useState(false);
  const [deviceId, setDeviceId] = useState('');
  const [deviceUserId, setDeviceUserId] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!deviceId || !deviceUserId) return;
    setSubmitting(true);
    try {
      await employeesApi.addDeviceEnrollment(employeeId, { device_id: Number(deviceId), device_user_id: deviceUserId });
      showToast('success', t('toast.created'));
      setModalOpen(false);
      setDeviceId('');
      setDeviceUserId('');
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  const columns: Column<EmployeeDeviceEnrollment>[] = [
    { key: 'device', header: t('employees.device'), render: (e) => e.device_label ?? String(e.device_id) },
    { key: 'deviceUserId', header: t('employees.deviceUserId'), render: (e) => e.device_user_id },
    { key: 'enrolledAt', header: t('employees.enrolledAt'), render: (e) => (e.enrolled_at ? <span className="font-mono">{formatDateTime(e.enrolled_at)}</span> : '–') },
  ];

  return (
    <Card
      headerAction={isAdmin ? <Button size="sm" leftIcon={<Plus size={16} />} onClick={() => setModalOpen(true)}>{t('employees.addEnrollment')}</Button> : undefined}
    >
      <DataTable
        columns={columns}
        rows={enrollments ?? []}
        rowKey={(e) => e.id}
        loading={loading}
        emptyIcon={<HardDrive size={24} />}
        emptyMessage={t('employees.emptyEnrollments')}
        mobileCard={(e) => ({ title: e.device_label ?? String(e.device_id), subtitle: e.device_user_id, rows: [] })}
      />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={t('employees.addEnrollment')}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <Select
            label={t('employees.device')}
            required
            placeholder={t('common.select')}
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
            options={(devices ?? []).map((d) => ({ value: d.id, label: d.label }))}
          />
          <Input label={t('employees.deviceUserId')} required value={deviceUserId} onChange={(e) => setDeviceUserId(e.target.value)} />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={submitting}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>
    </Card>
  );
}

function AssignmentsTab({
  employeeId,
  isAdmin,
  showToast,
  t,
}: {
  employeeId: number;
  isAdmin: boolean;
  showToast: ReturnType<typeof useToast>['showToast'];
  t: (key: string) => string;
}) {
  const { data: assignments, loading, reload } = useFetch(() => employeesApi.shiftAssignments(employeeId), [employeeId]);
  const { data: schedules } = useFetch(() => shiftSchedulesApi.list(), []);
  const [modalOpen, setModalOpen] = useState(false);
  // null = the modal is creating a new assignment; a row = editing that one.
  const [editing, setEditing] = useState<EmployeeShiftAssignment | null>(null);
  const [scheduleId, setScheduleId] = useState<string | number | null>(null);
  const [effectiveFrom, setEffectiveFrom] = useState(today());
  const [effectiveTo, setEffectiveTo] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState<EmployeeShiftAssignment | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);

  function openCreate() {
    setEditing(null);
    setScheduleId(null);
    setEffectiveFrom(today());
    setEffectiveTo('');
    setModalOpen(true);
  }

  function openEdit(a: EmployeeShiftAssignment) {
    setEditing(a);
    setScheduleId(a.shift_schedule_id);
    setEffectiveFrom(a.effective_from);
    setEffectiveTo(a.effective_to ?? '');
    setModalOpen(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!scheduleId) return;
    setSubmitting(true);
    try {
      const payload = {
        shift_schedule_id: Number(scheduleId),
        effective_from: effectiveFrom,
        effective_to: effectiveTo || null,
      };
      if (editing) {
        await employeesApi.updateShiftAssignment(employeeId, editing.id, payload);
        showToast('success', t('toast.saved'));
      } else {
        await employeesApi.addShiftAssignment(employeeId, payload);
        showToast('success', t('toast.created'));
      }
      setModalOpen(false);
      setEditing(null);
      setScheduleId(null);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    setDeletingBusy(true);
    try {
      await employeesApi.removeShiftAssignment(employeeId, deleting.id);
      showToast('success', t('toast.deleted'));
      setDeleting(null);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setDeletingBusy(false);
    }
  }

  const sorted = useMemo(
    () => [...(assignments ?? [])].sort((a, b) => b.effective_from.localeCompare(a.effective_from)),
    [assignments]
  );

  const columns: Column<EmployeeShiftAssignment>[] = [
    { key: 'schedule', header: t('employees.shiftSchedule'), render: (a) => a.shift_schedule_name ?? String(a.shift_schedule_id) },
    { key: 'from', header: t('employees.effectiveFrom'), render: (a) => <span className="font-mono">{formatDate(a.effective_from)}</span> },
    {
      key: 'to',
      header: t('employees.effectiveTo'),
      render: (a) => (a.effective_to ? <span className="font-mono">{formatDate(a.effective_to)}</span> : <CurrentBadge />),
    },
    ...(isAdmin
      ? [
          {
            key: 'actions',
            header: '',
            align: 'right' as const,
            render: (a: EmployeeShiftAssignment) => (
              <div className="flex justify-end gap-3" onClick={(e) => e.stopPropagation()}>
                <button type="button" className="text-caption text-primary-600 hover:underline" onClick={() => openEdit(a)}>
                  {t('common.edit')}
                </button>
                <button type="button" className="text-caption text-danger-600 hover:underline" onClick={() => setDeleting(a)}>
                  {t('common.delete')}
                </button>
              </div>
            ),
          } as Column<EmployeeShiftAssignment>,
        ]
      : []),
  ];

  return (
    <Card
      headerAction={isAdmin ? <Button size="sm" leftIcon={<Plus size={16} />} onClick={openCreate}>{t('employees.addAssignment')}</Button> : undefined}
    >
      <DataTable
        columns={columns}
        rows={sorted}
        rowKey={(a) => a.id}
        loading={loading}
        emptyIcon={<CalendarClock size={24} />}
        emptyMessage={t('employees.emptyAssignments')}
        mobileCard={(a) => ({
          title: a.shift_schedule_name ?? String(a.shift_schedule_id),
          subtitle: <span className="font-mono">{formatDate(a.effective_from)}</span>,
          badge: !a.effective_to ? <CurrentBadge /> : undefined,
          rows: [],
        })}
      />

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? t('employees.editAssignment') : t('employees.addAssignment')}
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <SearchableSelect
            label={t('employees.shiftSchedule')}
            placeholder={t('common.select')}
            value={scheduleId}
            onChange={setScheduleId}
            options={(schedules ?? []).map((s) => ({ value: s.id, label: s.name }))}
          />
          <Input
            label={t('employees.effectiveFrom')}
            type="date"
            required
            value={effectiveFrom}
            onChange={(e) => setEffectiveFrom(e.target.value)}
          />
          <Input
            label={t('employees.effectiveTo')}
            type="date"
            value={effectiveTo}
            onChange={(e) => setEffectiveTo(e.target.value)}
            hint={t('employees.effectiveToHint')}
          />
          <p className="text-caption text-neutral-500">{t('employees.parallelAssignmentHint')}</p>
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={submitting}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        loading={deletingBusy}
        title={t('employees.deleteAssignmentTitle')}
        description={t('employees.deleteAssignmentDesc')}
      />
    </Card>
  );
}

function AttendanceTab({ employeeId }: { employeeId: number }) {
  const { t } = useTranslation();
  const [dateFrom, setDateFrom] = useState(firstOfMonth());
  const [dateTo, setDateTo] = useState(today());

  const params = useMemo(() => ({ employee_id: employeeId, date_from: dateFrom, date_to: dateTo, page_size: 100 }), [employeeId, dateFrom, dateTo]);
  const { data, loading } = useFetch(() => attendanceApi.dailyStatus(params), [JSON.stringify(params)]);

  return (
    <div>
      <div className="mb-4">
        <DateRangeInput from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} fromLabel={t('attendance.dateFrom')} toLabel={t('attendance.dateTo')} />
      </div>
      <AttendanceStatusTable rows={data?.items ?? []} loading={loading} showEmployeeColumn={false} />
    </div>
  );
}
