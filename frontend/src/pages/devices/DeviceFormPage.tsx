import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { devicesApi, locationsApi } from '../../api/endpoints';
import { useFetch } from '../../lib/useFetch';
import { usePageTitle } from '../../layout/PageHeaderContext';
import { PageHeader } from '../../components/PageHeader';
import { Card } from '../../components/ui/Card';
import { FormSection, FormErrorBanner, FormFooterBar } from '../../components/ui/FormSection';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { useToast } from '../../components/ui/Toast';
import { ApiError } from '../../api/client';
import type { DeviceType } from '../../api/types';

const DEFAULT_PORT: Record<DeviceType, number> = { zkteco: 4370, hikvision: 80, hikvision_cloud: 443 };
const DEVICE_TYPE_VALUES: DeviceType[] = ['zkteco', 'hikvision', 'hikvision_cloud'];

// /devices/new (T3) — DESIGN_SPEC §5.9
export function DeviceFormPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showToast } = useToast();
  usePageTitle(t('devices.newDevice'), [{ label: t('devices.title'), to: '/devices' }, { label: t('devices.newDevice') }]);

  const { data: locations } = useFetch(() => locationsApi.list(), []);

  const [label, setLabel] = useState('');
  const [locationId, setLocationId] = useState('');
  const [deviceType, setDeviceType] = useState<DeviceType>('zkteco');
  const [ipAddress, setIpAddress] = useState('');
  const [port, setPort] = useState(DEFAULT_PORT.zkteco);
  const [serialNumber, setSerialNumber] = useState('');
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isCloud = deviceType === 'hikvision_cloud';

  function handleDeviceTypeChange(next: DeviceType) {
    setDeviceType(next);
    setPort(DEFAULT_PORT[next]);
  }

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!label.trim()) next.label = t('common.required');
    if (!locationId) next.location_id = t('common.required');
    if (!ipAddress.trim()) next.ip_address = t('common.required');
    // The cloud API addresses a device by serial, not by network address —
    // without it the adapter can't poll anything (see
    // worker/worker/adapters/hikvision_cloud.py).
    if (isCloud && !serialNumber.trim()) next.serial_number = t('common.required');
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!validate()) return;
    setSubmitting(true);
    try {
      const created = await devicesApi.create({
        label,
        location_id: Number(locationId),
        device_type: deviceType,
        ip_address: ipAddress,
        port,
        serial_number: serialNumber || null,
        ...(deviceType !== 'zkteco'
          ? { auth_username: authUsername || null, auth_password: authPassword || undefined }
          : {}),
      });
      showToast('success', t('toast.created'));
      navigate(`/devices/${created.id}`);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : t('toast.error'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader title={t('devices.newDevice')} />
      <form onSubmit={handleSubmit}>
        <Card className="max-w-[720px]" bodyClassName="p-6">
          {formError && <FormErrorBanner message={formError} onDismiss={() => setFormError(null)} />}
          <FormSection title={t('devices.title')} first>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Input label={t('devices.label')} required value={label} onChange={(e) => setLabel(e.target.value)} error={errors.label} />
              <Select
                label={t('devices.location')}
                required
                placeholder={t('common.select')}
                value={locationId}
                onChange={(e) => setLocationId(e.target.value)}
                options={(locations ?? []).map((l) => ({ value: l.id, label: l.name }))}
                error={errors.location_id}
              />
              <Select
                label={t('devices.deviceType')}
                required
                value={deviceType}
                onChange={(e) => handleDeviceTypeChange(e.target.value as DeviceType)}
                options={DEVICE_TYPE_VALUES.map((v) => ({ value: v, label: t(`devices.deviceTypes.${v}`) }))}
              />
              <Input
                label={isCloud ? t('devices.cloudHost') : t('devices.ipAddress')}
                required
                value={ipAddress}
                onChange={(e) => setIpAddress(e.target.value)}
                error={errors.ip_address}
                hint={isCloud ? t('devices.cloudHostHint') : t('devices.ipAddressHint')}
              />
              <Input label={t('devices.port')} type="number" value={port} onChange={(e) => setPort(Number(e.target.value))} />
              <Input
                label={isCloud ? t('devices.serialNumber') : `${t('devices.serialNumber')} (${t('common.optional')})`}
                required={isCloud}
                value={serialNumber}
                onChange={(e) => setSerialNumber(e.target.value)}
                error={errors.serial_number}
                hint={isCloud ? t('devices.serialNumberCloudHint') : undefined}
              />
              {deviceType !== 'zkteco' && (
                <>
                  <Input
                    label={isCloud ? t('devices.appKey') : t('devices.authUsername')}
                    value={authUsername}
                    onChange={(e) => setAuthUsername(e.target.value)}
                  />
                  <Input
                    label={isCloud ? t('devices.appSecret') : t('devices.authPassword')}
                    type="password"
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                  />
                </>
              )}
            </div>
          </FormSection>
        </Card>

        <FormFooterBar>
          <Button type="button" variant="secondary" onClick={() => navigate('/devices')}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" loading={submitting}>
            {t('common.save')}
          </Button>
        </FormFooterBar>
      </form>
    </div>
  );
}
