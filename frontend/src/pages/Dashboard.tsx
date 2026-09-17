import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, Clock, XCircle, CalendarOff, TrendingUp, Timer, AlertTriangle, Coffee } from 'lucide-react';
import { useMemo, useState } from 'react';
import { reportsApi, attendanceApi } from '../api/endpoints';
import { useFetch } from '../lib/useFetch';
import { usePageTitle } from '../layout/PageHeaderContext';
import { PageHeader } from '../components/PageHeader';
import { Card, KpiCard } from '../components/ui/Card';
import { Modal } from '../components/ui/Modal';
import { AttendanceTrendChart } from '../components/ui/MiniChart';
import { AttendanceStatusBadge, LeaveTypeBadge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { formatDate, formatTime } from '../lib/format';
import { localizedLeaveTypeName } from '../lib/leaveTypes';
import type { DailyStatusValue } from '../api/types';

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

type DetailKind = DailyStatusValue | 'on_break';

// / — Dashboard (T4) — DESIGN_SPEC §5.2. No approval workflow (client
// direction 2026-08-27) — leave always auto-approves, so there's no
// pending-review queue on this page anymore.
export function Dashboard() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  usePageTitle(t('nav.dashboard'));

  const { data, loading } = useFetch(() => reportsApi.dashboardSummary({}), []);
  const { data: analytics, loading: analyticsLoading } = useFetch(() => reportsApi.analytics({ days: 14 }), []);

  const [detail, setDetail] = useState<DetailKind | null>(null);
  // "Present" on this dashboard means present-or-late (see reports.py
  // dashboard_summary) — the drill-down and deep-link need to ask for both
  // statuses too, not just a literal "present" match.
  const detailStatusParam = detail === 'present' ? 'present,late' : (detail ?? undefined);
  const attendanceDetailParams = useMemo(
    () => (detail ? { status: detailStatusParam, date_from: today(), date_to: today(), page_size: 10 } : null),
    [detail, detailStatusParam]
  );
  const { data: attendanceDetail, loading: attendanceDetailLoading } = useFetch(
    () => (attendanceDetailParams ? attendanceApi.dailyStatus(attendanceDetailParams) : Promise.resolve(null)),
    [JSON.stringify(attendanceDetailParams)]
  );

  const detailTitle: Record<DetailKind, string> = {
    present: t('dashboard.presentToday'),
    late: t('dashboard.lateToday'),
    absent: t('dashboard.absentToday'),
    on_leave: t('status.attendance.on_leave'),
    holiday: t('status.attendance.holiday'),
    not_scheduled: t('status.attendance.not_scheduled'),
    on_break: t('dashboard.onBreakNow'),
  };

  return (
    <div>
      <PageHeader title={t('nav.dashboard')} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <KpiCard
          icon={CheckCircle2}
          color="success"
          value={data?.present_today ?? 0}
          label={t('dashboard.presentToday')}
          loading={loading}
          onClick={() => setDetail('present')}
          subValue={data?.on_site_now ?? 0}
          subLabel={t('dashboard.onSiteNow')}
        />
        <KpiCard
          icon={Clock}
          color="warning"
          value={data?.late_today ?? 0}
          label={t('dashboard.lateToday')}
          loading={loading}
          onClick={() => setDetail('late')}
        />
        <KpiCard
          icon={XCircle}
          color="danger"
          value={data?.absent_today ?? 0}
          label={t('dashboard.absentToday')}
          loading={loading}
          onClick={() => setDetail('absent')}
        />
        <KpiCard
          icon={Coffee}
          color="violet"
          value={data?.on_break_now ?? 0}
          label={t('dashboard.onBreakNow')}
          loading={loading}
          onClick={() => setDetail('on_break')}
        />
        <KpiCard
          icon={CalendarOff}
          color="violet"
          value={data?.on_leave_today ?? 0}
          label={t('dashboard.onLeaveToday')}
          loading={loading}
          onClick={() => setDetail('on_leave')}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title={t('dashboard.attendanceTrend')} className="lg:col-span-2">
          {analyticsLoading ? (
            <div className="h-40 animate-pulse rounded-sm bg-neutral-100" />
          ) : (
            <AttendanceTrendChart data={analytics?.attendance_trend ?? []} />
          )}
        </Card>

        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-neutral-200 bg-white p-3 shadow-sm">
              <div className="mb-2 flex h-7 w-7 items-center justify-center rounded-full bg-warning-100">
                <Timer size={14} className="text-warning-600" />
              </div>
              {analyticsLoading ? (
                <div className="h-6 w-10 animate-pulse rounded-sm bg-neutral-100" />
              ) : (
                <div className="font-mono text-section-title tabular-nums text-neutral-900">
                  {analytics?.avg_late_minutes ?? 0}
                </div>
              )}
              <div className="mt-1 text-caption text-neutral-500">{t('dashboard.avgLateMinutes')}</div>
            </div>
            <div className="rounded-lg border border-neutral-200 bg-white p-3 shadow-sm">
              <div className="mb-2 flex h-7 w-7 items-center justify-center rounded-full bg-success-100">
                <TrendingUp size={14} className="text-success-600" />
              </div>
              {analyticsLoading ? (
                <div className="h-6 w-10 animate-pulse rounded-sm bg-neutral-100" />
              ) : (
                <div className="font-mono text-section-title tabular-nums text-neutral-900">
                  {analytics?.total_overtime_minutes ?? 0}
                </div>
              )}
              <div className="mt-1 text-caption text-neutral-500">{t('dashboard.totalOvertimeMinutes')}</div>
            </div>
          </div>
          <Card title={t('dashboard.topOvertimeEmployees')} bodyClassName="py-2">
            {analyticsLoading ? (
              <div className="h-24 animate-pulse rounded-sm bg-neutral-100" />
            ) : (analytics?.top_overtime_employees.length ?? 0) === 0 ? (
              <EmptyState icon={TrendingUp} title={t('dashboard.noOvertimeEmployees')} />
            ) : (
              <div className="flex flex-col divide-y divide-neutral-200">
                {analytics?.top_overtime_employees.map((e) => (
                  <div key={e.employee_id} className="flex items-center justify-between gap-3 py-2">
                    <span className="text-body text-neutral-800">{e.employee_name}</span>
                    <span className="flex items-center gap-3 text-caption text-neutral-500">
                      <span className="font-mono">{t('dashboard.overtimeDaysCount', { count: e.overtime_days })}</span>
                      <span className="font-mono font-medium text-success-700">
                        {t('dashboard.totalMinutes', { minutes: e.total_overtime_minutes })}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>

      <div className="mt-6">
        <Card title={t('dashboard.topLateEmployees')}>
          {analyticsLoading ? (
            <div className="h-16 animate-pulse rounded-sm bg-neutral-100" />
          ) : (analytics?.top_late_employees.length ?? 0) === 0 ? (
            <EmptyState icon={AlertTriangle} title={t('dashboard.noLateEmployees')} />
          ) : (
            <div className="flex flex-col divide-y divide-neutral-200">
              {analytics?.top_late_employees.map((e) => (
                <div key={e.employee_id} className="flex items-center justify-between gap-3 py-2.5">
                  <span className="text-body text-neutral-800">{e.employee_name}</span>
                  <span className="flex items-center gap-3 text-caption text-neutral-500">
                    <span className="font-mono">{t('dashboard.lateDaysCount', { count: e.late_days })}</span>
                    <span className="font-mono font-medium text-warning-700">
                      {t('dashboard.totalMinutes', { minutes: e.total_late_minutes })}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Modal
        open={detail !== null}
        onClose={() => setDetail(null)}
        title={detail ? detailTitle[detail] : ''}
        size="lg"
        footer={
          detail && detail !== 'on_break' && (
            <Button
              variant="link"
              onClick={() => {
                navigate(`/attendance?status=${detailStatusParam}&date=${today()}`);
                setDetail(null);
              }}
            >
              {t('dashboard.viewAll')}
            </Button>
          )
        }
      >
        {detail === 'on_break' ? (
          (data?.on_break_employees.length ?? 0) === 0 ? (
            <EmptyState icon={Coffee} title={t('dashboard.noOneOnBreak')} />
          ) : (
            <div className="flex flex-col divide-y divide-neutral-200">
              {data?.on_break_employees.map((e) => (
                <div key={e.employee_id} className="flex items-center justify-between gap-3 py-3">
                  <span className="text-body font-medium text-neutral-800">{e.employee_name}</span>
                  <span className="font-mono text-caption text-neutral-500">
                    {t('dashboard.sinceTime', { time: formatTime(e.break_started_at) })}
                  </span>
                </div>
              ))}
            </div>
          )
        ) : detail === 'on_leave' ? (
          (data?.on_leave_employees.length ?? 0) === 0 ? (
            <EmptyState icon={CalendarOff} title={t('dashboard.noOneOnLeave')} />
          ) : (
            <div className="flex flex-col divide-y divide-neutral-200">
              {data?.on_leave_employees.map((e) => (
                <div key={e.employee_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="flex items-center gap-3">
                    <span className="text-body font-medium text-neutral-800">{e.employee_name}</span>
                    <LeaveTypeBadge name={localizedLeaveTypeName({ name_en: e.leave_type_name_en, name_sq: e.leave_type_name_sq }, i18n.language)} />
                  </div>
                  <span className="font-mono text-caption text-neutral-500">
                    {formatDate(e.start_date)} – {formatDate(e.end_date)}
                  </span>
                </div>
              ))}
            </div>
          )
        ) : attendanceDetailLoading ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded-sm bg-neutral-100" />
            ))}
          </div>
        ) : !attendanceDetail || attendanceDetail.items.length === 0 ? (
          <EmptyState icon={CheckCircle2} title={t('attendance.emptyMessage')} />
        ) : (
          <div className="flex flex-col divide-y divide-neutral-200">
            {attendanceDetail.items.map((row) => (
              <div key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="flex items-center gap-3">
                  <span className="text-body font-medium text-neutral-800">{row.employee_name}</span>
                  <AttendanceStatusBadge status={row.status} />
                  {row.late_minutes > 0 && (
                    <span className="font-mono text-caption text-neutral-500">+{row.late_minutes} min</span>
                  )}
                </div>
                <span className="font-mono text-caption text-neutral-500">
                  {row.actual_first_in ? formatTime(row.actual_first_in) : '–'}
                  {row.actual_last_out ? ` – ${formatTime(row.actual_last_out)}` : ''}
                </span>
              </div>
            ))}
            {attendanceDetail.total > attendanceDetail.items.length && (
              <p className="pt-3 text-caption text-neutral-500">
                +{attendanceDetail.total - attendanceDetail.items.length} more
              </p>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
