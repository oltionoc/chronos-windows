import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { employeesApi, locationsApi, usersApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { FormSection, FormErrorBanner, FormFooterBar } from '../../components/ui/FormSection';
import { Input, CurrencyInput } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { EmploymentStatus } from '../../api/types';

const STATUS_VALUES: EmploymentStatus[] = ['active', 'inactive', 'terminated'];

interface FormState {
  first_name: string;
  last_name: string;
  employee_code: string;
  national_id: string;
  job_title: string;
  hire_date: string;
  location_id: string;
  base_salary_eur: number | null;
  manager_user_id: string;
  employment_status: EmploymentStatus;
}

const EMPTY_FORM: FormState = {
  first_name: '',
  last_name: '',
  employee_code: '',
  national_id: '',
  job_title: '',
  hire_date: '',
  location_id: '',
  base_salary_eur: null,
  manager_user_id: '',
  employment_status: 'active',
};

// /employees/new, /employees/:id/edit (T3) — DESIGN_SPEC §5.5
export function EmployeeFormPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { id } = useParams();
  const isEdit = !!id;
  usePageTitle(
    isEdit ? t('common.edit') : t('employees.newEmployee'),
    [
      { label: t('employees.title'), to: '/employees' },
      { label: isEdit ? t('common.edit') : t('employees.newEmployee') },
    ]
  );

  const { data: locations } = useFetch(() => locationsApi.list(), []);
  const { data: managers } = useFetch(() => usersApi.list({ role: 'manager', page_size: 100 }), []);
  const { data: existing } = useFetch(() => (isEdit ? employeesApi.get(Number(id)) : Promise.resolve(null)), [id]);

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [dirty, setDirty] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (existing) {
      setForm({
        first_name: existing.first_name,
        last_name: existing.last_name,
        employee_code: existing.employee_code,
        national_id: existing.national_id ?? '',
        job_title: existing.job_title ?? '',
        hire_date: existing.hire_date,
        location_id: String(existing.location_id),
        base_salary_eur: existing.base_salary_eur,
        manager_user_id: existing.manager_user_id ? String(existing.manager_user_id) : '',
        employment_status: existing.employment_status,
      });
    }
  }, [existing]);

  useEffect(() => {
    function beforeUnload(e: BeforeUnloadEvent) {
      if (dirty) e.preventDefault();
    }
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  }

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!form.first_name.trim()) next.first_name = t('common.required');
    if (!form.last_name.trim()) next.last_name = t('common.required');
    if (!form.employee_code.trim()) next.employee_code = t('common.required');
    if (!form.hire_date) next.hire_date = t('common.required');
    if (!form.location_id) next.location_id = t('common.required');
    if (form.base_salary_eur == null) next.base_salary_eur = t('common.required');
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
        first_name: form.first_name,
        last_name: form.last_name,
        employee_code: form.employee_code,
        national_id: form.national_id || null,
        job_title: form.job_title || null,
        hire_date: form.hire_date,
        location_id: Number(form.location_id),
        base_salary_eur: form.base_salary_eur!,
        manager_user_id: form.manager_user_id ? Number(form.manager_user_id) : null,
        employment_status: form.employment_status,
      };
      if (isEdit) {
        await employeesApi.update(Number(id), payload);
        showToast('success', t('toast.saved'));
        navigate(`/employees/${id}`);
      } else {
        const created = await employeesApi.create(payload);
        showToast('success', t('toast.created'));
        navigate(`/employees/${created.id}`);
      }
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader title={isEdit ? t('common.edit') : t('employees.newEmployee')} />
      <form onSubmit={handleSubmit}>
        <Card className="max-w-[720px]" bodyClassName="p-6">
          {formError && <FormErrorBanner message={formError} onDismiss={() => setFormError(null)} />}

          <FormSection title={t('employees.basicInfoSection')} first>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Input
                label={t('employees.firstName')}
                required
                value={form.first_name}
                onChange={(e) => set('first_name', e.target.value)}
                error={errors.first_name}
              />
              <Input
                label={t('employees.lastName')}
                required
                value={form.last_name}
                onChange={(e) => set('last_name', e.target.value)}
                error={errors.last_name}
              />
              <Input
                label={t('employees.code')}
                required
                className="font-mono"
                value={form.employee_code}
                onChange={(e) => set('employee_code', e.target.value)}
                error={errors.employee_code}
              />
              <Input
                label={t('employees.nationalId')}
                value={form.national_id}
                onChange={(e) => set('national_id', e.target.value)}
              />
              <Input
                label={t('employees.jobTitle')}
                value={form.job_title}
                onChange={(e) => set('job_title', e.target.value)}
              />
              <Input
                label={t('employees.hireDate')}
                type="date"
                required
                value={form.hire_date}
                onChange={(e) => set('hire_date', e.target.value)}
                error={errors.hire_date}
              />
            </div>
          </FormSection>

          <FormSection title={t('employees.employmentSection')}>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Select
                label={t('employees.location')}
                required
                placeholder={t('common.select')}
                value={form.location_id}
                onChange={(e) => set('location_id', e.target.value)}
                options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
                error={errors.location_id}
              />
              <CurrencyInput
                label={t('employees.baseSalary')}
                required
                value={form.base_salary_eur}
                onChange={(v) => set('base_salary_eur', v)}
                error={errors.base_salary_eur}
              />
              <Select
                label={t('employees.manager')}
                placeholder={t('common.none')}
                value={form.manager_user_id}
                onChange={(e) => set('manager_user_id', e.target.value)}
                options={(managers?.items ?? []).map((m) => ({ value: m.id, label: m.username }))}
              />
              {isEdit && (
                <Select
                  label={t('employees.status')}
                  value={form.employment_status}
                  onChange={(e) => set('employment_status', e.target.value as EmploymentStatus)}
                  options={STATUS_VALUES.map((s) => ({ value: s, label: t(`status.employment.${s}`) }))}
                />
              )}
            </div>
          </FormSection>
        </Card>

        <FormFooterBar>
          <Button type="button" variant="secondary" onClick={() => navigate(isEdit ? `/employees/${id}` : '/employees')}>
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
