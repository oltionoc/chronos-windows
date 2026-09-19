import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { leaveApi, employeesApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { FormSection, FormErrorBanner, FormFooterBar } from '../../components/ui/FormSection';
import { Input } from '../../components/ui/Input';
import { SearchableSelect, Select } from '../../components/ui/Select';
import { Textarea } from '../../components/ui/Textarea';
import { Button } from '../../components/ui/Button';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import { localizedLeaveTypeName } from '../../lib/leaveTypes';

// /leave/new (T3) — DESIGN_SPEC §5.15
export function LeaveFormPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  usePageTitle(t('leave.newRequest'), [{ label: t('leave.title'), to: '/leave' }, { label: t('leave.newRequest') }]);

  const { data: employees } = useFetch(() => employeesApi.list({ page_size: 100 }), []);
  const { data: leaveTypes } = useFetch(() => leaveApi.leaveTypes(), []);

  const [employeeId, setEmployeeId] = useState<string | number | null>(null);
  const [leaveTypeId, setLeaveTypeId] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [hourly, setHourly] = useState(false);
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [notes, setNotes] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!employeeId) next.employee_id = t('common.required');
    if (!leaveTypeId) next.leave_type_id = t('common.required');
    if (!startDate) next.start_date = t('common.required');
    if (!hourly && !endDate) next.end_date = t('common.required');
    if (hourly) {
      if (!startTime) next.start_time = t('common.required');
      if (!endTime) next.end_time = t('common.required');
      if (startTime && endTime && endTime <= startTime) next.end_time = t('common.required');
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;
    setSubmitting(true);
    try {
      const created = await leaveApi.create({
        employee_id: Number(employeeId),
        leave_type_id: Number(leaveTypeId),
        start_date: startDate,
        end_date: hourly ? startDate : endDate,
        start_time: hourly ? startTime : null,
        end_time: hourly ? endTime : null,
        notes: notes || undefined,
      });
      showToast('success', t('toast.created'));
      navigate(`/leave/${created.id}`);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  const employeeOptions = (employees?.items ?? []).map((e) => ({ value: e.id, label: `${e.first_name} ${e.last_name}` }));
  const activeLeaveTypes = (leaveTypes ?? []).filter((lt) => lt.is_active);

  return (
    <div>
      <PageHeader title={t('leave.newRequest')} />
      <form onSubmit={handleSubmit}>
        <Card className="max-w-[720px]" bodyClassName="p-6">
          {formError && <FormErrorBanner message={formError} onDismiss={() => setFormError(null)} />}
          <FormSection title={t('leave.title')} first>
            <SearchableSelect
              label={t('leave.employee')}
              value={employeeId}
              onChange={setEmployeeId}
              placeholder={t('common.select')}
              options={employeeOptions}
              error={errors.employee_id}
            />
            <Select
              label={t('leave.leaveType')}
              required
              placeholder={t('common.select')}
              value={leaveTypeId}
              onChange={(e) => setLeaveTypeId(e.target.value)}
              options={activeLeaveTypes.map((lt) => ({ value: lt.id, label: localizedLeaveTypeName(lt, i18n.language) }))}
              error={errors.leave_type_id}
            />
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Input label={t('leave.startDate')} type="date" required value={startDate} onChange={(e) => setStartDate(e.target.value)} error={errors.start_date} />
              {!hourly && (
                <Input label={t('leave.endDate')} type="date" required value={endDate} onChange={(e) => setEndDate(e.target.value)} error={errors.end_date} />
              )}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={hourly} onChange={(e) => setHourly(e.target.checked)} />
              {t('leave.hourlyLeave')}
            </label>
            {hourly && (
              <>
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                  <Input label={t('leave.startTime')} type="time" required value={startTime} onChange={(e) => setStartTime(e.target.value)} error={errors.start_time} />
                  <Input label={t('leave.endTime')} type="time" required value={endTime} onChange={(e) => setEndTime(e.target.value)} error={errors.end_time} />
                </div>
                <p className="text-xs text-neutral-500">{t('leave.hourlyHint')}</p>
              </>
            )}
            <Textarea label={t('leave.notesOptional')} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </FormSection>
        </Card>

        <FormFooterBar>
          <Button type="button" variant="secondary" onClick={() => navigate('/leave')}>{t('common.cancel')}</Button>
          <Button type="submit" loading={submitting}>{t('common.save')}</Button>
        </FormFooterBar>
      </form>
    </div>
  );
}
