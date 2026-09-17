import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { attendanceApi, employeesApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { useAuth } from '../../auth/AuthContext';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { FilterBar, DateRangeInput } from '../../components/ui/FilterBar';
import { Select, SearchableSelect, MultiSelect } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Pagination } from '../../components/ui/Table';
import { AttendanceStatusTable } from '../../components/AttendanceStatusTable';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { DailyStatusValue } from '../../api/types';

const STATUS_VALUES: DailyStatusValue[] = ['present', 'late', 'absent', 'on_leave', 'holiday', 'not_scheduled'];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

// /attendance (T1) — DESIGN_SPEC §5.12
export function AttendanceDailyStatusPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { showToast } = useToast();
  const isAdmin = user?.role === 'admin';
  usePageTitle(isAdmin ? t('attendance.title') : t('attendance.myTeamTitle'));

  const [searchParams] = useSearchParams();
  const initialDate = searchParams.get('date');
  // Deep links can carry more than one status (e.g. the dashboard's
  // "Present" card links here as "present,late" since it counts late
  // arrivals as present too) — parse all comma-separated values, not just
  // the first.
  const initialStatuses = (searchParams.get('status')?.split(',') ?? []).filter((s): s is DailyStatusValue =>
    STATUS_VALUES.includes(s as DailyStatusValue)
  );

  const [dateFrom, setDateFrom] = useState(initialDate ?? today());
  const [dateTo, setDateTo] = useState(initialDate ?? today());
  const [employeeId, setEmployeeId] = useState<string | number | null>(null);
  const [locationId, setLocationId] = useState('');
  const [statuses, setStatuses] = useState<DailyStatusValue[]>(initialStatuses);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const { data: employees } = useFetch(() => employeesApi.list({ page_size: 100 }).catch(() => null), []);
  const { data: locations } = useFetch(() => locationsApi.list(), [isAdmin]);

  const params = useMemo(
    () => ({
      date_from: dateFrom,
      date_to: dateTo,
      employee_id: employeeId ? Number(employeeId) : undefined,
      location_id: isAdmin && locationId ? Number(locationId) : undefined,
      status: statuses.length ? statuses.join(',') : undefined,
      page,
      page_size: pageSize,
    }),
    [dateFrom, dateTo, employeeId, locationId, statuses, isAdmin, page, pageSize]
  );

  const { data, loading, reload } = useFetch(() => attendanceApi.dailyStatus(params), [JSON.stringify(params)]);

  const hasActiveFilters = !!(employeeId || locationId || statuses.length);
  function clearFilters() {
    setEmployeeId(null);
    setLocationId('');
    setStatuses([]);
    setPage(1);
  }

  async function handleExcusedChange(id: number, value: boolean) {
    try {
      await attendanceApi.setExcused(id, value);
      showToast('success', t('toast.saved'));
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    }
  }

  // Managers approve overtime for their own location too (the API enforces
  // the location check), so this is not gated on isAdmin like excusing is.
  async function handleOvertimeApproval(id: number, approved: boolean) {
    try {
      await attendanceApi.setOvertimeApproval(id, approved);
      showToast('success', t('toast.saved'));
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    }
  }

  const [recomputeOpen, setRecomputeOpen] = useState(false);
  const [recomputeFrom, setRecomputeFrom] = useState(today());
  const [recomputeTo, setRecomputeTo] = useState(today());
  const [recomputeEmployee, setRecomputeEmployee] = useState<string | number | null>(null);
  const [recomputing, setRecomputing] = useState(false);

  async function handleRecompute(e: FormEvent) {
    e.preventDefault();
    setRecomputing(true);
    try {
      await attendanceApi.recompute({
        date_from: recomputeFrom,
        date_to: recomputeTo,
        employee_id: recomputeEmployee ? Number(recomputeEmployee) : undefined,
      });
      showToast('success', t('attendance.recomputeSuccess'));
      setRecomputeOpen(false);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setRecomputing(false);
    }
  }

  const employeeOptions = (employees?.items ?? []).map((e) => ({ value: e.id, label: `${e.first_name} ${e.last_name}` }));

  return (
    <div>
      <PageHeader
        title={isAdmin ? t('attendance.title') : t('attendance.myTeamTitle')}
        actions={
          isAdmin ? (
            <Button variant="secondary" onClick={() => setRecomputeOpen(true)}>
              {t('attendance.recompute')}
            </Button>
          ) : undefined
        }
      />

      <div className="mb-4">
        <FilterBar hasActiveFilters={hasActiveFilters} onClearFilters={clearFilters}>
          <DateRangeInput
            from={dateFrom}
            to={dateTo}
            onFromChange={(v) => {
              setDateFrom(v);
              setPage(1);
            }}
            onToChange={(v) => {
              setDateTo(v);
              setPage(1);
            }}
            fromLabel={t('attendance.dateFrom')}
            toLabel={t('attendance.dateTo')}
          />
          <SearchableSelect
            label={t('attendance.employee')}
            placeholder={t('common.all')}
            value={employeeId}
            onChange={(v) => {
              setEmployeeId(v);
              setPage(1);
            }}
            options={employeeOptions}
            containerClassName="w-56"
          />
          {isAdmin && (
            <Select
              label={t('employees.location')}
              value={locationId}
              onChange={(e) => {
                setLocationId(e.target.value);
                setPage(1);
              }}
              placeholder={t('common.all')}
              options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
              containerClassName="w-48"
            />
          )}
          <MultiSelect
            label={t('attendance.status')}
            value={statuses}
            onChange={(v) => {
              setStatuses(v as DailyStatusValue[]);
              setPage(1);
            }}
            allLabel={t('common.all')}
            options={STATUS_VALUES.map((s) => ({ value: s, label: t(`status.attendance.${s}`) }))}
            containerClassName="w-48"
          />
        </FilterBar>
      </div>

      <AttendanceStatusTable
        rows={data?.items ?? []}
        loading={loading}
        canEditExcused={isAdmin}
        onExcusedChange={handleExcusedChange}
        canApproveOvertime
        onOvertimeApprovalChange={handleOvertimeApproval}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={clearFilters}
        footer={
          data && (
            <Pagination
              page={page}
              pageSize={pageSize}
              total={data.total}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size);
                setPage(1);
              }}
            />
          )
        }
      />

      <Modal open={recomputeOpen} onClose={() => setRecomputeOpen(false)} title={t('attendance.recomputeModalTitle')}>
        <form onSubmit={handleRecompute} className="flex flex-col gap-5">
          <DateRangeInput
            from={recomputeFrom}
            to={recomputeTo}
            onFromChange={setRecomputeFrom}
            onToChange={setRecomputeTo}
            fromLabel={t('attendance.dateFrom')}
            toLabel={t('attendance.dateTo')}
          />
          <SearchableSelect
            label={t('attendance.employee')}
            placeholder={t('common.all')}
            value={recomputeEmployee}
            onChange={setRecomputeEmployee}
            options={employeeOptions}
          />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setRecomputeOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={recomputing}>{t('common.recompute')}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
