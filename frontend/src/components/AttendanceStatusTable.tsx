import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarClock } from 'lucide-react';
import clsx from 'clsx';
import { DataTable } from './ui/Table';
import type { Column } from './ui/Table';
import { AttendanceStatusBadge } from './ui/Badge';
import { formatDate, formatDateTime, formatMinutes, formatTime } from '../lib/format';
import type { AttendanceDailyStatus } from '../api/types';

function ExcusedCell({
  row,
  editable,
  onChange,
}: {
  row: AttendanceDailyStatus;
  editable: boolean;
  onChange?: (id: number, value: boolean) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  if (row.status !== 'absent') return <span className="text-neutral-300">–</span>;

  const excused = !!row.is_absence_excused;
  const label = excused ? t('status.excused') : t('status.unexcused');
  const colorClass = excused ? 'text-success-700' : 'text-danger-700';

  if (!editable) {
    return <span className={clsx('text-caption font-medium', colorClass)}>{label}</span>;
  }

  return (
    <div className="relative inline-block" ref={ref} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={clsx('text-caption font-medium underline decoration-dotted', colorClass)}
      >
        {label}
      </button>
      {open && (
        <div className="absolute z-popover mt-1 w-36 rounded-md border border-neutral-200 bg-white py-1 shadow-md">
          <button
            type="button"
            onClick={() => {
              onChange?.(row.id, true);
              setOpen(false);
            }}
            className="block w-full px-3 py-1.5 text-left text-caption hover:bg-neutral-50"
          >
            {t('status.excused')}
          </button>
          <button
            type="button"
            onClick={() => {
              onChange?.(row.id, false);
              setOpen(false);
            }}
            className="block w-full px-3 py-1.5 text-left text-caption hover:bg-neutral-50"
          >
            {t('status.unexcused')}
          </button>
        </div>
      )}
    </div>
  );
}

function OvertimeCell({
  row,
  editable,
  onChange,
}: {
  row: AttendanceDailyStatus;
  editable: boolean;
  onChange?: (id: number, approved: boolean) => void;
}) {
  const { t } = useTranslation();
  const minutes = <span className="font-mono">{formatMinutes(row.overtime_minutes)}</span>;

  // Only locations whose overtime config requires pre-approval have a pending
  // state at all — everywhere else these minutes simply pay.
  if (!row.overtime_minutes || !row.overtime_requires_approval) return minutes;

  const approved = !!row.overtime_approved_at;
  return (
    <div className="flex flex-col items-end gap-0.5">
      {minutes}
      {editable ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onChange?.(row.id, !approved);
          }}
          className={clsx(
            'text-caption font-medium underline decoration-dotted',
            approved ? 'text-success-700' : 'text-warning-700'
          )}
        >
          {approved ? t('attendance.overtimeApproved') : t('attendance.overtimeApprove')}
        </button>
      ) : (
        <span className={clsx('text-caption font-medium', approved ? 'text-success-700' : 'text-warning-700')}>
          {approved ? t('attendance.overtimeApproved') : t('attendance.overtimePending')}
        </span>
      )}
    </div>
  );
}

interface AttendanceStatusTableProps {
  rows: AttendanceDailyStatus[];
  loading?: boolean;
  showEmployeeColumn?: boolean;
  canEditExcused?: boolean;
  onExcusedChange?: (id: number, value: boolean) => void;
  canApproveOvertime?: boolean;
  onOvertimeApprovalChange?: (id: number, approved: boolean) => void;
  hasActiveFilters?: boolean;
  onClearFilters?: () => void;
  footer?: ReactNode;
}

// Shared attendance daily-status table — used by /attendance (§5.12) and the
// Employee Detail "Attendance History" tab (§5.4), which reuses this exact
// table component pre-filtered to one employee.
export function AttendanceStatusTable({
  rows,
  loading,
  showEmployeeColumn = true,
  canEditExcused = false,
  onExcusedChange,
  canApproveOvertime = false,
  onOvertimeApprovalChange,
  hasActiveFilters,
  onClearFilters,
  footer,
}: AttendanceStatusTableProps) {
  const { t } = useTranslation();

  const columns: Column<AttendanceDailyStatus>[] = [
    { key: 'date', header: t('attendance.date'), render: (r) => <span className="font-mono">{formatDate(r.work_date)}</span> },
    ...(showEmployeeColumn
      ? [{ key: 'employee', header: t('attendance.employee'), render: (r: AttendanceDailyStatus) => r.employee_name ?? '–' } as Column<AttendanceDailyStatus>]
      : []),
    {
      key: 'scheduled',
      header: t('attendance.scheduled'),
      render: (r) =>
        r.scheduled_start && r.scheduled_end ? (
          <span className="font-mono">{formatTime(r.scheduled_start)}–{formatTime(r.scheduled_end)}</span>
        ) : (
          '–'
        ),
    },
    { key: 'actualIn', header: t('attendance.actualIn'), render: (r) => (r.actual_first_in ? <span className="font-mono">{formatDateTime(r.actual_first_in)}</span> : '–') },
    { key: 'actualOut', header: t('attendance.actualOut'), render: (r) => (r.actual_last_out ? <span className="font-mono">{formatDateTime(r.actual_last_out)}</span> : '–') },
    { key: 'late', header: t('attendance.late'), align: 'right', render: (r) => <span className="font-mono">{formatMinutes(r.late_minutes)}</span> },
    {
      key: 'early',
      header: t('attendance.earlyDeparture'),
      align: 'right',
      render: (r) => <span className="font-mono">{formatMinutes(r.early_departure_minutes)}</span>,
    },
    {
      key: 'overtime',
      header: t('attendance.overtime'),
      align: 'right',
      render: (r) => <OvertimeCell row={r} editable={canApproveOvertime} onChange={onOvertimeApprovalChange} />,
    },
    { key: 'break', header: t('attendance.breakMinutes'), align: 'right', render: (r) => <span className="font-mono">{formatMinutes(r.break_minutes_taken)}</span> },
    { key: 'status', header: t('attendance.status'), render: (r) => <AttendanceStatusBadge status={r.status} /> },
    {
      key: 'excused',
      header: t('attendance.excusedLabel'),
      render: (r) => <ExcusedCell row={r} editable={canEditExcused} onChange={onExcusedChange} />,
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      loading={loading}
      emptyIcon={<CalendarClock size={24} />}
      emptyMessage={t('attendance.emptyMessage')}
      hasActiveFilters={hasActiveFilters}
      onClearFilters={onClearFilters}
      footer={footer}
      mobileCard={(r) => ({
        title: r.employee_name ?? <span className="font-mono">{formatDate(r.work_date)}</span>,
        subtitle: showEmployeeColumn ? <span className="font-mono">{formatDate(r.work_date)}</span> : undefined,
        badge: <AttendanceStatusBadge status={r.status} />,
        rows: [
          { label: t('attendance.scheduled'), value: r.scheduled_start && r.scheduled_end ? <span className="font-mono">{formatTime(r.scheduled_start)}–{formatTime(r.scheduled_end)}</span> : '–' },
          { label: t('attendance.actualIn'), value: r.actual_first_in ? <span className="font-mono">{formatDateTime(r.actual_first_in)}</span> : '–' },
          { label: t('attendance.actualOut'), value: r.actual_last_out ? <span className="font-mono">{formatDateTime(r.actual_last_out)}</span> : '–' },
          { label: t('attendance.late'), value: <span className="font-mono">{formatMinutes(r.late_minutes)}</span> },
          { label: t('attendance.overtime'), value: <OvertimeCell row={r} editable={canApproveOvertime} onChange={onOvertimeApprovalChange} /> },
          { label: t('attendance.breakMinutes'), value: <span className="font-mono">{formatMinutes(r.break_minutes_taken)}</span> },
          { label: t('attendance.excusedLabel'), value: <ExcusedCell row={r} editable={canEditExcused} onChange={onExcusedChange} /> },
        ],
      })}
    />
  );
}
