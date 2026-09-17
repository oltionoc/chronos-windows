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
import { RadioGroup } from '../../components/ui/Controls';
import { EffectiveDatedTable } from '../../components/EffectiveDatedTable';
import type { Column } from '../../components/ui/Table';
import { formatCurrency, formatMinutes } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { PenaltyConfig, PenaltyRuleType } from '../../api/types';

const EMPTY = {
  rule_type: 'flat_per_minute' as PenaltyRuleType,
  rate_per_minute_eur: null as number | null,
  allowance_minutes: null as number | null,
  flat_amount_eur: null as number | null,
  max_daily_penalty_eur: null as number | null,
  early_departure_rate_per_minute_eur: null as number | null,
  effective_from: new Date().toISOString().slice(0, 10),
  location_id: '',
  is_active: true,
};

// /config/penalties — DESIGN_SPEC §5.21
export function PenaltiesConfigPage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  usePageTitle(t('config.penaltiesTitle'));

  const [locationId, setLocationId] = useState('');
  const { data: locations } = useFetch(() => locationsApi.list(), []);
  const params = useMemo(() => ({ location_id: locationId ? Number(locationId) : undefined }), [locationId]);
  const { data, loading, reload } = useFetch(() => configApi.penalty.list(params), [JSON.stringify(params)]);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [deactivating, setDeactivating] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  function set<K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function openCreate() {
    setEditingId(null);
    setForm(EMPTY);
    setShowAdvanced(false);
    setModalOpen(true);
  }

  function openEdit(row: PenaltyConfig) {
    setEditingId(row.id);
    setForm({
      rule_type: row.rule_type,
      rate_per_minute_eur: row.rate_per_minute_eur,
      allowance_minutes: row.allowance_minutes,
      flat_amount_eur: row.flat_amount_eur,
      max_daily_penalty_eur: row.max_daily_penalty_eur,
      early_departure_rate_per_minute_eur: row.early_departure_rate_per_minute_eur,
      effective_from: row.effective_from,
      location_id: row.location_id ? String(row.location_id) : '',
      is_active: row.is_active,
    });
    // Auto-expand if this rule already uses an advanced field, so editing
    // never hides a value that's actually set.
    setShowAdvanced(row.max_daily_penalty_eur != null || !!row.early_departure_rate_per_minute_eur);
    setModalOpen(true);
  }

  function buildPayload() {
    return {
      rule_type: form.rule_type,
      rate_per_minute_eur: form.rule_type === 'flat_per_minute' ? form.rate_per_minute_eur : null,
      allowance_minutes: form.rule_type === 'threshold_allowance' ? form.allowance_minutes : null,
      flat_amount_eur: form.rule_type === 'threshold_allowance' ? form.flat_amount_eur : null,
      max_daily_penalty_eur: form.max_daily_penalty_eur,
      early_departure_rate_per_minute_eur: form.early_departure_rate_per_minute_eur,
      effective_from: form.effective_from,
      location_id: form.location_id ? Number(form.location_id) : null,
    };
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (editingId != null) {
        await configApi.penalty.update(editingId, buildPayload());
        showToast('success', t('toast.saved'));
      } else {
        await configApi.penalty.create(buildPayload());
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
      await configApi.penalty.update(editingId, { is_active: false });
      showToast('success', t('toast.saved'));
      setModalOpen(false);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setDeactivating(false);
    }
  }

  const extraColumns: Column<PenaltyConfig>[] = [
    {
      key: 'ruleType',
      header: t('config.ruleType'),
      render: (r) => (r.rule_type === 'flat_per_minute' ? t('config.flatPerMinute') : t('config.thresholdAllowance')),
    },
    {
      key: 'value',
      header: t('config.ratePerMinute'),
      align: 'right',
      render: (r) => (
        <span className="font-mono">
          {r.rule_type === 'flat_per_minute'
            ? formatCurrency(r.rate_per_minute_eur ?? 0)
            : `${formatMinutes(r.allowance_minutes ?? 0)} / ${formatCurrency(r.flat_amount_eur ?? 0)}`}
        </span>
      ),
    },
    { key: 'maxDaily', header: t('config.maxDailyPenalty'), align: 'right', render: (r) => (r.max_daily_penalty_eur != null ? <span className="font-mono">{formatCurrency(r.max_daily_penalty_eur)}</span> : '–') },
  ];

  return (
    <div>
      <PageHeader
        title={t('config.penaltiesTitle')}
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
        mobileExtraRows={(r) => [
          { label: t('config.ruleType'), value: r.rule_type === 'flat_per_minute' ? t('config.flatPerMinute') : t('config.thresholdAllowance') },
        ]}
      />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editingId != null ? t('config.editRule') : t('config.newRule')}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <RadioGroup
            name="rule-type"
            value={form.rule_type}
            onChange={(v) => set('rule_type', v as PenaltyRuleType)}
            options={[
              { value: 'flat_per_minute', label: t('config.flatPerMinute') },
              { value: 'threshold_allowance', label: t('config.thresholdAllowance') },
            ]}
          />
          {form.rule_type === 'flat_per_minute' ? (
            <CurrencyInput label={t('config.ratePerMinute')} value={form.rate_per_minute_eur} onChange={(v) => set('rate_per_minute_eur', v)} />
          ) : (
            <>
              <Input
                label={t('config.allowanceMinutes')}
                type="number"
                min={0}
                value={form.allowance_minutes ?? ''}
                onChange={(e) => set('allowance_minutes', e.target.value === '' ? null : Number(e.target.value))}
              />
              <CurrencyInput label={t('config.flatAmount')} value={form.flat_amount_eur} onChange={(v) => set('flat_amount_eur', v)} />
            </>
          )}
          <Input label={t('config.effectiveFrom')} type="date" required value={form.effective_from} onChange={(e) => set('effective_from', e.target.value)} />
          <Select
            label={`${t('config.location')} (${t('common.optional')})`}
            placeholder={t('common.all')}
            value={form.location_id}
            onChange={(e) => set('location_id', e.target.value)}
            options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
          />
          {showAdvanced ? (
            <>
              <CurrencyInput label={`${t('config.maxDailyPenalty')} (${t('common.optional')})`} value={form.max_daily_penalty_eur} onChange={(v) => set('max_daily_penalty_eur', v)} />
              <CurrencyInput label={`${t('config.earlyDepartureRate')} (${t('common.optional')})`} value={form.early_departure_rate_per_minute_eur} onChange={(v) => set('early_departure_rate_per_minute_eur', v)} />
            </>
          ) : (
            <button
              type="button"
              onClick={() => setShowAdvanced(true)}
              className="self-start text-caption font-medium text-primary-600 hover:text-primary-700"
            >
              {t('config.showAdvanced')}
            </button>
          )}
          <div className="flex justify-end gap-3">
            {editingId != null && form.is_active && (
              <Button type="button" variant="danger-outline" loading={deactivating} onClick={handleDeactivate}>
                {t('config.deactivate')}
              </Button>
            )}
            <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={submitting}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
