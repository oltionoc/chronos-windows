import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CalendarCheck, Plus, Upload } from 'lucide-react';
import { leaveApi, employeesApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { useAuth } from '../../auth/AuthContext';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { BulkImportModal } from '../../components/BulkImportModal';
import { FilterBar, DateRangeInput } from '../../components/ui/FilterBar';
import { Select, SearchableSelect } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { LeaveStatusBadge, LeaveTypeBadge } from '../../components/ui/Badge';
import { formatDate } from '../../lib/format';
import { localizedLeaveTypeName } from '../../lib/leaveTypes';
import type { LeaveRecord, LeaveStatus } from '../../api/types';

const STATUS_VALUES: LeaveStatus[] = ['pending', 'approved', 'rejected', 'cancelled'];

function daysBetween(start: string, end: string): number {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return Math.round(ms / 86400000) + 1;
}

// /leave (T1) — DESIGN_SPEC §5.14. No approval workflow (client direction
// 2026-08-27): every leave request auto-approves on creation, so this page
// is a record/history view, not a review queue.
export function LeaveListPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [searchParams, setSearchParams] = useSearchParams();
  usePageTitle(isAdmin ? t('leave.title') : t('leave.myTeamTitle'));

  const [status, setStatus] = useState(searchParams.get('status') ?? '');
  const [employeeId, setEmployeeId] = useState<string | number | null>(null);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const { data: employees } = useFetch(() => employeesApi.list({ page_size: 100 }).catch(() => null), []);

  const params = useMemo(
    () => ({
      status: status || undefined,
      employee_id: employeeId ? Number(employeeId) : undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      page_size: 50,
    }),
    [status, employeeId, dateFrom, dateTo]
  );

  const { data, loading, reload } = useFetch(() => leaveApi.list(params), [JSON.stringify(params)]);

  const hasActiveFilters = !!(employeeId || dateFrom || dateTo || status !== (searchParams.get('status') ?? ''));

  function clearFilters() {
    setStatus('');
    setEmployeeId(null);
    setDateFrom('');
    setDateTo('');
    setSearchParams({});
  }

  const [importOpen, setImportOpen] = useState(false);

  const employeeOptions = (employees?.items ?? []).map((e) => ({ value: e.id, label: `${e.first_name} ${e.last_name}` }));

  const columns: Column<LeaveRecord>[] = [
    { key: 'employee', header: t('leave.employee'), render: (l) => <span className="font-medium">{l.employee_name}</span> },
    { key: 'type', header: t('leave.leaveType'), render: (l) => <LeaveTypeBadge name={localizedLeaveTypeName({ name_en: l.leave_type_name_en, name_sq: l.leave_type_name_sq }, i18n.language)} /> },
    { key: 'start', header: t('leave.startDate'), render: (l) => <span className="font-mono">{formatDate(l.start_date)}</span> },
    { key: 'end', header: t('leave.endDate'), render: (l) => <span className="font-mono">{formatDate(l.end_date)}</span> },
    { key: 'days', header: t('leave.days'), align: 'right', render: (l) => <span className="font-mono">{daysBetween(l.start_date, l.end_date)}</span> },
    { key: 'status', header: t('leave.status'), render: (l) => <LeaveStatusBadge status={l.status} /> },
    { key: 'requestedBy', header: t('leave.requestedBy'), render: (l) => l.requested_by_name ?? '–' },
  ];

  return (
    <div>
      <PageHeader
        title={isAdmin ? t('leave.title') : t('leave.myTeamTitle')}
        actions={
          <div className="flex gap-2">
            {isAdmin && (
              <Button variant="secondary" leftIcon={<Upload size={16} />} onClick={() => setImportOpen(true)}>
                {t('bulkImport.button')}
              </Button>
            )}
            <Button leftIcon={<Plus size={16} />} onClick={() => navigate('/leave/new')}>
              {t('leave.newRequest')}
            </Button>
          </div>
        }
      />

      {isAdmin && (
        <BulkImportModal
          open={importOpen}
          onClose={() => setImportOpen(false)}
          resourceLabel={t('leave.title')}
          columns={['employee_id', 'leave_type_id', 'start_date', 'end_date', 'notes']}
          onImport={(file) => leaveApi.bulkImport(file)}
          onDone={reload}
        />
      )}

      <div className="mb-4">
        <FilterBar hasActiveFilters={hasActiveFilters} onClearFilters={clearFilters}>
          <Select
            label={t('leave.status')}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            placeholder={t('common.all')}
            options={STATUS_VALUES.map((s) => ({ value: s, label: t(`status.leave.${s}`) }))}
            containerClassName="w-44"
          />
          <SearchableSelect
            label={t('leave.employee')}
            placeholder={t('common.all')}
            value={employeeId}
            onChange={setEmployeeId}
            options={employeeOptions}
            containerClassName="w-56"
          />
          <DateRangeInput
            from={dateFrom}
            to={dateTo}
            onFromChange={setDateFrom}
            onToChange={setDateTo}
            fromLabel={t('attendance.dateFrom')}
            toLabel={t('attendance.dateTo')}
          />
        </FilterBar>
      </div>

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(l) => l.id}
        loading={loading}
        onRowClick={(l) => navigate(`/leave/${l.id}`)}
        emptyIcon={<CalendarCheck size={24} />}
        emptyMessage={t('leave.emptyMessage')}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
        mobileCard={(l) => ({
          title: l.employee_name,
          subtitle: <span className="font-mono">{formatDate(l.start_date)} – {formatDate(l.end_date)}</span>,
          badge: <LeaveStatusBadge status={l.status} />,
          rows: [
            { label: t('leave.leaveType'), value: <LeaveTypeBadge name={localizedLeaveTypeName({ name_en: l.leave_type_name_en, name_sq: l.leave_type_name_sq }, i18n.language)} /> },
            { label: t('leave.days'), value: <span className="font-mono">{daysBetween(l.start_date, l.end_date)}</span> },
          ],
        })}
      />
    </div>
  );
}
