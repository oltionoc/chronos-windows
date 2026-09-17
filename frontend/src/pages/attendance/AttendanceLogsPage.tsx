import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileClock, RefreshCw } from 'lucide-react';
import { attendanceApi, devicesApi, employeesApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { FilterBar, DateRangeInput } from '../../components/ui/FilterBar';
import { Select, SearchableSelect } from '../../components/ui/Select';
import { Toggle } from '../../components/ui/Controls';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { DataTable, Pagination } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { Badge, PunchTypeBadge } from '../../components/ui/Badge';
import { CodeChip } from '../../components/ui/CodeChip';
import { formatDateTime } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { AttendanceLog } from '../../api/types';

// /attendance/logs (T1) — DESIGN_SPEC §5.13
export function AttendanceLogsPage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  usePageTitle(t('attendance.logsTitle'));

  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [employeeId, setEmployeeId] = useState<string | number | null>(null);
  const [deviceId, setDeviceId] = useState('');
  const [unresolvedOnly, setUnresolvedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const { data: employees } = useFetch(() => employeesApi.list({ page_size: 100 }), []);
  const { data: devices } = useFetch(() => devicesApi.list(), []);

  const params = useMemo(
    () => ({
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      employee_id: employeeId ? Number(employeeId) : undefined,
      device_id: deviceId ? Number(deviceId) : undefined,
      unresolved_only: unresolvedOnly || undefined,
      page,
      page_size: pageSize,
    }),
    [dateFrom, dateTo, employeeId, deviceId, unresolvedOnly, page, pageSize]
  );

  const { data, loading, reload } = useFetch(() => attendanceApi.logs(params), [JSON.stringify(params)]);

  const hasActiveFilters = !!(dateFrom || dateTo || employeeId || deviceId || unresolvedOnly);
  function clearFilters() {
    setDateFrom('');
    setDateTo('');
    setEmployeeId(null);
    setDeviceId('');
    setUnresolvedOnly(false);
    setPage(1);
  }

  const [resolveLog, setResolveLog] = useState<AttendanceLog | null>(null);
  const [resolveEmployee, setResolveEmployee] = useState<string | number | null>(null);
  const [resolving, setResolving] = useState(false);

  async function handleResolve() {
    if (!resolveLog || !resolveEmployee) return;
    setResolving(true);
    try {
      await attendanceApi.resolveLog(resolveLog.id, Number(resolveEmployee));
      showToast('success', t('attendance.resolveSuccess'));
      setResolveLog(null);
      setResolveEmployee(null);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setResolving(false);
    }
  }

  const employeeOptions = (employees?.items ?? []).map((e) => ({ value: e.id, label: `${e.first_name} ${e.last_name}` }));

  const columns: Column<AttendanceLog>[] = [
    { key: 'timestamp', header: t('attendance.timestamp'), render: (l) => <span className="font-mono">{formatDateTime(l.punch_timestamp)}</span> },
    { key: 'device', header: t('attendance.deviceCol'), render: (l) => l.device_label ?? String(l.device_id) },
    {
      key: 'employee',
      header: t('attendance.employee'),
      render: (l) =>
        l.employee_id ? l.employee_name : <Badge className="bg-warning-100 text-warning-700">{t('attendance.unresolved')}</Badge>,
    },
    { key: 'punchType', header: t('attendance.punchType'), render: (l) => <PunchTypeBadge type={l.punch_type} /> },
    { key: 'rawStatus', header: t('attendance.rawStatusCode'), render: (l) => <CodeChip>{l.raw_status_code}</CodeChip> },
    {
      key: 'actions',
      header: '',
      render: (l) =>
        !l.employee_id ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={(e) => {
              e.stopPropagation();
              setResolveLog(l);
            }}
          >
            {t('common.resolve')}
          </Button>
        ) : null,
    },
  ];

  return (
    <div>
      <PageHeader
        title={t('attendance.logsTitle')}
        actions={
          <Button variant="secondary" leftIcon={<RefreshCw size={16} />} onClick={reload} loading={loading}>
            {t('common.refresh')}
          </Button>
        }
      />

      <div className="mb-4">
        <FilterBar hasActiveFilters={hasActiveFilters} onClearFilters={clearFilters}>
          <DateRangeInput
            from={dateFrom}
            to={dateTo}
            onFromChange={(v) => { setDateFrom(v); setPage(1); }}
            onToChange={(v) => { setDateTo(v); setPage(1); }}
            fromLabel={t('attendance.dateFrom')}
            toLabel={t('attendance.dateTo')}
          />
          <SearchableSelect
            label={t('attendance.employee')}
            placeholder={t('common.all')}
            value={employeeId}
            onChange={(v) => { setEmployeeId(v); setPage(1); }}
            options={employeeOptions}
            containerClassName="w-56"
          />
          <Select
            label={t('attendance.deviceCol')}
            value={deviceId}
            onChange={(e) => { setDeviceId(e.target.value); setPage(1); }}
            placeholder={t('common.all')}
            options={(devices ?? []).map((d) => ({ value: d.id, label: d.label }))}
            containerClassName="w-48"
          />
          <Toggle checked={unresolvedOnly} onChange={(v) => { setUnresolvedOnly(v); setPage(1); }} label={t('attendance.unresolvedOnly')} />
        </FilterBar>
      </div>

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(l) => l.id}
        loading={loading}
        emptyIcon={<FileClock size={24} />}
        emptyMessage={t('attendance.logsEmptyMessage')}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
        mobileCard={(l) => ({
          title: l.employee_id ? l.employee_name : <Badge className="bg-warning-100 text-warning-700">{t('attendance.unresolved')}</Badge>,
          subtitle: <span className="font-mono">{formatDateTime(l.punch_timestamp)}</span>,
          badge: <PunchTypeBadge type={l.punch_type} />,
          rows: [
            { label: t('attendance.deviceCol'), value: l.device_label ?? String(l.device_id) },
            { label: t('attendance.rawStatusCode'), value: <CodeChip>{l.raw_status_code}</CodeChip> },
            ...(!l.employee_id
              ? [{ label: '', value: <Button size="sm" variant="secondary" onClick={() => setResolveLog(l)}>{t('common.resolve')}</Button> }]
              : []),
          ],
        })}
        footer={
          data && (
            <Pagination
              page={page}
              pageSize={pageSize}
              total={data.total}
              onPageChange={setPage}
              onPageSizeChange={(size) => { setPageSize(size); setPage(1); }}
            />
          )
        }
      />

      <Modal open={!!resolveLog} onClose={() => setResolveLog(null)} title={t('attendance.resolvePunch')}>
        <div className="flex flex-col gap-5">
          <SearchableSelect
            label={t('employees.title')}
            placeholder={t('common.select')}
            value={resolveEmployee}
            onChange={setResolveEmployee}
            options={employeeOptions}
          />
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setResolveLog(null)}>{t('common.cancel')}</Button>
            <Button onClick={handleResolve} loading={resolving} disabled={!resolveEmployee}>{t('common.resolve')}</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
