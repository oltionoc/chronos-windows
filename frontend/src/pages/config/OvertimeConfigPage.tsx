import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import { configApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { FilterBar } from '../../components/ui/FilterBar';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Input, CurrencyInput } from '../../components/ui/Input';
import { RadioGroup, Toggle } from '../../components/ui/Controls';
import { EffectiveDatedTable } from '../../components/EffectiveDatedTable';
import type { Column } from '../../components/ui/Table';
import { formatCurrency, formatMinutes } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { OvertimeConfig, OvertimeThresholdBasis } from '../../api/types';

const EMPTY = {
  threshold_basis: 'daily' as OvertimeThresholdBasis,
  daily_threshold_minutes: null as number | null,
  weekly_threshold_minutes: null as number | null,
  rate_per_hour_eur: null as number | null,
  weekend_rate_per_hour_eur: null as number | null,
  holiday_rate_per_hour_eur: null as number | null,
  requires_preapproval: false,
  monthly_cap_minutes: null as number | null,
  effective_from: new Date().toISOString().slice(0, 10),
  location_id: '',
  is_active: true,
};

// /config/overtime — DESIGN_SPEC §5.21
export function OvertimeConfigPage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  usePageTitle(t('config.overtimeTitle'));

  const [locationId, setLocationId] = useState('');
  const { data: locations } = useFetch(() => locationsApi.list(), []);
  const params = useMemo(() => ({ location_id: locationId ? Number(locationId) : undefined }), [locationId]);
  const { data, loading, reload } = useFetch(() => configApi.overtime.list(params), [JSON.stringify(params)]);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [deactivating, setDeactivating] = useState(false);

  function set<K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function openCreate() {
    setEditingId(null);
    setForm(EMPTY);
    setModalOpen(true);
  }

  function openEdit(row: OvertimeConfig) {
    setEditingId(row.id);
    setForm({
      threshold_basis: row.threshold_basis,
      daily_threshold_minutes: row.daily_threshold_minutes,
      weekly_threshold_minutes: row.weekly_threshold_minutes,
      rate_per_hour_eur: row.rate_per_hour_eur,
      weekend_rate_per_hour_eur: row.weekend_rate_per_hour_eur,
      holiday_rate_per_hour_eur: row.holiday_rate_per_hour_eur,
      requires_preapproval: row.requires_preapproval,
      monthly_cap_minutes: row.monthly_cap_minutes,
      effective_from: row.effective_from,
      location_id: row.location_id ? String(row.location_id) : '',
      is_active: row.is_active,
    });
    setModalOpen(true);
  }

  function buildPayload() {
    return {
      threshold_basis: form.threshold_basis,
      daily_threshold_minutes: form.threshold_basis === 'daily' ? form.daily_threshold_minutes : null,
      weekly_threshold_minutes: form.threshold_basis === 'weekly' ? form.weekly_threshold_minutes : null,
      rate_per_hour_eur: form.rate_per_hour_eur!,
      weekend_rate_per_hour_eur: form.weekend_rate_per_hour_eur,
      holiday_rate_per_hour_eur: form.holiday_rate_per_hour_eur,
      requires_preapproval: form.requires_preapproval,
      monthly_cap_minutes: form.monthly_cap_minutes,
      effective_from: form.effective_from,
      location_id: form.location_id ? Number(form.location_id) : null,
    };
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (form.rate_per_hour_eur == null) return;
    setSubmitting(true);
    try {
      if (editingId != null) {
        await configApi.overtime.update(editingId, buildPayload());
        showToast('success', t('toast.saved'));
      } else {
        await configApi.overtime.create(buildPayload());
        showToast('success', t('toast.created'));
      }
      setModalOpen(false);
      setForm(EMPTY);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeactivate() {
    if (editingId == null) return;
    setDeactivating(true);
    try {
      await configApi.overtime.update(editingId, { is_active: false });
      showToast('success', t('toast.saved'));
      setModalOpen(false);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setDeactivating(false);
    }
  }

  const extraColumns: Column<OvertimeConfig>[] = [
    { key: 'basis', header: t('config.thresholdBasis'), render: (r) => (r.threshold_basis === 'daily' ? t('config.daily') : t('config.weekly')) },
    {
      key: 'threshold',
      header: t('config.dailyThresholdMinutes'),
      align: 'right',
      render: (r) => <span className="font-mono">{formatMinutes(r.threshold_basis === 'daily' ? (r.daily_threshold_minutes ?? 0) : (r.weekly_threshold_minutes ?? 0))}</span>,
    },
    { key: 'rate', header: t('config.ratePerHour'), align: 'right', render: (r) => <span className="font-mono">{formatCurrency(r.rate_per_hour_eur)}</span> },
  ];

  return (
    <div>
      <PageHeader
        title={t('config.overtimeTitle')}
        actions={<Button leftIcon={<Plus size={16} />} onClick={openCreate}>{t('config.newRule')}</Button>}
      />

      <div className="mb-4">
        <FilterBar hasActiveFilters={!!locationId} onClearFilters={() => setLocationId('')}>
          <Select
            label={t('config.location')}
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            placeholder={t('common.all')}
            options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
            containerClassName="w-48"
          />
        </FilterBar>
      </div>

      <EffectiveDatedTable
        rows={data ?? []}
        loading={loading}
        extraColumns={extraColumns}
        onRowClick={openEdit}
        emptyMessage={t('config.emptyMessage')}
        mobileExtraRows={(r) => [{ label: t('config.ratePerHour'), value: <span className="font-mono">{formatCurrency(r.rate_per_hour_eur)}</span> }]}
      />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editingId != null ? t('config.editRule') : t('config.newRule')}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <RadioGroup
            name="threshold-basis"
            value={form.threshold_basis}
            onChange={(v) => set('threshold_basis', v as OvertimeThresholdBasis)}
            options={[
              { value: 'daily', label: t('config.daily') },
              { value: 'weekly', label: t('config.weekly') },
            ]}
          />
          {form.threshold_basis === 'daily' ? (
            <Input
              label={t('config.dailyThresholdMinutes')}
              type="number"
              min={0}
              value={form.daily_threshold_minutes ?? ''}
              onChange={(e) => set('daily_threshold_minutes', e.target.value === '' ? null : Number(e.target.value))}
            />
          ) : (
            <Input
              label={t('config.weeklyThresholdMinutes')}
              type="number"
              min={0}
              value={form.weekly_threshold_minutes ?? ''}
              onChange={(e) => set('weekly_threshold_minutes', e.target.value === '' ? null : Number(e.target.value))}
            />
          )}
          <CurrencyInput label={t('config.ratePerHour')} required value={form.rate_per_hour_eur} onChange={(v) => set('rate_per_hour_eur', v)} />
          <CurrencyInput label={t('config.weekendRate')} value={form.weekend_rate_per_hour_eur} onChange={(v) => set('weekend_rate_per_hour_eur', v)} hint={t('config.weekendRateHint')} />
          <CurrencyInput label={`${t('config.holidayRate')} (${t('common.optional')})`} value={form.holiday_rate_per_hour_eur} onChange={(v) => set('holiday_rate_per_hour_eur', v)} />
          <Toggle checked={form.requires_preapproval} onChange={(v) => set('requires_preapproval', v)} label={t('config.requiresPreapproval')} />
          <Input
            label={`${t('config.monthlyCapMinutes')} (${t('common.optional')})`}
            type="number"
            min={0}
            value={form.monthly_cap_minutes ?? ''}
            onChange={(e) => set('monthly_cap_minutes', e.target.value === '' ? null : Number(e.target.value))}
          />
          <Input label={t('config.effectiveFrom')} type="date" required value={form.effective_from} onChange={(e) => set('effective_from', e.target.value)} />
          <Select
            label={t('config.location')}
            placeholder={t('common.all')}
            value={form.location_id}
            onChange={(e) => set('location_id', e.target.value)}
            options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
          />
          <div className="flex justify-end gap-3">
            {editingId != null && form.is_active && (
              <Button type="button" variant="danger-outline" loading={deactivating} onClick={handleDeactivate}>
                {t('config.deactivate')}
              </Button>
            )}
            <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={submitting} disabled={form.rate_per_hour_eur == null}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
