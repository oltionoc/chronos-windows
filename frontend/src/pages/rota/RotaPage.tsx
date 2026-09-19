import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { CalendarRange, ChevronLeft, ChevronRight, Plus, Settings2, Trash2 } from 'lucide-react';
import { rotaApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { useAuth } from '../../auth/AuthContext';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { Modal, ConfirmDialog } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Toggle } from '../../components/ui/Controls';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { RosterEntryIn, ShiftTemplate } from '../../api/types';

const WEEKLY = 'weekly';
const OFF = 'off';

function mondayOf(d: Date): Date {
  const x = new Date(d);
  const day = (x.getDay() + 6) % 7; // Monday = 0
  x.setDate(x.getDate() - day);
  x.setHours(0, 0, 0, 0);
  return x;
}
function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}
function shortDay(t: (k: string) => string, isoDate: string): string {
  const dow = (new Date(isoDate + 'T00:00:00').getDay() + 6) % 7;
  return t(`shiftSchedules.days.${dow}`);
}

// /rota — weekly grid, one row per employee, a shift per date.
export function RotaPage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const { user } = useAuth();
  usePageTitle(t('rota.title'));

  const { data: locations } = useFetch(() => locationsApi.list(), []);
  const [locationId, setLocationId] = useState<number | null>(user?.location_id ?? null);
  const [weekStart, setWeekStart] = useState<Date>(mondayOf(new Date()));
  const weekIso = iso(weekStart);

  // Chosen location: managers are pinned to their own; admins pick.
  const effectiveLocation = user?.role === 'manager' ? user.location_id : locationId ?? (locations?.[0]?.id ?? null);

  const { data: roster, loading, reload } = useFetch(
    () => (effectiveLocation ? rotaApi.week(effectiveLocation, weekIso) : Promise.resolve(null)),
    [effectiveLocation, weekIso]
  );
  const { data: templates, reload: reloadTemplates } = useFetch(
    () => (effectiveLocation ? rotaApi.templates({ location_id: effectiveLocation }) : Promise.resolve([])),
    [effectiveLocation]
  );

  // Pending edits: "empId:date" -> "weekly" | "off" | templateId(as string)
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [templatesOpen, setTemplatesOpen] = useState(false);

  function cellValue(empId: number, date: string): string {
    const key = `${empId}:${date}`;
    if (key in edits) return edits[key];
    const row = roster?.employees.find((e) => e.employee_id === empId);
    if (!row || !(date in row.assignments)) return WEEKLY;
    const v = row.assignments[date];
    return v === null ? OFF : String(v);
  }

  function setCell(empId: number, date: string, value: string) {
    setEdits((prev) => ({ ...prev, [`${empId}:${date}`]: value }));
  }

  const dirty = Object.keys(edits).length > 0;

  async function save() {
    if (!dirty) return;
    setSaving(true);
    try {
      const entries: RosterEntryIn[] = Object.entries(edits).map(([key, value]) => {
        const [empId, date] = key.split(':');
        if (value === WEEKLY) return { employee_id: Number(empId), work_date: date, clear: true };
        if (value === OFF) return { employee_id: Number(empId), work_date: date, shift_template_id: null };
        return { employee_id: Number(empId), work_date: date, shift_template_id: Number(value) };
      });
      await rotaApi.save(entries);
      showToast('success', t('rota.saved'));
      setEdits({});
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSaving(false);
    }
  }

  const options = useMemo(
    () => [
      { value: WEEKLY, label: t('rota.weekly') },
      { value: OFF, label: t('rota.dayOff') },
      ...(templates ?? []).filter((tp) => tp.is_active).map((tp) => ({ value: String(tp.id), label: tp.name })),
    ],
    [templates, t]
  );

  const shiftMonth = weekStart.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const weekEndLabel = new Date(weekStart.getTime() + 6 * 86400000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

  return (
    <div>
      <PageHeader
        title={t('rota.title')}
        subtitle={t('rota.subtitle')}
        actions={
          <Button variant="secondary" leftIcon={<Settings2 size={16} />} onClick={() => setTemplatesOpen(true)}>
            {t('rota.manageShifts')}
          </Button>
        }
      />

      <Card className="mb-4" bodyClassName="p-3">
        <div className="flex flex-wrap items-center gap-3">
          {user?.role === 'admin' && (
            <Select
              value={effectiveLocation ?? ''}
              onChange={(e) => setLocationId(Number(e.target.value))}
              options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
            />
          )}
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => setWeekStart(new Date(weekStart.getTime() - 7 * 86400000))} aria-label="previous week">
              <ChevronLeft size={18} />
            </Button>
            <span className="min-w-[150px] text-center text-body font-medium text-neutral-800">
              {shiftMonth} – {weekEndLabel}
            </span>
            <Button variant="ghost" size="sm" onClick={() => setWeekStart(new Date(weekStart.getTime() + 7 * 86400000))} aria-label="next week">
              <ChevronRight size={18} />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setWeekStart(mondayOf(new Date()))}>
              {t('rota.thisWeek')}
            </Button>
          </div>
          <div className="ml-auto">
            <Button onClick={save} loading={saving} disabled={!dirty}>
              {t('rota.save')}
            </Button>
          </div>
        </div>
      </Card>

      {dirty && <p className="mb-3 text-caption text-warning-700">{t('rota.unsaved')}</p>}

      <Card bodyClassName="p-0">
        <div className="overflow-x-auto">
          {loading || !roster ? (
            <div className="p-6">
              <div className="h-40 animate-pulse rounded-md bg-neutral-100" />
            </div>
          ) : roster.employees.length === 0 ? (
            <div className="flex flex-col items-center gap-2 p-10 text-center text-neutral-500">
              <CalendarRange size={24} />
              <p className="text-body">{t('rota.noEmployees')}</p>
            </div>
          ) : (
            <table className="w-full border-collapse text-caption">
              <thead>
                <tr className="border-b border-neutral-200">
                  <th className="sticky left-0 z-10 bg-white px-3 py-2 text-left font-semibold text-neutral-600">
                    {t('rota.employee')}
                  </th>
                  {roster.dates.map((d) => (
                    <th key={d} className="min-w-[120px] px-2 py-2 text-left font-semibold text-neutral-600">
                      <div>{shortDay(t, d)}</div>
                      <div className="font-mono text-[11px] font-normal text-neutral-400">{d.slice(5)}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {roster.employees.map((row) => (
                  <tr key={row.employee_id} className="border-b border-neutral-100 last:border-0">
                    <td className="sticky left-0 z-10 bg-white px-3 py-1.5 font-medium text-neutral-800">
                      {row.employee_name}
                    </td>
                    {roster.dates.map((d) => {
                      const val = cellValue(row.employee_id, d);
                      return (
                        <td key={d} className="px-1.5 py-1">
                          <select
                            value={val}
                            onChange={(e) => setCell(row.employee_id, d, e.target.value)}
                            className={[
                              'h-8 w-full rounded-md border bg-white px-2 text-caption transition-colors focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600',
                              val === OFF ? 'border-neutral-200 text-neutral-400' : 'border-neutral-300 text-neutral-800',
                            ].join(' ')}
                          >
                            {options.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>

      <p className="mt-3 text-caption text-neutral-500">{t('rota.recomputeHint')}</p>

      {templatesOpen && (
        <TemplatesModal
          locationId={effectiveLocation}
          templates={templates ?? []}
          onClose={() => setTemplatesOpen(false)}
          onChanged={reloadTemplates}
        />
      )}
    </div>
  );
}

function TemplatesModal({
  locationId,
  templates,
  onClose,
  onChanged,
}: {
  locationId: number | null;
  templates: ShiftTemplate[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [editing, setEditing] = useState<ShiftTemplate | 'new' | null>(null);
  const [deleting, setDeleting] = useState<ShiftTemplate | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);

  async function handleDelete() {
    if (!deleting) return;
    setDeletingBusy(true);
    try {
      await rotaApi.deleteTemplate(deleting.id);
      showToast('success', t('toast.deleted'));
      setDeleting(null);
      onChanged();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setDeletingBusy(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={t('rota.shiftsTitle')}>
      {editing ? (
        <TemplateForm
          locationId={locationId}
          template={editing === 'new' ? null : editing}
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col divide-y divide-neutral-100">
            {templates.length === 0 && <p className="py-3 text-caption text-neutral-500">{t('rota.noShifts')}</p>}
            {templates.map((tp) => (
              <div key={tp.id} className="flex items-center justify-between gap-3 py-2">
                <div>
                  <span className="text-body font-medium text-neutral-800">{tp.name}</span>
                  <span className="ml-2 font-mono text-caption text-neutral-500">
                    {tp.work_start_time.slice(0, 5)}–{tp.work_end_time.slice(0, 5)}
                    {tp.break_start_time && ` · ${t('rota.break')} ${tp.break_start_time.slice(0, 5)}–${tp.break_end_time?.slice(0, 5)}`}
                  </span>
                  {!tp.is_active && <span className="ml-2 text-caption text-neutral-400">({t('rota.inactive')})</span>}
                </div>
                <div className="flex items-center gap-2">
                  <button type="button" className="text-caption text-primary-600 hover:underline" onClick={() => setEditing(tp)}>
                    {t('common.edit')}
                  </button>
                  <button type="button" className="text-neutral-400 hover:text-danger-600" onClick={() => setDeleting(tp)} aria-label="delete">
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div>
            <Button variant="secondary" leftIcon={<Plus size={16} />} onClick={() => setEditing('new')}>
              {t('rota.newShift')}
            </Button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        loading={deletingBusy}
        title={t('rota.deleteShiftTitle')}
        description={t('rota.deleteShiftDesc')}
      />
    </Modal>
  );
}

function TemplateForm({
  locationId,
  template,
  onCancel,
  onSaved,
}: {
  locationId: number | null;
  template: ShiftTemplate | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [name, setName] = useState(template?.name ?? '');
  const [start, setStart] = useState(template?.work_start_time?.slice(0, 5) ?? '10:00');
  const [end, setEnd] = useState(template?.work_end_time?.slice(0, 5) ?? '18:00');
  const [hasBreak, setHasBreak] = useState(!!template?.break_start_time);
  const [breakStart, setBreakStart] = useState(template?.break_start_time?.slice(0, 5) ?? '13:00');
  const [breakEnd, setBreakEnd] = useState(template?.break_end_time?.slice(0, 5) ?? '13:30');
  const [grace, setGrace] = useState(template?.grace_minutes_late ?? 5);
  const [active, setActive] = useState(template?.is_active ?? true);
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      const body = {
        location_id: locationId,
        name: name.trim(),
        work_start_time: start,
        work_end_time: end,
        break_start_time: hasBreak ? breakStart : null,
        break_end_time: hasBreak ? breakEnd : null,
        grace_minutes_late: grace,
        is_active: active,
      };
      if (template) await rotaApi.updateTemplate(template.id, body);
      else await rotaApi.createTemplate(body);
      showToast('success', template ? t('toast.saved') : t('toast.created'));
      onSaved();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Input label={t('rota.shiftName')} required value={name} onChange={(e) => setName(e.target.value)} />
      <div className="grid grid-cols-2 gap-3">
        <Input label={t('rota.start')} type="time" value={start} onChange={(e) => setStart(e.target.value)} />
        <Input label={t('rota.end')} type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      <Toggle checked={hasBreak} onChange={setHasBreak} label={t('rota.hasBreak')} />
      {hasBreak && (
        <div className="grid grid-cols-2 gap-3">
          <Input label={t('rota.breakStart')} type="time" value={breakStart} onChange={(e) => setBreakStart(e.target.value)} />
          <Input label={t('rota.breakEnd')} type="time" value={breakEnd} onChange={(e) => setBreakEnd(e.target.value)} />
        </div>
      )}
      <Input label={t('rota.grace')} type="number" min={0} value={grace} onChange={(e) => setGrace(Number(e.target.value))} hint={t('common.min')} />
      <Toggle checked={active} onChange={setActive} label={t('rota.activeShift')} />
      <div className="flex justify-end gap-3">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" loading={saving}>
          {t('common.save')}
        </Button>
      </div>
    </form>
  );
}
