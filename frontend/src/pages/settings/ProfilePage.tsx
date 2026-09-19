import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { authApi } from '../../api/endpoints';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { LanguageSwitcher } from '../../components/ui/LanguageSwitcher';
import { Toggle } from '../../components/ui/Controls';
import { useShowWeeklySchedule, setShowWeeklySchedule } from '../../lib/uiPrefs';
import { RoleBadge } from '../../components/ui/Badge';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { formatDateTime } from '../../lib/format';

// /settings/profile (two stacked Cards) — DESIGN_SPEC §5.24
export function ProfilePage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const { user, refresh } = useAuth();
  const showWeekly = useShowWeeklySchedule();
  usePageTitle(t('profile.title'));

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError(t('profile.passwordMismatch'));
      return;
    }
    setSubmitting(true);
    try {
      await authApi.changePassword(currentPassword, newPassword);
      showToast('success', t('profile.passwordSaved'));
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      // SECURITY: re-fetch /auth/me so `must_change_password` clears and
      // ProtectedRoute stops redirecting here — see SECURITY_REPORT.md.
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader title={t('profile.title')} />

      <div className="flex max-w-[720px] flex-col gap-6">
        <Card title={t('profile.accountSection')}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <p className="text-caption text-neutral-500">{t('profile.username')}</p>
              <p className="font-mono text-body text-neutral-800">{user?.username}</p>
            </div>
            <div>
              <p className="text-caption text-neutral-500">{t('profile.role')}</p>
              {user && <RoleBadge role={user.role} />}
            </div>
            {user?.role === 'manager' && (
              <div>
                <p className="text-caption text-neutral-500">{t('profile.assignedLocation')}</p>
                <p className="text-body text-neutral-800">{user.location_name ?? t('profile.noLocation')}</p>
              </div>
            )}
            {user?.employee_name && (
              <div>
                <p className="text-caption text-neutral-500">{t('profile.linkedEmployee')}</p>
                <p className="text-body text-neutral-800">{user.employee_name}</p>
              </div>
            )}
            <div>
              <p className="text-caption text-neutral-500">{t('profile.lastLogin')}</p>
              <p className="font-mono text-body text-neutral-800">
                {user?.last_login_at ? formatDateTime(user.last_login_at) : t('common.never')}
              </p>
            </div>
          </div>
        </Card>

        <Card title={t('profile.changePasswordSection')}>
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            {user?.must_change_password && (
              <div className="rounded-md bg-warning-50 px-3 py-2 text-sm text-warning-700">
                {t('profile.mustChangeNotice')}
              </div>
            )}
            {error && <div className="rounded-md bg-danger-50 px-3 py-2 text-sm text-danger-700">{error}</div>}
            <Input label={t('profile.currentPassword')} type="password" required value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
            <Input label={t('profile.newPassword')} type="password" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
            <Input label={t('profile.confirmNewPassword')} type="password" required value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
            <div>
              <Button type="submit" loading={submitting}>{t('profile.savePassword')}</Button>
            </div>
          </form>
        </Card>

        <Card title={t('profile.languageSection')}>
          <LanguageSwitcher size="large" />
        </Card>

        <Card title={t('profile.displaySection')}>
          <Toggle
            checked={showWeekly}
            onChange={setShowWeeklySchedule}
            label={t('profile.showWeeklySchedule')}
          />
          <p className="mt-2 text-caption text-neutral-500">{t('profile.showWeeklyScheduleHint')}</p>
        </Card>
      </div>
    </div>
  );
}
