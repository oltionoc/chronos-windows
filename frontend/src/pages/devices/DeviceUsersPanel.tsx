import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { UserCheck, UserPlus, Users } from 'lucide-react';
import { devicesApi, employeesApi } from '../../api/endpoints';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { SearchableSelect } from '../../components/ui/Select';
import { Input } from '../../components/ui/Input';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { DeviceUserRow } from '../../api/types';

/**
 * Reads the users enrolled on a device (read-only) and lets an admin link each
 * to an employee, or create a new employee from it — so device IDs never have
 * to be typed by hand. Nothing is written back to the device.
 */
export function DeviceUsersPanel({
  deviceId,
  locationId,
  isAdmin,
}: {
  deviceId: number;
  locationId: number;
  isAdmin: boolean;
}) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const [rows, setRows] = useState<DeviceUserRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [linking, setLinking] = useState<DeviceUserRow | null>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await devicesApi.readUsers(deviceId);
      setRows(res.users);
      if (res.users.length === 0) showToast('info', t('deviceUsers.none'));
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card title={t('deviceUsers.title')}>
      <p className="mb-3 text-caption text-neutral-500">{t('deviceUsers.hint')}</p>
      <Button variant="secondary" leftIcon={<Users size={16} />} onClick={load} loading={loading}>
        {t('deviceUsers.read')}
      </Button>

      {rows && rows.length > 0 && (
        <div className="mt-4 flex flex-col divide-y divide-neutral-100">
          {rows.map((u) => (
            <div key={u.device_user_id} className="flex items-center justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-caption text-neutral-500">#{u.device_user_id}</span>
                  <span className="truncate text-body text-neutral-800">{u.name || t('deviceUsers.noName')}</span>
                </div>
              </div>
              {u.linked_employee_id ? (
                <span className="flex shrink-0 items-center gap-1.5 text-caption text-success-700">
                  <UserCheck size={14} /> {u.linked_employee_name}
                </span>
              ) : isAdmin ? (
                <Button size="sm" variant="ghost" leftIcon={<UserPlus size={14} />} onClick={() => setLinking(u)}>
                  {t('deviceUsers.link')}
                </Button>
              ) : (
                <span className="shrink-0 text-caption text-neutral-400">{t('deviceUsers.notLinked')}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {linking && (
        <LinkModal
          row={linking}
          deviceId={deviceId}
          locationId={locationId}
          onClose={() => setLinking(null)}
          onDone={() => {
            setLinking(null);
            load();
          }}
          onOpenEmployee={(id) => navigate(`/employees/${id}`)}
        />
      )}
    </Card>
  );
}

function LinkModal({
  row,
  deviceId,
  locationId,
  onClose,
  onDone,
  onOpenEmployee,
}: {
  row: DeviceUserRow;
  deviceId: number;
  locationId: number;
  onClose: () => void;
  onDone: () => void;
  onOpenEmployee: (id: number) => void;
}) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [mode, setMode] = useState<'link' | 'create'>('link');
  const [employeeId, setEmployeeId] = useState<string | number | null>(null);
  const [firstName, setFirstName] = useState(row.name.split(' ')[0] ?? '');
  const [lastName, setLastName] = useState(row.name.split(' ').slice(1).join(' '));
  const [code, setCode] = useState('');
  const [saving, setSaving] = useState(false);

  // Only employees at this device's location can be linked.
  const employeesQuery = useEmployees(locationId);

  async function enroll(empId: number) {
    await employeesApi.addDeviceEnrollment(empId, { device_id: deviceId, device_user_id: row.device_user_id });
  }

  async function submit() {
    setSaving(true);
    try {
      if (mode === 'link') {
        if (!employeeId) return;
        await enroll(Number(employeeId));
        showToast('success', t('deviceUsers.linked'));
      } else {
        if (!firstName.trim() || !code.trim()) return;
        const emp = await employeesApi.create({
          location_id: locationId,
          employee_code: code.trim(),
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          hire_date: new Date().toISOString().slice(0, 10),
          base_salary_eur: 0,
          employment_status: 'active',
        });
        await enroll(emp.id);
        showToast('success', t('deviceUsers.created'));
        onOpenEmployee(emp.id);
        return;
      }
      onDone();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={t('deviceUsers.linkTitle', { id: row.device_user_id })}>
      <div className="flex flex-col gap-5">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setMode('link')}
            className={`flex-1 rounded-md border px-3 py-2 text-caption ${mode === 'link' ? 'border-primary-600 bg-primary-50 text-primary-700' : 'border-neutral-200 text-neutral-600'}`}
          >
            {t('deviceUsers.linkExisting')}
          </button>
          <button
            type="button"
            onClick={() => setMode('create')}
            className={`flex-1 rounded-md border px-3 py-2 text-caption ${mode === 'create' ? 'border-primary-600 bg-primary-50 text-primary-700' : 'border-neutral-200 text-neutral-600'}`}
          >
            {t('deviceUsers.createNew')}
          </button>
        </div>

        {mode === 'link' ? (
          <SearchableSelect
            label={t('deviceUsers.employee')}
            placeholder={t('common.select')}
            value={employeeId}
            onChange={setEmployeeId}
            options={(employeesQuery.data?.items ?? []).map((e) => ({
              value: e.id,
              label: `${e.first_name} ${e.last_name} (${e.employee_code})`,
            }))}
          />
        ) : (
          <div className="flex flex-col gap-4">
            <Input label={t('employees.employeeCode')} required value={code} onChange={(e) => setCode(e.target.value)} />
            <div className="grid grid-cols-2 gap-3">
              <Input label={t('employees.firstName')} required value={firstName} onChange={(e) => setFirstName(e.target.value)} />
              <Input label={t('employees.lastName')} value={lastName} onChange={(e) => setLastName(e.target.value)} />
            </div>
            <p className="text-caption text-neutral-500">{t('deviceUsers.createHint')}</p>
          </div>
        )}

        <div className="flex justify-end gap-3">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="button" loading={saving} onClick={submit}>
            {mode === 'link' ? t('deviceUsers.link') : t('deviceUsers.createAndLink')}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// Small local fetch so the modal only loads employees when opened.
import { useFetch } from '../../lib/useFetch';
function useEmployees(locationId: number) {
  return useFetch(() => employeesApi.list({ location_id: locationId, page_size: 200 }), [locationId]);
}
