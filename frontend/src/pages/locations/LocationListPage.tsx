import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { MapPin, Plus } from 'lucide-react';
import { locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Toggle } from '../../components/ui/Controls';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { ActiveBadge } from '../../components/ui/Badge';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { Location } from '../../api/types';

function getTimezoneOptions(): string[] {
  try {
    const values: string[] = Intl.supportedValuesOf('timeZone');
    if (values && values.length) return values;
  } catch {
    /* fall through to fallback list */
  }
  return [
    'Europe/Tirane',
    'Europe/Belgrade',
    'Europe/London',
    'Europe/Berlin',
    'Europe/Paris',
    'Europe/Rome',
    'UTC',
  ];
}

const TIMEZONES = getTimezoneOptions();

interface LocationForm {
  name: string;
  address: string;
  timezone: string;
  is_active: boolean;
}

const EMPTY: LocationForm = { name: '', address: '', timezone: 'Europe/Tirane', is_active: true };

// /locations (T1, create+edit via Modal) — DESIGN_SPEC §5.11
export function LocationListPage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  usePageTitle(t('locations.title'));

  const { data, loading, reload } = useFetch(() => locationsApi.list(), []);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<LocationForm>(EMPTY);
  const [submitting, setSubmitting] = useState(false);

  function openCreate() {
    setEditingId(null);
    setForm(EMPTY);
    setModalOpen(true);
  }

  function openEdit(loc: Location) {
    setEditingId(loc.id);
    setForm({ name: loc.name, address: loc.address ?? '', timezone: loc.timezone, is_active: loc.is_active });
    setModalOpen(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = { name: form.name, address: form.address || null, timezone: form.timezone, is_active: form.is_active };
      if (editingId) {
        await locationsApi.update(editingId, payload);
        showToast('success', t('toast.saved'));
      } else {
        await locationsApi.create(payload);
        showToast('success', t('toast.created'));
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  const columns: Column<Location>[] = [
    { key: 'name', header: t('locations.name'), render: (l) => <span className="font-medium">{l.name}</span> },
    { key: 'address', header: t('locations.address'), render: (l) => l.address ?? '–' },
    { key: 'timezone', header: t('locations.timezone'), render: (l) => l.timezone },
    {
      key: 'active',
      header: t('locations.active'),
      render: (l) => <ActiveBadge active={l.is_active} />,
    },
  ];

  return (
    <div>
      <PageHeader
        title={t('locations.title')}
        actions={
          <Button leftIcon={<Plus size={16} />} onClick={openCreate}>
            {t('locations.newLocation')}
          </Button>
        }
      />

      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(l) => l.id}
        loading={loading}
        onRowClick={openEdit}
        emptyIcon={<MapPin size={24} />}
        emptyMessage={t('locations.emptyMessage')}
        mobileCard={(l) => ({
          title: l.name,
          subtitle: l.timezone,
          badge: <ActiveBadge active={l.is_active} />,
          rows: [{ label: t('locations.address'), value: l.address ?? '–' }],
        })}
      />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editingId ? t('common.edit') : t('locations.newLocation')}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <Input label={t('locations.name')} required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          <Input label={t('locations.address')} value={form.address} onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))} />
          <Select
            label={t('locations.timezone')}
            value={form.timezone}
            onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
            options={TIMEZONES.map((tz) => ({ value: tz, label: tz }))}
          />
          <Toggle checked={form.is_active} onChange={(v) => setForm((f) => ({ ...f, is_active: v }))} label={t('locations.active')} />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={submitting}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
