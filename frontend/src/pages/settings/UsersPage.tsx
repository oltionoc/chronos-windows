import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { UserCog, Plus } from 'lucide-react';
import { usersApi, employeesApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { FilterBar } from '../../components/ui/FilterBar';
import { Select, SearchableSelect } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Toggle } from '../../components/ui/Controls';
import { DataTable } from '../../components/ui/Table';
import type { Column } from '../../components/ui/Table';
import { RoleBadge, Badge } from '../../components/ui/Badge';
import { formatDateTime } from '../../lib/format';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { AppUser, Role } from '../../api/types';

const ROLE_VALUES: Role[] = ['admin', 'manager'];

interface FormState {
  username: string;
  password: string;
  role: Role;
  location_id: string | number | null;
  employee_id: string | number | null;
  is_active: boolean;
}

const EMPTY: FormState = { username: '', password: '', role: 'manager', location_id: null, employee_id: null, is_active: true };

// /settings/users (T1) — DESIGN_SPEC §5.23
export function UsersPage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  usePageTitle(t('users.title'));

  const [role, setRole] = useState('');
  const params = useMemo(() => ({ role: (role || undefined) as Role | undefined, page_size: 100 }), [role]);
  const { data, loading, reload } = useFetch(() => usersApi.list(params), [JSON.stringify(params)]);
  const { data: employees } = useFetch(() => employeesApi.list({ page_size: 100 }), []);
  const { data: locations } = useFetch(() => locationsApi.list(), []);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<AppUser | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [resetting, setResetting] = useState(false);

  function openCreate() {
    setEditingUser(null);
    setForm(EMPTY);
    setModalOpen(true);
  }

  function openEdit(u: AppUser) {
    setEditingUser(u);
    setForm({ username: u.username, password: '', role: u.role, location_id: u.location_id, employee_id: u.employee_id, is_active: u.is_active });
    setModalOpen(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    // admin accounts never carry a location_id (BLUEPRINT §3.14) — cleared
    // regardless of what was previously selected before switching roles.
    const location_id = form.role === 'manager' && form.location_id ? Number(form.location_id) : null;
    try {
      if (editingUser) {
        await usersApi.update(editingUser.id, {
          role: form.role,
          location_id,
          employee_id: form.employee_id ? Number(form.employee_id) : null,
          is_active: form.is_active,
        });
        showToast('success', t('toast.saved'));
      } else {
        await usersApi.create({
          username: form.username,
          password: form.password,
          role: form.role,
          location_id,
          employee_id: form.employee_id ? Number(form.employee_id) : null,
          is_active: form.is_active,
        });
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

  async function handleResetPassword() {
    if (!editingUser || !newPassword) return;
    setResetting(true);
    try {
      await usersApi.resetPassword(editingUser.id, newPassword);
      showToast('success', t('toast.saved'));
      setResetOpen(false);
      setNewPassword('');
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setResetting(false);
    }
  }

  async function toggleActive(u: AppUser, value: boolean) {
    try {
      await usersApi.update(u.id, { is_active: value });
      reload();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    }
  }

  const employeeOptions = (employees?.items ?? []).map((e) => ({ value: e.id, label: `${e.first_name} ${e.last_name}` }));
  const locationOptions = (locations ?? []).map((l) => ({ value: l.id, label: l.name }));

  const columns: Column<AppUser>[] = [
    { key: 'username', header: t('users.username'), render: (u) => <span className="font-medium">{u.username}</span> },
    { key: 'role', header: t('users.role'), render: (u) => <RoleBadge role={u.role} /> },
    {
      key: 'location',
      header: t('users.location'),
      render: (u) =>
        u.role !== 'manager' ? '–' : u.location_name ? u.location_name : <Badge className="bg-warning-100 text-warning-700">{t('users.unassigned')}</Badge>,
    },
    { key: 'employee', header: t('users.linkedEmployee'), render: (u) => u.employee_name || '–' },
    {
      key: 'active',
      header: t('users.active'),
      render: (u) => (
        <span onClick={(e) => e.stopPropagation()}>
          <Toggle checked={u.is_active} onChange={(v) => toggleActive(u, v)} />
        </span>
      ),
    },
    { key: 'lastLogin', header: t('users.lastLogin'), render: (u) => (u.last_login_at ? <span className="font-mono">{formatDateTime(u.last_login_at)}</span> : t('common.never')) },
  ];

  return (
    <div>
      <PageHeader
        title={t('users.title')}
        actions={<Button leftIcon={<Plus size={16} />} onClick={openCreate}>{t('users.newAccount')}</Button>}
      />

      <div className="mb-4">
        <FilterBar hasActiveFilters={!!role} onClearFilters={() => setRole('')}>
          <Select
            label={t('users.role')}
            value={role}
            onChange={(e) => setRole(e.target.value)}
            placeholder={t('common.all')}
            options={ROLE_VALUES.map((r) => ({ value: r, label: t(`status.role.${r}`) }))}
            containerClassName="w-48"
          />
        </FilterBar>
      </div>

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(u) => u.id}
        loading={loading}
        onRowClick={openEdit}
        emptyIcon={<UserCog size={24} />}
        emptyMessage={t('users.emptyMessage')}
        mobileCard={(u) => ({
          title: u.username,
          subtitle:
            u.role === 'manager'
              ? u.location_name || <Badge className="bg-warning-100 text-warning-700">{t('users.unassigned')}</Badge>
              : u.employee_name || '–',
          badge: <RoleBadge role={u.role} />,
          rows: [
            { label: t('users.lastLogin'), value: u.last_login_at ? <span className="font-mono">{formatDateTime(u.last_login_at)}</span> : t('common.never') },
          ],
        })}
      />

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editingUser ? t('common.edit') : t('users.newAccount')}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <Input
            label={t('users.username')}
            required
            disabled={!!editingUser}
            value={form.username}
            onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
          />
          {editingUser ? (
            <Button type="button" variant="secondary" onClick={() => setResetOpen(true)}>{t('users.resetPassword')}</Button>
          ) : (
            <Input
              label={t('users.password')}
              type="password"
              required
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            />
          )}
          <Select
            label={t('users.role')}
            value={form.role}
            onChange={(e) => {
              const nextRole = e.target.value as Role;
              // Switching away from Manager unmounts the Location field and
              // clears any selected value before submit (DESIGN_SPEC §5.23).
              setForm((f) => ({ ...f, role: nextRole, location_id: nextRole === 'manager' ? f.location_id : null }));
            }}
            options={ROLE_VALUES.map((r) => ({ value: r, label: t(`status.role.${r}`) }))}
          />
          {form.role === 'manager' && (
            <div>
              <Select
                label={t('users.assignedLocation')}
                requiredMark
                placeholder={t('common.select')}
                value={form.location_id ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, location_id: e.target.value }))}
                options={locationOptions}
              />
              {!form.location_id && (
                <p className="mt-1 text-caption text-warning-600">{t('users.assignedLocationWarning')}</p>
              )}
            </div>
          )}
          <SearchableSelect
            label={`${t('users.linkedEmployee')} (${t('common.optional')})`}
            placeholder={t('common.none')}
            value={form.employee_id}
            onChange={(v) => setForm((f) => ({ ...f, employee_id: v }))}
            options={employeeOptions}
          />
          <Toggle checked={form.is_active} onChange={(v) => setForm((f) => ({ ...f, is_active: v }))} label={t('users.active')} />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setModalOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" loading={submitting}>{t('common.save')}</Button>
          </div>
        </form>
      </Modal>

      <Modal open={resetOpen} onClose={() => setResetOpen(false)} title={t('users.resetPassword')} size="sm">
        <div className="flex flex-col gap-5">
          <p className="text-body-muted text-neutral-500">{t('users.resetPasswordConfirm')}</p>
          <Input label={t('users.newPassword')} type="password" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => setResetOpen(false)}>{t('common.cancel')}</Button>
            <Button onClick={handleResetPassword} loading={resetting} disabled={!newPassword}>{t('common.confirm')}</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
