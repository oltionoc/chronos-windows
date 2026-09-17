import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CalendarClock, Plus } from 'lucide-react';
import clsx from 'clsx';
import { shiftSchedulesApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { FilterBar } from '../../components/ui/FilterBar';
import { Select } from '../../components/ui/Select';
import { Toggle } from '../../components/ui/Controls';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { ActiveBadge } from '../../components/ui/Badge';
import { formatMinutes } from '../../lib/format';
import type { ShiftSchedule } from '../../api/types';

function WorkingDaysChips({ schedule }: { schedule: ShiftSchedule }) {
  const { t } = useTranslation();
  if (!schedule.days) return <span className="text-neutral-300">–</span>;
  return (
    <div className="flex gap-1">
      {schedule.days
        .slice()
        .sort((a, b) => a.day_of_week - b.day_of_week)
        .map((d) => (
          <span
            key={d.day_of_week}
            className={clsx(
              'rounded-sm px-1.5 py-0.5 text-caption',
              d.is_working_day ? 'bg-primary-100 text-primary-700' : 'text-neutral-400'
            )}
          >
            {t(`shiftSchedules.daysShort.${d.day_of_week}`)}
          </span>
        ))}
    </div>
  );
}

// /shift-schedules (T1) — DESIGN_SPEC §5.6
export function ShiftScheduleListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  usePageTitle(t('shiftSchedules.title'));

  const [locationId, setLocationId] = useState('');
  const [activeOnly, setActiveOnly] = useState(true);

  const { data: locations } = useFetch(() => locationsApi.list(), []);
  const params = useMemo(() => ({ location_id: locationId ? Number(locationId) : undefined }), [locationId]);
  const { data, loading } = useFetch(() => shiftSchedulesApi.list(params), [JSON.stringify(params)]);

  const rows = useMemo(() => (data ?? []).filter((s) => (activeOnly ? s.is_active : true)), [data, activeOnly]);
  const hasActiveFilters = !!locationId || !activeOnly;

  const columns: Column<ShiftSchedule>[] = [
    { key: 'name', header: t('shiftSchedules.name'), render: (s) => <span className="font-medium">{s.name}</span> },
    { key: 'location', header: t('shiftSchedules.location'), render: (s) => s.location_name ?? '–' },
    { key: 'days', header: t('shiftSchedules.workingDays'), render: (s) => <WorkingDaysChips schedule={s} /> },
    { key: 'grace', header: t('shiftSchedules.graceMinutes'), align: 'right', render: (s) => <span className="font-mono">{formatMinutes(s.grace_minutes_late)}</span> },
    {
      key: 'active',
      header: t('shiftSchedules.active'),
      render: (s) => <ActiveBadge active={s.is_active} />,
    },
  ];

  return (
    <div>
      <PageHeader
        title={t('shiftSchedules.title')}
        actions={
          <Button leftIcon={<Plus size={16} />} onClick={() => navigate('/shift-schedules/new')}>
            {t('shiftSchedules.newSchedule')}
          </Button>
        }
      />

      <div className="mb-4">
        <FilterBar
          hasActiveFilters={hasActiveFilters}
          onClearFilters={() => {
            setLocationId('');
            setActiveOnly(true);
          }}
        >
          <Select
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            placeholder={t('common.all')}
            options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
            containerClassName="w-48"
            aria-label={t('shiftSchedules.location')}
          />
          <Toggle checked={activeOnly} onChange={setActiveOnly} label={t('shiftSchedules.activeOnly')} />
        </FilterBar>
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(s) => s.id}
        loading={loading}
        onRowClick={(s) => navigate(`/shift-schedules/${s.id}/edit`)}
        emptyIcon={<CalendarClock size={24} />}
        emptyMessage={t('shiftSchedules.emptyMessage')}
        hasActiveFilters={hasActiveFilters}
        onClearFilters={() => {
          setLocationId('');
          setActiveOnly(true);
        }}
        mobileCard={(s) => ({
          title: s.name,
          subtitle: s.location_name,
          badge: <ActiveBadge active={s.is_active} />,
          rows: [{ label: t('shiftSchedules.graceMinutes'), value: <span className="font-mono">{formatMinutes(s.grace_minutes_late)}</span> }],
        })}
      />
    </div>
  );
}
