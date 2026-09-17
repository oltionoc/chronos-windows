import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarDays, Plus } from 'lucide-react';
import { holidaysApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { useAuth } from '../../auth/AuthContext';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Button } from '../../components/ui/Button';
import { Modal, ConfirmDialog } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Toggle } from '../../components/ui/Controls';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import { formatDate } from '../../lib/format';
import type { Holiday } from '../../api/types';

interface HolidayForm {
  location_id: string;
  holiday_date: string;
  name_en: string;
  name_sq: string;
  recurs_annually: boolean;
}

const EMPTY_FORM: HolidayForm = {
  location_id: '',
  holiday_date: '',
  name_en: '',
  name_sq: '',
  recurs_annually: false,
};

// /config/holidays — the calendar that decides which dates are public
// holidays. Added 2026-09-17: without it a holiday read as an unexcused
// absence for everyone who was correctly off, and holiday work paid at the
// ordinary rate.
export function HolidaysConfigPage() {
  const { t, i18n } = useTranslation();
  const { showToast } = useToast();
  const { user } = useAuth();
  usePageTitle(t('config.holidaysTitle'));

  const [year, setYear] = useState(String(new Date().getFullYear()));
  const { data, loading, reload } = useFetch(() => holidaysApi.list({ year: Number(year) }), [year]);
  const { data: locations } = useFetch(() => locationsApi.list(), []);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Holiday | null>(null);
  const [form, setForm] = useState<HolidayForm>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState<Holiday | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);

  const isAdmin = user?.role === 'admin';

  const yearOptions = useMemo(() => {
    const current = new Date().getFullYear();
    return Array.from({ length: 5 }, (_, i) => String(current - 1 + i));
  }, []);

  function openCreate() {
    setEditing(null);
    setForm({ ...EMPTY_FORM, holiday_date: `${year}-01-01` });
    setModalOpen(true);
  }

  function openEdit(h: Holiday) {
    setEditing(h);
    setForm({
      location_id: h.location_id != null ? String(h.location_id) : '',
      holiday_date: h.holiday_date,
      name_en: h.name_en,
      name_sq: h.name_sq,
      recurs_annually: h.recurs_annually,
    });
    setModalOpen(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = {
        location_id: form.location_id ? Number(form.location_id) : null,
        holiday_date: form.holiday_date,
        name_en: form.name_en,
        name_sq: form.name_sq,
        recurs_annually: form.recurs_annually,
      };
      if (editing) {
        await holidaysApi.update(editing.id, payload);
        showToast('success', t('toast.saved'));
      } else {
        await holidaysApi.create(payload);
        showToast('success', t('toast.created'));
      }
      setModalOpen(false);
      setEditing(null);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    setDeletingBusy(true);
    try {
      await holidaysApi.remove(deleting.id);
      showToast('success', t('toast.deleted'));
      setDeleting(null);
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setDeletingBusy(false);
    }
  }

  const holidayName = (h: Holiday) => (i18n.language === 'en' ? h.name_en : h.name_sq);

  const columns: Column<Holiday>[] = [
    {
      key: 'date',
      header: t('config.holidayDate'),
      render: (h) => <span className="font-mono">{formatDate(h.holiday_date)}</span>,
    },
    { key: 'name', header: t('config.name'), render: (h) => <span className="font-medium">{holidayName(h)}</span> },
    {
      key: 'location',
      header: t('config.location'),
      render: (h) => h.location_name ?? t('config.allLocations'),
    },
    {
      key: 'recurring',
      header: t('config.recursAnnually'),
      render: (h) => (h.recurs_annually ? t('common.yes') : t('common.no')),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (h) => (
        <div className="flex justify-end gap-3">
          <button type="button" className="text-caption text-primary-600 hover:underline" onClick={() => openEdit(h)}>
            {t('common.edit')}
          </button>
          <button type="button" className="text-caption text-danger-600 hover:underline" onClick={() => setDeleting(h)}>
            {t('common.delete')}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title={t('config.holidaysTitle')}
        subtitle={t('config.holidaysSubtitle')}
        actions={<Button leftIcon={<Plus size={16} />} onClick={openCreate}>{t('config.newHoliday')}</Button>}
      />

      <div className="mb-4 max-w-[200px]">
        <Select
          label={t('config.year')}
          value={year}
          onChange={(e) => setYear(e.target.value)}
          options={yearOptions.map((y) => ({ value: y, label: y }))}
        />
      </div>

      <DataTable
        columns={columns}
        rows={data ?? []}
        rowKey={(h) => h.id}
        loading={loading}
        emptyIcon={<CalendarDays size={24} />}
        emptyMessage={t('config.emptyHolidays')}
        mobileCard={(h) => ({
          title: holidayName(h),
          subtitle: <span className="font-mono">{formatDate(h.holiday_date)}</span>,
          rows: [
            { label: t('config.location'), value: h.location_name ?? t('config.allLocations') },
            { label: t('config.recursAnnually'), value: h.recurs_annually ? t('common.yes') : t('common.no') },
          ],
        })}
      />

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? t('config.editHoliday') : t('config.newHoliday')}
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <Input
            label={t('config.holidayDate')}
            type="date"
            required
            value={form.holiday_date}
            onChange={(e) => setForm((f) => ({ ...f, holiday_date: e.target.value }))}
          />
          <Input
            label={t('config.nameEn')}
            required
            value={form.name_en}
            onChange={(e) => setForm((f) => ({ ...f, name_en: e.target.value }))}
          />
          <Input
            label={t('config.nameSq')}
            required
            value={form.name_sq}
            onChange={(e) => setForm((f) => ({ ...f, name_sq: e.target.value }))}
          />
          <Select
            label={t('config.location')}
            placeholder={isAdmin ? t('config.allLocations') : undefined}
            value={form.location_id}
            onChange={(e) => setForm((f) => ({ ...f, location_id: e.target.value }))}
            options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
            hint={isAdmin ? t('config.allLocationsHint') : undefined}
          />
          <Toggle
            checked={form.recurs_annually}
            onChange={(v) => setForm((f) => ({ ...f, recurs_annually: v }))}
            label={t('config.recursAnnually')}
          />
          <p className="text-caption text-neutral-500">{t('config.holidayRecomputeHint')}</p>
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={submitting}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        loading={deletingBusy}
        title={t('config.deleteHolidayTitle')}
        description={t('config.deleteHolidayDesc')}
      />
    </div>
  );
}
