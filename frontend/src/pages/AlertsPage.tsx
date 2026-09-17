import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, AlertOctagon, CheckCircle2 } from 'lucide-react';
import { reportsApi } from '../api/endpoints';
import { useFetch } from '../lib/useFetch';
import { usePageTitle } from '../layout/PageHeaderContext';
import { PageHeader } from '../components/PageHeader';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { formatDate, formatDateTime } from '../lib/format';
import { alertKey, getSeenAlertKeys, markAlertsSeen } from '../lib/alertsSeen';
import type { AlertItem } from '../api/types';

const SEVERITY_ICON = { warning: AlertTriangle, danger: AlertOctagon } as const;
const SEVERITY_COLOR = { warning: 'text-warning-600 bg-warning-100', danger: 'text-danger-600 bg-danger-100' } as const;

// The backend's `message` field is always English (built once, server-side,
// from data — not per-viewer). Build the actual displayed string from
// `type` + structured fields via i18n instead, so Albanian-locale users see
// Albanian text; fall back to the raw `message` for any alert `type` this
// frontend doesn't recognize yet (forward-compatible, never blank).
function alertMessage(t: (key: string, opts?: Record<string, unknown>) => string, a: AlertItem): string {
  switch (a.type) {
    case 'missing_checkout':
      return t('alerts.types.missing_checkout', { name: a.employee_name });
    case 'stuck_on_break':
      return t('alerts.types.stuck_on_break', { name: a.employee_name });
    case 'not_checked_in':
      return t('alerts.types.not_checked_in', { name: a.employee_name });
    case 'unresolved_punches':
      return t('alerts.types.unresolved_punches', { count: a.count });
    case 'punch_outside_schedule':
      return t('alerts.types.punch_outside_schedule', { name: a.employee_name, count: a.count });
    case 'overtime_pending_approval':
      return t('alerts.types.overtime_pending_approval', { name: a.employee_name, count: a.count });
    case 'device_clock_drift':
      return t('alerts.types.device_clock_drift', {
        label: a.device_label,
        minutes: Math.abs(a.count ?? 0),
        direction: t((a.count ?? 0) > 0 ? 'alerts.ahead' : 'alerts.behind'),
      });
    case 'device_stale':
      return t('alerts.types.device_stale', { label: a.device_label });
    case 'backup_missing':
    case 'backup_failed':
      return t(`alerts.types.${a.type}`);
    case 'backup_stale':
      return t('alerts.types.backup_stale', { count: a.count });
    case 'manager_no_location':
      return t('alerts.types.manager_no_location', { username: a.username });
    default:
      return a.message;
  }
}

// /alerts — operational anomalies the system detected automatically
// (missing checkouts, unresolved punches, stale devices, unassigned
// managers). Not part of DESIGN_SPEC's original route inventory — added on
// direct request after the missing-checkout payroll bug was found; follows
// the same Card/EmptyState/list patterns already used on the Dashboard.
export function AlertsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  usePageTitle(t('nav.alerts'));

  const { data, loading } = useFetch(() => reportsApi.alerts({ days: 14 }), []);
  const alerts = data?.alerts ?? [];

  // Snapshot which keys were already seen BEFORE marking the current batch
  // as seen, so this render can still grey out ones seen on a prior visit
  // (and the sidebar dot clears once this page has been opened).
  const [seenSnapshot, setSeenSnapshot] = useState<Set<string> | null>(null);
  useEffect(() => {
    if (!data) return;
    setSeenSnapshot(getSeenAlertKeys());
    markAlertsSeen(data.alerts.map(alertKey));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  return (
    <div>
      <PageHeader title={t('nav.alerts')} subtitle={t('alerts.subtitle')} />

      <Card>
        {loading ? (
          <div className="flex flex-col gap-2 p-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-sm bg-neutral-100" />
            ))}
          </div>
        ) : alerts.length === 0 ? (
          <EmptyState icon={CheckCircle2} title={t('alerts.empty')} subtitle={t('alerts.emptyDesc')} />
        ) : (
          <div className="flex flex-col divide-y divide-neutral-200">
            {alerts.map((a, i) => {
              const Icon = SEVERITY_ICON[a.severity];
              const isRead = seenSnapshot?.has(alertKey(a)) ?? false;
              return (
                <div
                  key={i}
                  className={[
                    'flex items-start gap-3 py-3',
                    a.link ? 'cursor-pointer hover:bg-neutral-50' : '',
                    isRead ? 'opacity-50' : '',
                  ].join(' ')}
                  onClick={a.link ? () => navigate(a.link!) : undefined}
                >
                  <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${SEVERITY_COLOR[a.severity]}`}>
                    <Icon size={16} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-body text-neutral-800">{alertMessage(t, a)}</p>
                    {(a.occurred_at || a.work_date) && (
                      <p className="mt-0.5 font-mono text-caption text-neutral-500">
                        {a.occurred_at ? formatDateTime(a.occurred_at) : formatDate(a.work_date!)}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
