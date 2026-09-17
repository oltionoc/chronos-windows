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
import { formatCurrency } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { AbsenceDeductionBasis, AbsenceRuleConfig } from '../../api/types';


const EMPTY = {
  rule_type: 'no_punch_no_leave',
  deduction_basis: 'full_day_salary_fraction' as AbsenceDeductionBasis,
  deduction_value: null as number | null,
  effective_from: new Date().toISOString().slice(0, 10),
  location_id: '',
  is_active: true,
};

// /config/absence-rule — DESIGN_SPEC §5.21
export function AbsenceRuleConfigPage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  usePageTitle(t('config.absenceRuleTitle'));

  const [locationId, setLocationId] = useState('');
  const { data: locations } = useFetch(() => locationsApi.list(), []);
  const params = useMemo(() => ({ location_id: locationId ? Number(locationId) : undefined }), [locationId]);
  const { data, loading, reload } = useFetch(() => configApi.absenceRule.list(params), [JSON.stringify(params)]);

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

  function openEdit(row: AbsenceRuleConfig) {
    setEditingId(row.id);
    setForm({
      rule_type: row.rule_type,
      deduction_basis: row.deduction_basis,
      deduction_value: row.deduction_value,
      effective_from: row.effective_from,
      location_id: row.location_id ? String(row.location_id) : '',
      is_active: row.is_active,
    });
    setModalOpen(true);
  }

  function buildPayload() {
    return {
      rule_type: form.rule_type,
      deduction_basis: form.deduction_basis,
      deduction_value: form.deduction_value!,
      effective_from: form.effective_from,
      location_id: form.location_id ? Number(form.location_id) : null,
    };
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (form.deduction_value == null) return;
    setSubmitting(true);
    try {
      if (editingId != null) {
        await configApi.absenceRule.update(editingId, buildPayload());
        showToast('success', t('toast.saved'));
      } else {
        await configApi.absenceRule.create(buildPayload());
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
      await configApi.absenceRule.update(editingId, { is_active: false });
      showToast('success', t('toast.saved'));
      setModalOpen(false);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setDeactivating(false);
    }
  }

  const extraColumns: Column<AbsenceRuleConfig>[] = [
    { key: 'ruleType', header: t('config.absenceRuleType'), render: (r) => r.rule_type },
    {
      key: 'basis',
      header: t('config.deductionBasis'),
      render: (r) => (r.deduction_basis === 'flat_amount' ? t('config.flatAmountBasis') : t('config.fullDaySalaryFraction')),
    },
    {
      key: 'value',
      header: t('config.deductionValueAmount'),
      align: 'right',
      render: (r) => (r.deduction_basis === 'flat_amount' ? <span className="font-mono">{formatCurrency(r.deduction_value)}</span> : r.deduction_value.toFixed(2)),
    },
  ];

  return (
    <div>
      <PageHeader
        title={t('config.absenceRuleTitle')}
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
        mobileExtraRows={(r) => [{ label: t('config.absenceRuleType'), value: r.rule_type }]}
      />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editingId != null ? t('config.editRule') : t('config.newRule')}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <Input label={t('config.absenceRuleType')} required value={form.rule_type} onChange={(e) => set('rule_type', e.target.value)} hint={t('config.absenceRuleTypeHint')} />
          <RadioGroup
            name="deduction-basis"
            value={form.deduction_basis}
            onChange={(v) => set('deduction_basis', v as AbsenceDeductionBasis)}
            options={[
              { value: 'flat_amount', label: t('config.flatAmountBasis') },
              { value: 'full_day_salary_fraction', label: t('config.fullDaySalaryFraction') },
            ]}
          />
          {form.deduction_basis === 'flat_amount' ? (
            <CurrencyInput label={t('config.deductionValueAmount')} required value={form.deduction_value} onChange={(v) => set('deduction_value', v)} />
          ) : (
            <Input
              label={t('config.deductionValueFraction')}
              type="number"
              step="0.1"
              min={0}
              required
              value={form.deduction_value ?? ''}
              onChange={(e) => set('deduction_value', e.target.value === '' ? null : Number(e.target.value))}
            />
          )}
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
            <Button type="submit" loading={submitting} disabled={form.deduction_value == null}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
