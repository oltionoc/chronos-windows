import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { KeyRound } from 'lucide-react';
import { licenseApi } from '../../api/endpoints';
import { useLicense } from '../../auth/LicenseContext';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Textarea } from '../../components/ui/Textarea';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import { formatDate } from '../../lib/format';

// /settings/license — view the licence and paste a new key. Admin only.
export function LicensePage() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const { status, refresh } = useLicense();
  usePageTitle(t('license.title'));

  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);

  async function handleInstall(e: FormEvent) {
    e.preventDefault();
    if (!key.trim()) return;
    setSaving(true);
    try {
      await licenseApi.install(key.trim());
      showToast('success', t('license.installed'));
      setKey('');
      await refresh();
    } catch (err) {
      showToast('error', err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSaving(false);
    }
  }

  const tone = status?.expired ? 'danger' : status?.expiring_soon ? 'warning' : 'ok';
  const toneClass = {
    ok: 'border-success-200 bg-success-50 text-success-800',
    warning: 'border-warning-200 bg-warning-50 text-warning-800',
    danger: 'border-danger-200 bg-danger-50 text-danger-800',
  }[tone];

  return (
    <div className="max-w-[640px]">
      <PageHeader title={t('license.title')} subtitle={t('license.subtitle')} />

      <Card className="mb-5">
        {status ? (
          <div className="flex flex-col gap-4">
            <div className={`rounded-md border px-4 py-3 text-sm ${toneClass}`}>
              {status.expired
                ? t('license.stateExpired', { date: formatDate(status.expires) })
                : status.expiring_soon
                  ? t('license.stateExpiring', { days: status.days_left, date: formatDate(status.expires) })
                  : t('license.stateValid', { date: formatDate(status.expires) })}
            </div>
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-neutral-500">{t('license.issuedTo')}</dt>
                <dd className="font-medium text-neutral-800">{status.issued_to}</dd>
              </div>
              <div>
                <dt className="text-neutral-500">{t('license.expires')}</dt>
                <dd className="font-mono text-neutral-800">{formatDate(status.expires)}</dd>
              </div>
            </dl>
          </div>
        ) : (
          <div className="h-16 animate-pulse rounded-md bg-neutral-100" />
        )}
      </Card>

      <Card>
        <form onSubmit={handleInstall} className="flex flex-col gap-4">
          <div>
            <h3 className="flex items-center gap-2 text-body font-semibold text-neutral-800">
              <KeyRound size={16} /> {t('license.installTitle')}
            </h3>
            <p className="mt-1 text-caption text-neutral-500">{t('license.installHint')}</p>
          </div>
          <Textarea
            value={key}
            onChange={(e) => setKey(e.target.value)}
            rows={4}
            placeholder={t('license.keyPlaceholder')}
            className="font-mono text-caption"
          />
          <div className="flex justify-end">
            <Button type="submit" loading={saving} disabled={!key.trim()}>
              {t('license.install')}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
