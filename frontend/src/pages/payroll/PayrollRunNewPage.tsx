import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { payrollApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { FormSection, FormErrorBanner, FormFooterBar } from '../../components/ui/FormSection';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { ApiError } from '../../api/client';

const CURRENT_YEAR = new Date().getFullYear();
const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

// /payroll/runs/new (T3, compact) — DESIGN_SPEC §5.18
export function PayrollRunNewPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  usePageTitle(t('payroll.newRun'), [{ label: t('payroll.runsTitle'), to: '/payroll/runs' }, { label: t('payroll.newRun') }]);

  const { data: locations } = useFetch(() => locationsApi.list(), []);

  const [periodYear, setPeriodYear] = useState(CURRENT_YEAR);
  const [periodMonth, setPeriodMonth] = useState(String(new Date().getMonth() + 1));
  const [locationId, setLocationId] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const next: Record<string, string> = {};
    if (!locationId) next.location_id = t('common.required');
    setErrors(next);
    if (Object.keys(next).length) return;

    setSubmitting(true);
    try {
      const created = await payrollApi.createRun({
        period_year: periodYear,
        period_month: Number(periodMonth),
        location_id: Number(locationId),
      });
      navigate(`/payroll/runs/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setErrors({ location_id: t('payroll.conflictError') });
      } else {
        setFormError(err instanceof ApiError ? err.message : t('toast.error'));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader title={t('payroll.newRun')} />
      <form onSubmit={handleSubmit}>
        <Card className="max-w-[480px]" bodyClassName="p-6">
          {formError && <FormErrorBanner message={formError} onDismiss={() => setFormError(null)} />}
          <FormSection title={t('payroll.newRun')} first>
            <Input label={t('payroll.periodYear')} type="number" required value={periodYear} onChange={(e) => setPeriodYear(Number(e.target.value))} />
            <Select
              label={t('payroll.periodMonth')}
              value={periodMonth}
              onChange={(e) => setPeriodMonth(e.target.value)}
              options={MONTHS.map((m) => ({ value: m, label: t(`payroll.months.${m}`) }))}
            />
            <Select
              label={t('payroll.location')}
              required
              placeholder={t('common.select')}
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
              error={errors.location_id}
            />
          </FormSection>
        </Card>

        <FormFooterBar>
          <Button type="button" variant="secondary" onClick={() => navigate('/payroll/runs')}>{t('common.cancel')}</Button>
          <Button type="submit" loading={submitting}>{t('payroll.generateRun')}</Button>
        </FormFooterBar>
      </form>
    </div>
  );
}
