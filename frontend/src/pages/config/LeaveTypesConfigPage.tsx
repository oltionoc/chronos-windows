import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Tags, Plus } from 'lucide-react';
import { leaveApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Toggle } from '../../components/ui/Controls';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import { localizedLeaveTypeName } from '../../lib/leaveTypes';
import type { LeaveType } from '../../api/types';

interface NewForm {
  name_en: string;
  name_sq: string;
  is_paid: boolean;
  annual_entitlement_days: number | null;
  requires_approval: boolean;
}

const EMPTY_FORM: NewForm = { name_en: '', name_sq: '', is_paid: true, annual_entitlement_days: null, requires_approval: false };

// /config/leave-types (T1 with inline edit) — DESIGN_SPEC §5.22
export function LeaveTypesConfigPage() {
  const { t, i18n } = useTranslation();
  const { showToast } = useToast();
  usePageTitle(t('config.leaveTypesTitle'));

  const { data, loading, reload, setData } = useFetch(() => leaveApi.leaveTypes(), []);
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set());

  function markSaving(key: string, saving: boolean) {
    setSavingKeys((prev) => {
      const next = new Set(prev);
      if (saving) next.add(key);
      else next.delete(key);
      return next;
    });
  }

  async function updateField(lt: LeaveType, patch: Partial<LeaveType>, key: string) {
    markSaving(key, true);
    try {
      const updated = await leaveApi.updateLeaveType(lt.id, patch);
      setData((prev) => (prev ?? []).map((x) => (x.id === lt.id ? updated : x)));
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      markSaving(key, false);
    }
  }

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<NewForm>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await leaveApi.createLeaveType(form);
      showToast('success', t('toast.created'));
      setModalOpen(false);
      setForm(EMPTY_FORM);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  const columns: Column<LeaveType>[] = [
    { key: 'name', header: t('config.name'), render: (lt) => <span className="font-medium">{localizedLeaveTypeName(lt, i18n.language)}</span> },
    {
      key: 'paid',
      header: t('config.isPaid'),
      render: (lt) => (
        <Toggle
          checked={lt.is_paid}
          loading={savingKeys.has(`${lt.id}:paid`)}
          onChange={(v) => updateField(lt, { is_paid: v }, `${lt.id}:paid`)}
        />
      ),
    },
    {
      key: 'entitlement',
      header: t('config.annualEntitlement'),
      align: 'right',
      render: (lt) => (
        <input
          type="number"
          min={0}
          step="0.5"
          defaultValue={lt.annual_entitlement_days ?? ''}
          onBlur={(e) => {
            const value = e.target.value === '' ? null : Number(e.target.value);
            if (value !== lt.annual_entitlement_days) updateField(lt, { annual_entitlement_days: value }, `${lt.id}:entitlement`);
          }}
          className="h-8 w-20 rounded-md border border-neutral-300 bg-white px-2 text-right font-mono text-body tabular-nums transition-[border-color] duration-100 ease-out focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600 focus:ring-offset-0"
        />
      ),
    },
    {
      key: 'approval',
      header: t('config.requiresApproval'),
      render: (lt) => (
        <Toggle
          checked={lt.requires_approval}
          loading={savingKeys.has(`${lt.id}:approval`)}
          onChange={(v) => updateField(lt, { requires_approval: v }, `${lt.id}:approval`)}
        />
      ),
    },
    {
      key: 'active',
      header: t('config.active'),
      render: (lt) => (
        <Toggle
          checked={lt.is_active}
          loading={savingKeys.has(`${lt.id}:active`)}
          onChange={(v) => updateField(lt, { is_active: v }, `${lt.id}:active`)}
        />
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title={t('config.leaveTypesTitle')}
        actions={<Button leftIcon={<Plus size={16} />} onClick={() => setModalOpen(true)}>{t('config.newLeaveType')}</Button>}
      />

      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(lt) => lt.id}
        loading={loading}
        emptyIcon={<Tags size={24} />}
        emptyMessage={t('config.emptyLeaveTypes')}
        mobileCard={(lt) => ({
          title: localizedLeaveTypeName(lt, i18n.language),
          badge: <Toggle checked={lt.is_active} loading={savingKeys.has(`${lt.id}:active`)} onChange={(v) => updateField(lt, { is_active: v }, `${lt.id}:active`)} />,
          rows: [
            { label: t('config.isPaid'), value: <Toggle checked={lt.is_paid} loading={savingKeys.has(`${lt.id}:paid`)} onChange={(v) => updateField(lt, { is_paid: v }, `${lt.id}:paid`)} /> },
            { label: t('config.requiresApproval'), value: <Toggle checked={lt.requires_approval} loading={savingKeys.has(`${lt.id}:approval`)} onChange={(v) => updateField(lt, { requires_approval: v }, `${lt.id}:approval`)} /> },
            { label: t('config.annualEntitlement'), value: lt.annual_entitlement_days != null ? <span className="font-mono">{lt.annual_entitlement_days}</span> : '–' },
          ],
        })}
      />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={t('config.newLeaveType')}>
        <form onSubmit={handleCreate} className="flex flex-col gap-5">
          <Input label={t('config.nameEn')} required value={form.name_en} onChange={(e) => setForm((f) => ({ ...f, name_en: e.target.value }))} />
          <Input label={t('config.nameSq')} required value={form.name_sq} onChange={(e) => setForm((f) => ({ ...f, name_sq: e.target.value }))} />
          <Toggle checked={form.is_paid} onChange={(v) => setForm((f) => ({ ...f, is_paid: v }))} label={t('config.isPaid')} />
          <Input
            label={t('config.annualEntitlement')}
            type="number"
            min={0}
            step="0.5"
            value={form.annual_entitlement_days ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, annual_entitlement_days: e.target.value === '' ? null : Number(e.target.value) }))}
          />
          <Toggle checked={form.requires_approval} onChange={(v) => setForm((f) => ({ ...f, requires_approval: v }))} label={t('config.requiresApproval')} />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={submitting}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
