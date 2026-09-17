import type { ReactNode } from 'react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import type {
  AdjustmentType,
  DailyStatusValue,
  EmploymentStatus,
  LeaveStatus,
  PayrollRunStatus,
  PunchType,
  Role,
} from '../../api/types';

interface BadgeProps {
  children: ReactNode;
  className?: string;
  outline?: boolean;
  strike?: boolean;
}

// Generic pill — DESIGN_SPEC §6.8
export function Badge({ children, className, outline, strike }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-badge',
        outline && 'border bg-transparent',
        strike && 'line-through',
        className
      )}
    >
      {children}
    </span>
  );
}

const attendanceMap: Record<DailyStatusValue, string> = {
  present: 'bg-success-100 text-success-700',
  late: 'bg-warning-100 text-warning-700',
  absent: 'bg-danger-100 text-danger-700',
  on_leave: 'bg-violet-100 text-violet-700',
  holiday: 'bg-neutral-100 text-neutral-600',
  not_scheduled: 'border-neutral-300 text-neutral-500',
};

export function AttendanceStatusBadge({ status }: { status: DailyStatusValue }) {
  const { t } = useTranslation();
  return (
    <Badge outline={status === 'not_scheduled'} className={attendanceMap[status]}>
      {t(`status.attendance.${status}`)}
    </Badge>
  );
}

const leaveMap: Record<LeaveStatus, string> = {
  pending: 'bg-warning-100 text-warning-700',
  approved: 'bg-success-100 text-success-700',
  rejected: 'bg-danger-100 text-danger-700',
  cancelled: 'bg-neutral-100 text-neutral-500',
};

export function LeaveStatusBadge({ status }: { status: LeaveStatus }) {
  const { t } = useTranslation();
  return (
    <Badge strike={status === 'cancelled'} className={leaveMap[status]}>
      {t(`status.leave.${status}`)}
    </Badge>
  );
}

const employmentMap: Record<EmploymentStatus, string> = {
  active: 'bg-success-100 text-success-700',
  inactive: 'bg-neutral-100 text-neutral-600',
  terminated: 'bg-danger-100 text-danger-700',
};

export function EmploymentStatusBadge({ status }: { status: EmploymentStatus }) {
  const { t } = useTranslation();
  return <Badge className={employmentMap[status]}>{t(`status.employment.${status}`)}</Badge>;
}

const payrollMap: Record<PayrollRunStatus, string> = {
  draft: 'bg-warning-100 text-warning-700',
  finalized: 'bg-success-100 text-success-700',
};

export function PayrollStatusBadge({ status }: { status: PayrollRunStatus }) {
  const { t } = useTranslation();
  return <Badge className={payrollMap[status]}>{t(`status.payrollRun.${status}`)}</Badge>;
}

export function PunchTypeBadge({ type }: { type: PunchType | null }) {
  const { t } = useTranslation();
  const value = type ?? 'unclassified';
  return (
    <Badge
      outline
      className={clsx(
        'border-neutral-300 text-neutral-700',
        value === 'unclassified' && 'border-l-2 border-l-warning-500'
      )}
    >
      {t(`status.punchType.${value}`)}
    </Badge>
  );
}

const roleMap: Record<Role, string> = {
  admin: 'bg-primary-100 text-primary-700',
  manager: 'bg-violet-100 text-violet-700',
};

export function RoleBadge({ role }: { role: Role }) {
  const { t } = useTranslation();
  return <Badge className={roleMap[role]}>{t(`status.role.${role}`)}</Badge>;
}

export function AdjustmentTypeBadge({ type }: { type: AdjustmentType }) {
  const { t } = useTranslation();
  return (
    <Badge
      outline
      className={type === 'bonus' ? 'border-success-300 text-success-700' : 'border-danger-300 text-danger-700'}
    >
      {t(`status.adjustment.${type}`)}
    </Badge>
  );
}

// Shared read-only active/inactive badge — used wherever a resource has a
// plain `is_active` flag (devices, shift schedules, locations), so the same
// concept renders identically everywhere instead of each page inlining its
// own color classes.
export function ActiveBadge({ active }: { active: boolean }) {
  const { t } = useTranslation();
  return (
    <Badge className={active ? 'bg-success-100 text-success-700' : 'bg-neutral-100 text-neutral-600'}>
      {active ? t('common.active') : t('common.inactive')}
    </Badge>
  );
}

export function CurrentBadge() {
  const { t } = useTranslation();
  return <Badge className="bg-success-100 text-success-700">{t('common.current')}</Badge>;
}

export function LeaveTypeBadge({ name }: { name: string }) {
  return <Badge outline className="border-neutral-300 text-neutral-700">{name}</Badge>;
}

export function ExcusedBadge({ excused }: { excused: boolean }) {
  const { t } = useTranslation();
  return (
    <Badge
      outline
      className={excused ? 'border-success-300 text-success-700' : 'border-danger-300 text-danger-700'}
    >
      {excused ? t('status.excused') : t('status.unexcused')}
    </Badge>
  );
}

// ---- Status Dot (DESIGN_SPEC §6.9) ----
type DotColor = 'success' | 'danger' | 'neutral' | 'warning';

const dotMap: Record<DotColor, string> = {
  success: 'bg-success-500',
  danger: 'bg-danger-500',
  neutral: 'bg-neutral-300',
  warning: 'bg-warning-500',
};

export function StatusDot({ color, pulse }: { color: DotColor; pulse?: boolean }) {
  return <span className={clsx('inline-block h-1.5 w-1.5 rounded-full', dotMap[color], pulse && 'animate-pulse')} />;
}
