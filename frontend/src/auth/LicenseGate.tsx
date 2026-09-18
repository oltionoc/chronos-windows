import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Clock, KeyRound } from 'lucide-react';
import { licenseApi } from '../api/endpoints';
import { useLicense } from './LicenseContext';
import { useAuth } from './AuthContext';
import { Button } from '../components/ui/Button';
import { Textarea } from '../components/ui/Textarea';
import { useToast } from '../components/ui/Toast';
import { ApiError } from '../api/client';
import { formatDate } from '../lib/format';

/**
 * Wraps the authenticated app. Normally renders its children with a slim
 * warning banner when the licence is close to expiry; once expired it replaces
 * the whole app with a lock screen. An admin can paste a new key there and get
 * straight back in; a manager is told to contact the administrator. The worker
 * keeps recording punches the whole time, so nothing is lost while locked.
 */
export function LicenseGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { status, expired, refresh } = useLicense();

  if (expired) return <LockScreen onCleared={refresh} />;

  return (
    <>
      {status?.expiring_soon && (
        <div className="flex items-center gap-2 border-b border-warning-200 bg-warning-50 px-4 py-2 text-caption text-warning-800">
          <Clock size={14} className="shrink-0" />
          <span>{t('license.bannerExpiring', { days: status.days_left, date: formatDate(status.expires) })}</span>
        </div>
      )}
      {children}
    </>
  );
}

function LockScreen({ onCleared }: { onCleared: () => Promise<void> }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { showToast } = useToast();
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const isAdmin = user?.role === 'admin';

  async function handleInstall(e: FormEvent) {
    e.preventDefault();
    if (!key.trim()) return;
    setSaving(true);
    try {
      await licenseApi.install(key.trim());
      showToast('success', t('license.installed'));
      await onCleared();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-neutral-50 p-4">
      <div className="w-full max-w-[460px] rounded-xl border border-neutral-200 bg-white p-8 shadow-sm">
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-lg bg-danger-100 text-danger-700">
          <KeyRound size={22} />
        </div>
        <h1 className="text-h3 font-semibold text-neutral-900">{t('license.lockTitle')}</h1>
        <p className="mt-2 text-body text-neutral-600">{t('license.lockBody')}</p>

        {isAdmin ? (
          <form onSubmit={handleInstall} className="mt-6 flex flex-col gap-3">
            <Textarea
              value={key}
              onChange={(e) => setKey(e.target.value)}
              rows={4}
              placeholder={t('license.keyPlaceholder')}
              className="font-mono text-caption"
            />
            <Button type="submit" loading={saving} disabled={!key.trim()}>
              {t('license.install')}
            </Button>
          </form>
        ) : (
          <p className="mt-6 rounded-md border border-neutral-200 bg-neutral-50 px-4 py-3 text-caption text-neutral-600">
            {t('license.lockManager')}
          </p>
        )}
      </div>
    </div>
  );
}
