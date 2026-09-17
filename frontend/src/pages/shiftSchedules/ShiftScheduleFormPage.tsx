import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { shiftSchedulesApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { FormSection, FormErrorBanner, FormFooterBar } from '../../components/ui/FormSection';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Toggle } from '../../components/ui/Controls';
import { Button } from '../../components/ui/Button';
import { ShiftDayGrid } from '../../components/ShiftDayGrid';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { ShiftScheduleDay } from '../../api/types';

function defaultDays(): ShiftScheduleDay[] {
  return Array.from({ length: 7 }, (_, day_of_week) => ({
    day_of_week,
    is_working_day: day_of_week < 5,
    work_start_time: day_of_week < 5 ? '08:00' : null,
    work_end_time: day_of_week < 5 ? '16:00' : null,
    work_windows: day_of_week < 5 ? [{ work_start_time: '08:00', work_end_time: '16:00' }] : [],
    break_windows: [],
  }));
}

// /shift-schedules/new, /shift-schedules/:id/edit (T3, wide) — DESIGN_SPEC §5.7
export function ShiftScheduleFormPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { id } = useParams();
  const isEdit = !!id;
  usePageTitle(
    isEdit ? t('common.edit') : t('shiftSchedules.newSchedule'),
    [{ label: t('shiftSchedules.title'), to: '/shift-schedules' }, { label: isEdit ? t('common.edit') : t('shiftSchedules.newSchedule') }]
  );

  const { data: locations } = useFetch(() => locationsApi.list(), []);
  const { data: existing } = useFetch(() => (isEdit ? shiftSchedulesApi.get(Number(id)) : Promise.resolve(null)), [id]);

  const [name, setName] = useState('');
  const [locationId, setLocationId] = useState('');
  const [graceMinutes, setGraceMinutes] = useState(0);
  const [active, setActive] = useState(true);
  const [days, setDays] = useState<ShiftScheduleDay[]>(defaultDays());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (existing) {
      setName(existing.name);
      setLocationId(existing.location_id != null ? String(existing.location_id) : '');
      setGraceMinutes(existing.grace_minutes_late);
      setActive(existing.is_active);
      if (existing.days && existing.days.length === 7) {
        setDays(
          existing.days.map((d) => ({
            ...d,
            break_windows: d.break_windows ?? [],
            // A day saved before split shifts existed comes back with only the
            // start/end pair; treat it as one block so editing it works.
            work_windows:
              d.work_windows?.length
                ? d.work_windows
                : d.is_working_day && d.work_start_time && d.work_end_time
                  ? [{ work_start_time: d.work_start_time, work_end_time: d.work_end_time }]
                  : [],
          }))
        );
      }
    }
  }, [existing]);

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = t('common.required');
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;
    setSubmitting(true);
    try {
      const payload = {
        name,
        location_id: locationId ? Number(locationId) : null,
        grace_minutes_late: graceMinutes,
        is_active: active,
      };
      const scheduleId = isEdit ? Number(id) : (await shiftSchedulesApi.create(payload)).id;
      if (isEdit) await shiftSchedulesApi.update(scheduleId, payload);
      await shiftSchedulesApi.putDays(scheduleId, days);
      showToast('success', isEdit ? t('toast.saved') : t('toast.created'));
      navigate('/shift-schedules');
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader title={isEdit ? t('common.edit') : t('shiftSchedules.newSchedule')} />
      <form onSubmit={handleSubmit}>
        <Card className="max-w-[880px]" bodyClassName="p-6">
          {formError && <FormErrorBanner message={formError} onDismiss={() => setFormError(null)} />}

          <FormSection title={t('shiftSchedules.scheduleInfoSection')} first>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
              <Input label={t('shiftSchedules.name')} required value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
              <Select
                label={t('shiftSchedules.location')}
                placeholder={t('common.none')}
                value={locationId}
                onChange={(e) => setLocationId(e.target.value)}
                options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
              />
              <Input
                label={t('shiftSchedules.graceMinutesLate')}
                type="number"
                min={0}
                value={graceMinutes}
                onChange={(e) => setGraceMinutes(Number(e.target.value))}
                hint={t('common.min')}
              />
            </div>
            <Toggle checked={active} onChange={setActive} label={t('shiftSchedules.active')} />
          </FormSection>

          <FormSection title={t('shiftSchedules.weeklyPatternSection')}>
            <ShiftDayGrid days={days} onChange={setDays} />
          </FormSection>
        </Card>

        <FormFooterBar>
          <Button type="button" variant="secondary" onClick={() => navigate('/shift-schedules')}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" loading={submitting}>
            {t('common.save')}
          </Button>
        </FormFooterBar>
      </form>
    </div>
  );
}
